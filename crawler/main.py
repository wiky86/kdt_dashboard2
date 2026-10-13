"""KDT 훈련과정 수집기: 고용24 웹페이지 크롤링 → Supabase.

1. KDT 목록 페이지를 브라우저(Playwright)로 넘기며 과정을 모은다.
2. DB에 이미 있는 과정과 합친 뒤, 과정마다 필요한 회차의 상세 페이지를 읽는다.
   - 아직 없는 회차 (처음 보는 과정이면 1회차부터 전부)
   - 값이 아직 바뀌는 회차 (종강 후 9개월 이내 또는 값이 빈 회차)
   - 진행 중인 과정은 '마지막 회차 + 1'도 확인 (새 회차 발견)
3. 회차별 값을 Supabase에 저장한다. 저장된 값은 빈 값으로 덮어쓰지 않는다.

사용 예:
    python -m crawler.main                     # 평소 실행
    python -m crawler.main --max-pages 6000    # 처음: 상세 페이지를 많이
    python -m crawler.main --inspect out/x --dry-run --max-pages 10   # 시험 실행

환경변수: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
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
from .list_crawler import KDT_CODE, LIST_URL, CourseRef, ListCrawler

log = logging.getLogger("collector")

KST = timezone(timedelta(hours=9))

COURSE_LEVEL = ("ncs_code", "ncs_job", "ncs_level", "training_days", "training_hours")
SESSION_FIELDS = ("start_date", "end_date", "training_fee", "capacity", "applicants", "confirmed",
                  "completed", "satisfaction", "evaluators", "completion_rate",
                  "employment_rate_3m", "employment_rate_6m")


# ---------------------------------------------------------------------------
# 값 정리 (시트 이전 스크립트도 사용)
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
    if conf and done is not None and row.get("completion_rate") is None:
        row["completion_rate"] = round(done / conf * 100, 1)


def days_since(ts: Optional[str], now: datetime) -> float:
    if not ts:
        return 1e9
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return 1e9
    return (now - t).total_seconds() / 86400


def is_live(row: dict, today: date) -> bool:
    """값이 아직 바뀔 수 있는 회차인가 (모집 중·진행 중·종강 후 9개월 이내, 또는 핵심 값이 빔)."""
    ed = row.get("end_date")
    if not ed:
        return True
    if date.fromisoformat(ed) >= today - timedelta(days=270):
        return True
    return any(row.get(c) is None for c in ("confirmed", "satisfaction"))


# ---------------------------------------------------------------------------
# 수집 계획
# ---------------------------------------------------------------------------

def plan_tasks(courses: dict[tuple, CourseRef], rows: dict[tuple, dict], skips: dict[tuple, str],
               active: set[tuple], today: date, now: datetime, rescrape_days: int,
               skip_retry_days: int = 30) -> list[tuple]:
    """(우선순위, tracse_id, cstmr_id, session) 목록. 숫자가 작을수록 먼저."""
    by_course: dict[tuple, dict[int, dict]] = defaultdict(dict)
    for (tid, cst, sess), r in rows.items():
        by_course[(tid, cst)][sess] = r

    tasks = []
    for ck, ref in courses.items():
        known = by_course.get(ck, {})
        top = max([ref.tracse_tme, *known.keys()] or [1])
        for s in range(1, top + 1):
            k = (*ck, s)
            if s in known:
                r = known[s]
                if is_live(r, today) and days_since(r.get("web_scraped_at"), now) >= rescrape_days:
                    tasks.append((0 if ck in active else 1, *k))
            elif days_since(skips.get(k), now) >= skip_retry_days:
                # 아직 없는 회차: 최근 회차부터
                tasks.append((2, *k))
        # 진행 중인 과정은 다음 회차가 생겼는지 확인
        if ck in active:
            k = (*ck, top + 1)
            if days_since(skips.get(k), now) >= 1:
                tasks.append((0, *k))
    tasks.sort(key=lambda t: (t[0], -t[3]))
    return tasks


# ---------------------------------------------------------------------------
# 실행
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--max-pages", type=int, default=int(os.getenv("MAX_PAGES", "1500")),
                   help="한 번 실행에 여는 상세 페이지 최대 수")
    p.add_argument("--max-list-pages", type=int, default=300, help="목록 페이지 최대 수")
    p.add_argument("--delay", type=float, default=float(os.getenv("CRAWL_DELAY", "1.2")),
                   help="상세 페이지 사이 대기(초)")
    p.add_argument("--rescrape-days", type=int, default=7, help="같은 회차를 다시 읽기까지 일수")
    p.add_argument("--skip-list", action="store_true", help="목록 크롤링 생략 (DB에 있는 과정만 갱신)")
    p.add_argument("--list-url", help="목록 페이지 주소 (기본: KDT 목록)")
    p.add_argument("--save-every", type=int, default=200, help="상세 페이지 N개마다 중간 저장")
    p.add_argument("--dry-run", action="store_true", help="DB에 쓰지 않음")
    p.add_argument("--inspect", metavar="DIR", help="목록·상세 페이지 원본 샘플을 DIR에 저장")
    p.add_argument("--csv", metavar="PATH", help="결과를 CSV로도 저장")
    p.add_argument("--headful", action="store_true", help="브라우저 창을 띄워서 실행 (로컬 디버깅용)")
    return p.parse_args(argv)


def run(args) -> int:
    today = datetime.now(KST).date()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    stats: dict[str, int] = defaultdict(int)

    db = SupabaseDB(os.environ.get("SUPABASE_URL", ""),
                    os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""), dry_run=args.dry_run)

    # 1) 목록 페이지 ---------------------------------------------------------
    listed: dict[tuple, CourseRef] = {}
    if not args.skip_list:
        lc = ListCrawler(url=args.list_url or LIST_URL,
                         max_pages=args.max_list_pages, headless=not args.headful,
                         dump_dir=os.path.join(args.inspect, "list") if args.inspect else None)
        try:
            listed = lc.crawl()
        except Exception:
            log.exception("목록 크롤링 실패 — DB에 있는 과정만 갱신합니다")
    stats["listed"] = len(listed)
    log.info("목록에서 찾은 과정: %d", len(listed))

    # 2) DB의 기존 과정과 합치기 ---------------------------------------------
    rows: dict[tuple, dict] = {k: {c: v.get(c) for c in COLUMNS} for k, v in db.existing_all().items()}
    skips = db.skips_all()
    courses: dict[tuple, CourseRef] = {}
    for (tid, cst, sess), r in rows.items():
        ref = courses.setdefault((tid, cst), CourseRef(tid, cst, 1, r.get("crse_tracse_se") or KDT_CODE))
        ref.tracse_tme = max(ref.tracse_tme, sess)
        ref.title = ref.title or (r.get("course_name") or "")
        ref.institution = ref.institution or (r.get("institution") or "")
    for ck, ref in listed.items():
        if ck in courses:
            cur = courses[ck]
            cur.tracse_tme = max(cur.tracse_tme, ref.tracse_tme)
            cur.title = ref.title or cur.title
            cur.institution = ref.institution or cur.institution
            cur.crse_tracse_se = ref.crse_tracse_se or cur.crse_tracse_se
        else:
            courses[ck] = ref
    if not courses:
        log.error("수집할 과정이 없습니다. 목록 크롤링 결과를 확인하세요 (--inspect).")
        report([], stats, args)
        return 2
    active = set(listed)
    log.info("전체 과정 %d (목록 %d, DB %d행)", len(courses), len(active), len(rows))

    # 3) 상세 페이지 ---------------------------------------------------------
    tasks = plan_tasks(courses, rows, skips, active, today, now, args.rescrape_days)
    log.info("상세 페이지 대상 %d개 (이번 실행 최대 %d)", len(tasks), args.max_pages)
    scraper = DetailScraper(delay=args.delay, max_pages=args.max_pages,
                            dump_dir=os.path.join(args.inspect, "detail") if args.inspect else None)

    sessions_of: dict[tuple, set] = defaultdict(set)
    for (tid, cst, sess) in rows:
        sessions_of[(tid, cst)].add(sess)
    dirty: set[tuple] = set()
    new_skips: list[tuple] = []
    queued = {t[1:] for t in tasks}
    i = 0
    while i < len(tasks) and not scraper.exhausted:
        _, tid, cst, sess = tasks[i]
        i += 1
        ck, k = (tid, cst), (tid, cst, sess)
        ref = courses[ck]
        got = scraper.fetch(tid, sess, ref.crse_tracse_se or KDT_CODE, cst)
        if not got:
            stats["detail_missing"] += 1
            new_skips.append(k)
            continue
        stats["detail_ok"] += 1

        row = rows.get(k)
        if row is None:
            # 새 회차: 같은 과정의 다른 회차에서 과정 공통값을 물려받는다
            row = {"tracse_id": tid, "trainst_cstmr_id": cst, "session": sess}
            for s2 in sessions_of[ck]:
                sib = rows[(tid, cst, s2)]
                row = merge(row, {c: sib.get(c) for c in COURSE_LEVEL if row.get(c) is None})
        row["crse_tracse_se"] = ref.crse_tracse_se or KDT_CODE
        row["institution"] = row.get("institution") or ref.institution or got.get("institution")
        row["course_name"] = ref.title or row.get("course_name") or got.get("course_name")
        row = merge(row, {c: got.get(c) for c in SESSION_FIELDS})
        row["web_scraped_at"] = now_iso
        rows[k] = row
        dirty.add(k)

        # 과정 공통값은 이 회차에 넣고, 같은 과정의 다른 회차는 빈 칸만 채움
        course_vals = {c: got[c] for c in COURSE_LEVEL if got.get(c) is not None}
        rows[k] = merge(rows[k], course_vals)
        sessions_of[ck].add(sess)
        for s2 in sessions_of[ck]:
            kk = (tid, cst, s2)
            rr = rows[kk]
            fill = {c: v for c, v in course_vals.items() if rr.get(c) is None}
            if fill:
                rows[kk] = merge(rr, fill)
                dirty.add(kk)

        # 상세 페이지가 알려준 총 회차가 더 크면 빠진 회차를 대기열에 추가
        top = got.get("max_session") or 0
        for s in range(1, top + 1):
            nk = (tid, cst, s)
            if nk not in rows and nk not in queued:
                queued.add(nk)
                tasks.append((3, tid, cst, s))

        if len(dirty) >= args.save_every:
            save(db, rows, dirty, stats)
            db.upsert_skips(new_skips, now_iso)
            new_skips.clear()

    if scraper.exhausted and i < len(tasks):
        log.info("이번 실행 한도 도달: 남은 %d개는 다음 실행에서", len(tasks) - i)
    stats["remaining"] = max(0, len(tasks) - i)

    save(db, rows, dirty, stats)
    db.upsert_skips(new_skips, now_iso)
    merged = db.merge_legacy_rows()
    log.info("시트 이전 행과 병합 %s행", merged)

    out = [r for r in rows.values() if r.get("institution") and r.get("course_name")]
    if args.csv:
        os.makedirs(os.path.dirname(os.path.abspath(args.csv)), exist_ok=True)
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(sorted(out, key=lambda r: (r.get("start_date") or ""), reverse=True))
    report(out, stats, args, pages=scraper.pages)
    return 0


def save(db: SupabaseDB, rows: dict, dirty: set, stats: dict) -> None:
    batch = []
    for k in list(dirty):
        r = rows[k]
        if not r.get("institution") or not r.get("course_name"):
            stats["skipped_no_name"] += 1
            continue
        r["source"] = r.get("source") or "crawler"
        fill_derived(r)
        batch.append(r)
    n = db.upsert(batch)
    stats["saved"] += n
    dirty.clear()
    log.info("중간 저장 %d행 (누적 %d)", n, stats["saved"])


def report(rows: list[dict], stats: dict, args, pages: int = 0) -> None:
    total = len(rows) or 1
    cover = {c: sum(1 for r in rows if r.get(c) not in (None, "")) for c in
             ("training_fee", "training_hours", "ncs_job", "ncs_level", "capacity", "applicants",
              "confirmed", "completed", "satisfaction", "evaluators", "employment_rate_6m")}
    lines = [
        f"## KDT 수집 결과 ({datetime.now(KST):%Y-%m-%d %H:%M} KST){' — dry-run' if args.dry_run else ''}",
        f"- 목록에서 찾은 과정: {stats['listed']}",
        f"- 상세 페이지: {pages}개 열람, 성공 {stats['detail_ok']}, 회차 없음 {stats['detail_missing']}, "
        f"다음 실행으로 넘김 {stats['remaining']}",
        f"- 저장: {stats['saved']}행 (이름 없어 건너뜀 {stats['skipped_no_name']})",
        f"- DB 전체 회차(이번 실행 기준): {len(rows)}",
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
    if os.environ.get("GITHUB_ACTIONS"):
        # 실행 목록·API에서 바로 보이도록 한 줄 요약을 알림으로도 남긴다
        cov = ", ".join(f"{c} {v / total * 100:.0f}%" for c, v in cover.items())
        print(f"::notice title=KDT 수집 결과::과정 {stats['listed']}개 / 상세 성공 {stats['detail_ok']}, "
              f"회차 없음 {stats['detail_missing']}, 남음 {stats['remaining']} / 저장 {stats['saved']}행 / {cov}")


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
