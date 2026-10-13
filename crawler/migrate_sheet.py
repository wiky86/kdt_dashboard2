"""구글 시트(시트4)의 기존 데이터를 Supabase로 한 번 옮긴다.

    python -m crawler.migrate_sheet            # 옮기기
    python -m crawler.migrate_sheet --dry-run  # 읽기만

옮긴 행은 source='sheet_migration', tracse_id=null 로 들어간다.
이후 수집기가 같은 과정·회차·개강일을 수집하면 merge_legacy_rows()가
옛 행의 값을 새 행으로 합치고 옛 행은 지운다.

환경변수: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
          (선택) GOOGLE_SHEET_ID, GOOGLE_API_KEY, GOOGLE_SHEET_RANGE
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from urllib.parse import quote

import requests

from .db import SupabaseDB
from .main import to_date, to_float, to_int

log = logging.getLogger("migrate")

# 기존 대시보드 코드에 들어 있던 값 (공개 읽기 전용 키)
DEFAULT_SHEET_ID = "1upfeAj22FEoYAgtSckJLQJ-Tg6FWFxU1ea3IdjfhGzM"
DEFAULT_RANGE = "시트4!A:Q"


def fetch_sheet(sheet_id: str, rng: str, api_key: str) -> list[list[str]]:
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{quote(rng)}"
    r = requests.get(url, params={"key": api_key}, timeout=60)
    r.raise_for_status()
    return r.json().get("values", [])


def sheet_row_to_db(row: list[str]) -> dict | None:
    row = row + [""] * (17 - len(row))
    inst, course = row[0].strip(), row[1].strip()
    session = to_int(row[8])
    if not inst or not course or session is None:
        return None
    return {
        "tracse_id": None,
        "trainst_cstmr_id": None,
        "session": session,
        "institution": inst,
        "course_name": course,
        "training_fee": to_int(row[2]),
        "ncs_job": row[3].strip() or None,
        "ncs_level": to_int(row[4]),
        "training_days": to_int(row[5]),
        "training_hours": to_int(row[6]),
        "hourly_fee": to_int(row[7]),
        "start_date": to_date(row[9]),
        "capacity": to_int(row[10]),
        "confirmed": to_int(row[11]),
        "satisfaction": to_float(row[12]) or None,
        "evaluators": to_int(row[13]),
        "recruitment_rate": to_float(row[14]),
        "completion_rate": to_float(row[15]),
        "employment_rate_6m": to_float(row[16]),
        "source": "sheet_migration",
    }


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="이미 옮긴 행이 있어도 다시 추가")
    args = p.parse_args(argv)

    sheet_id = os.getenv("GOOGLE_SHEET_ID", DEFAULT_SHEET_ID)
    rng = os.getenv("GOOGLE_SHEET_RANGE", DEFAULT_RANGE)
    api_key = os.getenv("GOOGLE_API_KEY", "AIzaSyD-zp3ID1MdWeMMQoSMTzHsGcvXZVnNe4k")

    values = fetch_sheet(sheet_id, rng, api_key)
    if len(values) < 2:
        log.error("시트에 데이터가 없습니다.")
        return 1
    rows = [r for r in (sheet_row_to_db(v) for v in values[1:]) if r]
    log.info("시트 %d행 중 %d행 변환", len(values) - 1, len(rows))

    db = SupabaseDB(os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
                    dry_run=args.dry_run)
    if not args.dry_run and not args.force:
        already = db.count("select=id&source=eq.sheet_migration")
        if already:
            log.error("이미 옮긴 행이 %d개 있습니다. 다시 하려면 --force", already)
            return 1
    n = db.insert(rows)
    merged = db.merge_legacy_rows()
    log.info("추가 %d행, 수집 데이터와 병합 %s행", n, merged)
    return 0


if __name__ == "__main__":
    sys.exit(main())
