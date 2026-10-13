"""KDT 훈련과정 수집기: 고용24 오픈API → (부족한 값만) 상세 페이지 → Supabase.

사용 예:
    python -m crawler.main                 # 평소 실행 (최근 약 15개월 ~ 6개월 뒤 개강 회차)
    python -m crawler.main --full          # 처음 한 번: KDT 시작(2020-12)부터 전부
    python -m crawler.main --inspect out/  # API 원본·상세 페이지 샘플 저장 (필드 확인용)
    python -m crawler.main --dry-run       # DB에 쓰지 않고 결과만 확인

환경변수: WORK24_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from .db import COLUMNS, SupabaseDB
from .detail_scraper import DetailScraper
from .work24_api import KDT_CODE, ApiError, Work24Api, pick

log = logging.getLogger("collector")

KST = timezone(timedelta(hours=9))
KDT_START = date(2020, 12, 1)

COURSE_LEVEL = ("training_fee", "ncs_code", "ncs_job", "ncs_level", "training_days", "training_hours")
SESSION_SCRAPE_FIELDS = ("evaluators", "confirmed")


# ---------------------------------------------------------------------------
# 값 정리
# ---------------------------------------------------------------------------

def to_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    s = re.sub(r"[^\d.\-]", "", str(v))
    if not s or s in {"-", "."}:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def to_float(v: Any) -> Optional[float]:
    """'53.3', '79.2%', '0' 등 → float. 'A'(개설예정) 같은 코드값은 None."""
    if v is None:
        return None
    s = str(v).strip().replace("%", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def to_date(v: Any) -> Optional[str]:
    if not v:
        return None
    d = re.sub(r"[^\d]", "", str(v))
    if len(d) >= 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return None


def from_api(item: dict) -> dict:
    """오픈API 레코드(목록·일정 공통) → DB 컬럼 dict. 값이 없는 키는 넣지 않는다."""
    raw = {
        "tracse_id": pick(item, "tracse_id"),
        "trainst_cstmr_id": pick(item, "trainst_cstmr_id"),
        "session": to_int(pick(item, "session")),
        "course_name": pick(item, "course_name"),
        "institution": pick(item, "institution"),
        "training_fee": to_int(pick(item, "training_fee")),
        "capacity": to_int(pick(item, "capacity")),
        "applicants": to_int(pick(item, "applicants")),
        "confirmed": to_int(pick(item, "confirmed")),
        "completed": to_int(pick(item, "completed")),
        "satisfaction": to_float(pick(item, "satisfaction")),
        "employment_rate_3m": to_float(pick(item, "employment_rate_3m")),
        "employment_rate_6m": to_float(pick(item, "employment_rate_6m")),
        "start_date": to_date(pick(item, "start_date")),
        "end_date": to_date(pick(item, "end_date")),
        "ncs_code": pick(item, "ncs_code"),
        "training_hours": to_int(pick(item, "training_hours")),
        "training_days": to_int(pick(item, "training_days")),
        "ncs_job": pick(item, "ncs_job"),
        "ncs_level": to_int(pick(item, "ncs_level")),
    }
    if raw["satisfaction"] == 0:
        raw["satisfaction"] = None  # 평가 전
    for k in ("course_name", "institution", "ncs_job"):
        if isinstance(raw[k], str):
            raw[k] = re.sub(r"\s+", " ", raw[k]).strip()
    return {k: v for k, v in raw.items() if v not in (None, "")}


def merge(base: dict, new: dict) -> dict:
    """new의 값이 있는 칸만 base 위에 덮어쓴다 (None으로 지우지 않음)."""
    out = dict(base)
    for k, v in new.items():
        if v is not None and v != "":
            out[k] = v
    return out


def fill_derived(row: dict) -> None:
    fee, hours = row.get("training_fee"), row.get("training_hours")
    if fee and hours:
        row["hourly_fee"] = round(fee / hours)
    cap, conf, done = row.get("capacity"), row.get("confirmed"), row.get("completed")
    if cap and conf is not None:
        row["recruitment_rate"] = round(conf / cap * 100, 1)
    if conf and done is not None:
        row["completion_rate"] = round(done / conf * 100, 1)


def key_of(row: dict) -> tuple:
    return (row["tracse_id"], row["trainst_cstmr_id"], int(row["session"]))


def days_ago(ts: Optional[str], now: datetime) -> float:
    if not ts:
        return 1e9
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return 1e9
    return (now - t).total_seconds() / 86400


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--full", action="store_true", help="KDT 시작(2020-12)부터 전체 수집")
    p.add_argument("--since", help="개강일 시작 (YYYY-MM-DD)")
    p.add_argument("--until", help="개강일 끝 (YYYY-MM-DD)")
    p.add_argument("--days-back", type=int, default=450, help="평소 실행 시 오늘 기준 과거 일수")
    p.add_argument("--days-ahead", type=int, default=180, help="평소 실행 시 오늘 기준 미래 일수")
    p.add_argument("--max-api-calls", type=int, default=int(os.getenv("MAX_API_CALLS", "4000")))
    p.add_argument("--max-scrape", type=int, default=int(os.getenv("MAX_SCRAPE", "400")),
                   help="한 번 실행에 여는 상세 페이지 최대 수")
    p.add_argument("--scrape-delay", type=float, default=1.5)
    p.add_argument("--rescrape-days", type=int, default=14, help="같은 회차를 다시 크롤링하기까지 일수")
    p.add_argument("--skip-schedule", action="store_true", help="훈련일정 API(310L03) 호출 안 함")
    p.add_argument("--skip-info", action="store_true", help="과정정보 API(310L02) 호출 안 함")
    p.add_argument("--skip-scrape", action="store_true", help="상세 페이지 크롤링 안 함")
    p.add_argument("--dry-run", action="store_true", help="DB에 쓰지 않음")
    p.add_argument("--inspect", metavar="DIR", help="API 원본 응답과 상세 페이지 샘플을 DIR에 저장")
    p.add_argument("--csv", metavar="PATH", help="결과를 CSV로도 저장")
    return p.parse_args(argv)


def run(args) -> int:
    today = datetime.now(KST).date()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    if args.full:
        start, end = KDT_START, today + timedelta(days=args.days_ahead)
    else:
        start = today - timedelta(days=args.days_back)
        end = today + timedelta(days=args.days_ahead)
    if args.since:
        start = date.fromisoformat(args.since)
    if args.until:
        end = date.fromisoformat(args.until)
    log.info("개강일 범위: %s ~ %s", start, end)

    api = Work24Api(os.environ.get("WORK24_API_KEY", ""), max_calls=args.max_api_calls,
                    inspect_dir=args.inspect)
    db = SupabaseDB(os.environ.get("SUPABASE_URL", ""),
                    os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""), dry_run=args.dry_run)

    # 1) 목록 API: 회차 단위 기본 데이터 ------------------------------------
    rows: dict[tuple, dict] = {}
    for item in api.list_sessions(start, end, KDT_CODE):
        rec = from_api(item)
        if not all(rec.get(k) for k in ("tracse_id", "trainst_cstmr_id", "session")):
            continue
        rec["api_synced_at"] = now_iso
        rows[key_of(rec)] = merge(rows.get(key_of(rec), {}), rec)
    log.info("목록 API: %d개 회차, %d개 과정", len(rows), len({(k[0], k[1]) for k in rows}))
    if not rows:
        log.error("목록 API 결과가 0건입니다. 인증키와 파라미터를 확인하세요 (--inspect로 원본 확인).")
        return 2

    # 2) 기존 DB 값과 합치기 ------------------------------------------------
    existing = db.existing_for_courses(k[0] for k in rows)
    log.info("DB 기존 행: %d", len(existing))
    for k, ex in existing.items():
        base = {c: ex.get(c) for c in COLUMNS}
        rows[k] = merge(base, rows.get(k, {}))

    courses: dict[tuple, list[tuple]] = defaultdict(list)
    for k in rows:
        courses[(k[0], k[1])].append(k)

    # 3) 과정정보 API(310L02): 훈련시간·NCS --------------------------------
    stats = defaultdict(int)
    if not args.skip_info:
        for (tid, cst), keys in courses.items():
            if all(rows[k].get("training_hours") and rows[k].get("ncs_job") for k in keys):
                continue
            latest = max(keys, key=lambda k: k[2])
            try:
                info = api.course_info(tid, latest[2], cst)
            except ApiError as e:
                log.warning("과정정보 API 중단: %s", e)
                break
            rec = from_api(info) if info else {}
            course_vals = {c: rec[c] for c in COURSE_LEVEL if rec.get(c)}
            if course_vals:
                stats["info_ok"] += 1
                for k in keys:
                    # 훈련비는 회차마다 다를 수 있으니 비어 있을 때만 채운다
                    vals = dict(course_vals)
                    if rows[k].get("training_fee"):
                        vals.pop("training_fee", None)
                    rows[k] = merge(rows[k], vals)

    # 4) 훈련일정 API(310L03): 수강·수료 인원, 취업률 -----------------------
    if not args.skip_schedule:
        for (tid, cst), keys in courses.items():
            # 끝난 지 9개월 넘고 값이 다 찬 과정은 건너뜀 (실적이 더 안 바뀜)
            def settled(k):
                r = rows[k]
                ed = r.get("end_date")
                old = ed and date.fromisoformat(ed) < today - timedelta(days=270)
                return old and r.get("confirmed") is not None and r.get("employment_rate_6m") is not None
            if all(settled(k) for k in keys):
                continue
            try:
                sched = api.schedule(tid, cst)
            except ApiError as e:
                log.warning("훈련일정 API 중단: %s", e)
                break
            template = rows[max(keys, key=lambda k: k[2])]
            for item in sched:
                rec = from_api(item)
                sess = rec.get("session")
                if not sess:
                    continue
                rec.update(tracse_id=tid, trainst_cstmr_id=cst, session=sess)
                k = key_of(rec)
                if k not in rows:
                    # 목록 범위 밖의 옛 회차: 과정 공통값을 물려받아 새로 추가
                    base = {c: template.get(c) for c in ("institution", "course_name", *COURSE_LEVEL)}
                    rows[k] = base
                    courses[(tid, cst)].append(k)
                    stats["schedule_new_sessions"] += 1
                rec["api_synced_at"] = now_iso
                rows[k] = merge(rows[k], rec)
            stats["schedule_ok"] += 1

    # 5) 상세 페이지 크롤링: API에 없는 값만 -------------------------------
    if not args.skip_scrape:
        scraper = DetailScraper(delay=args.scrape_delay, max_pages=args.max_scrape,
                                dump_dir=os.path.join(args.inspect, "detail") if args.inspect else None)
        todo = []
        for (tid, cst), keys in courses.items():
            course_missing = not all(rows[k].get(c) for k in keys for c in ("ncs_level", "training_hours", "ncs_job"))
            for k in keys:
                r = rows[k]
                started = r.get("start_date") and r["start_date"] <= today.isoformat()
                sess_missing = started and any(r.get(c) is None for c in SESSION_SCRAPE_FIELDS)
                if (course_missing or sess_missing) and days_ago(r.get("web_scraped_at"), now) >= args.rescrape_days:
                    todo.append(k)
        # 최근 개강 회차부터
        todo.sort(key=lambda k: rows[k].get("start_date") or "", reverse=True)
        log.info("상세 페이지 크롤링 대상 %d개 (이번 실행 최대 %d)", len(todo), args.max_scrape)

        course_done: set[tuple] = set()
        for k in todo:
            if scraper.exhausted:
                break
            tid, cst, sess = k
            r = rows[k]
            sess_missing = any(r.get(c) is None for c in SESSION_SCRAPE_FIELDS)
            if not sess_missing and (tid, cst) in course_done:
                continue
            got = scraper.fetch(tid, sess, KDT_CODE, cst)
            r["web_scraped_at"] = now_iso
            if not got:
                stats["scrape_fail"] += 1
                continue
            stats["scrape_ok"] += 1
            # 회차 단위 값
            sess_vals = {c: got[c] for c in ("evaluators", "confirmed", "completed", "completion_rate", "capacity")
                         if c in got and r.get(c) is None}
            if r.get("satisfaction") is None and "satisfaction" in got:
                sess_vals["satisfaction"] = got["satisfaction"]
            rows[k] = merge(r, sess_vals)
            # 과정 단위 값은 같은 과정의 모든 회차에 (비어 있는 칸만)
            course_vals = {c: got[c] for c in ("ncs_level", "ncs_job", "ncs_code", "training_hours", "training_days")
                           if c in got}
            if course_vals:
                course_done.add((tid, cst))
                for kk in courses[(tid, cst)]:
                    rows[kk] = merge(rows[kk], {c: v for c, v in course_vals.items() if rows[kk].get(c) is None})

    # 6) 계산값 + 저장 ------------------------------------------------------
    out = []
    for r in rows.values():
        if not r.get("institution") or not r.get("course_name"):
            stats["skipped_no_name"] += 1
            continue
        r["source"] = r.get("source") or "api"
        fill_derived(r)
        out.append(r)

    n = db.upsert(out)
    merged = db.merge_legacy_rows()
    log.info("저장 %d행, 시트 이전 행과 병합 %s행", n, merged)

    if args.csv:
        os.makedirs(os.path.dirname(os.path.abspath(args.csv)), exist_ok=True)
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(sorted(out, key=lambda r: (r.get("start_date") or ""), reverse=True))

    report(out, stats, api.calls, start, end, args)
    return 0


def report(rows: list[dict], stats: dict, api_calls: int, start, end, args) -> None:
    total = len(rows) or 1
    cover = {c: sum(1 for r in rows if r.get(c) not in (None, "")) for c in
             ("training_fee", "training_hours", "ncs_job", "ncs_level", "capacity", "applicants",
              "confirmed", "completed", "satisfaction", "evaluators", "employment_rate_6m")}
    lines = [
        f"## KDT 수집 결과 ({datetime.now(KST):%Y-%m-%d %H:%M} KST)",
        f"- 개강일 범위: {start} ~ {end}{' (dry-run)' if args.dry_run else ''}",
        f"- 저장 회차: {len(rows)} / API 호출: {api_calls}",
        f"- 과정정보 API 성공: {stats['info_ok']} / 훈련일정 API 성공: {stats['schedule_ok']} "
        f"(새 회차 {stats['schedule_new_sessions']})",
        f"- 상세 페이지: 성공 {stats['scrape_ok']} / 실패 {stats['scrape_fail']}",
        "",
        "| 항목 | 채워진 비율 |",
        "|---|---|",
        *[f"| {c} | {v / total * 100:.0f}% ({v}) |" for c, v in cover.items()],
    ]
    text = "\n".join(lines)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args(argv)
    try:
        return run(args)
    except Exception:
        log.exception("수집 실패")
        return 1


if __name__ == "__main__":
    sys.exit(main())
