"""Supabase(PostgREST) 저장소. 추가 패키지 없이 requests로 REST API를 호출한다."""

from __future__ import annotations

import logging
import os
from typing import Iterator, Optional

import requests

log = logging.getLogger(__name__)

TABLE = "training_sessions"
CONFLICT_COLS = "tracse_id,trainst_cstmr_id,session"

# 수집기가 쓰는 컬럼 (id, created_at 등 DB가 관리하는 컬럼 제외)
COLUMNS = [
    "tracse_id", "trainst_cstmr_id", "crse_tracse_se", "session", "institution", "course_name",
    "training_fee", "ncs_code", "ncs_job", "ncs_level", "training_days", "training_hours",
    "hourly_fee", "start_date", "end_date", "capacity", "applicants", "confirmed",
    "completed", "satisfaction", "evaluators", "recruitment_rate", "completion_rate",
    "employment_rate_3m", "employment_rate_6m", "source", "web_scraped_at",
]


class SupabaseError(RuntimeError):
    pass


class SupabaseDB:
    def __init__(self, url: str, service_key: str, dry_run: bool = False):
        if not url or not service_key:
            raise SupabaseError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY가 비어 있습니다.")
        self.base = url.rstrip("/") + "/rest/v1"
        self.dry_run = dry_run
        self.failed_rows = 0
        self.s = requests.Session()
        self.s.headers.update({
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        })

    def _check(self, r: requests.Response) -> None:
        if r.status_code >= 400:
            raise SupabaseError(f"{r.status_code} {r.request.method} {r.url}: {r.text[:500]}")

    def select_all(self, query: str, page_size: int = 1000) -> Iterator[dict]:
        """Range 헤더로 1000행씩 끊어서 전부 읽는다."""
        start = 0
        while True:
            r = self.s.get(f"{self.base}/{TABLE}?{query}",
                           headers={"Range-Unit": "items", "Range": f"{start}-{start + page_size - 1}"},
                           timeout=60)
            self._check(r)
            rows = r.json()
            yield from rows
            if len(rows) < page_size:
                break
            start += page_size

    def existing_all(self) -> dict[tuple, dict]:
        """수집기가 저장한 모든 행을 (tracse_id, trainst_cstmr_id, session) 키로."""
        out = {}
        for row in self.select_all("select=*&tracse_id=not.is.null&order=id.asc"):
            out[(row["tracse_id"], row["trainst_cstmr_id"], int(row["session"]))] = row
        return out

    def skips_all(self) -> dict[tuple, str]:
        """상세 페이지가 없던 회차 → 마지막 확인 시각."""
        out = {}
        start = 0
        while True:
            r = self.s.get(f"{self.base}/crawl_skips?select=*",
                           headers={"Range-Unit": "items", "Range": f"{start}-{start + 999}"}, timeout=60)
            self._check(r)
            rows = r.json()
            for row in rows:
                out[(row["tracse_id"], row["trainst_cstmr_id"], int(row["session"]))] = row["checked_at"]
            if len(rows) < 1000:
                return out
            start += 1000

    def upsert_skips(self, keys: list[tuple], checked_at: str) -> None:
        if not keys or self.dry_run:
            return
        body = [{"tracse_id": k[0], "trainst_cstmr_id": k[1], "session": k[2], "checked_at": checked_at}
                for k in dict.fromkeys(keys)]   # 같은 키가 두 번 있으면 Postgres가 거부하므로 중복 제거
        try:
            r = self._post(f"{self.base}/crawl_skips?on_conflict=tracse_id,trainst_cstmr_id,session", body)
            self._check(r)
        except (SupabaseError, requests.RequestException) as e:
            log.warning("건너뛸 회차 기록 실패(무시): %s", str(e)[:300])

    def upsert(self, rows: list[dict], batch: int = 500) -> int:
        """같은 키가 있으면 갱신, 없으면 추가. 모든 행이 같은 컬럼을 갖도록 맞춘다."""
        if not rows:
            return 0
        clean = [{c: r.get(c) for c in COLUMNS} for r in rows]
        if self.dry_run:
            log.info("[dry-run] upsert %d행 생략", len(clean))
            return len(clean)
        n = 0
        for i in range(0, len(clean), batch):
            n += self._upsert_part(clean[i:i + batch])
        return n

    def _post(self, url: str, body: list) -> requests.Response:
        """일시적인 네트워크 오류는 3번까지 다시 시도."""
        import time
        for attempt in range(3):
            try:
                return self.s.post(url, json=body, timeout=120,
                                   headers={"Prefer": "resolution=merge-duplicates,return=minimal"})
            except requests.RequestException as e:
                if attempt == 2:
                    raise
                log.warning("Supabase 요청 실패, 재시도: %s", e)
                time.sleep(5 * (attempt + 1))
        raise AssertionError("unreachable")

    def _upsert_part(self, part: list[dict]) -> int:
        """한 묶음 저장. 실패하면 반씩 나눠 다시 시도해서 문제 있는 행만 건너뛴다."""
        r = self._post(f"{self.base}/{TABLE}?on_conflict={CONFLICT_COLS}", part)
        if r.status_code < 400:
            return len(part)
        if r.status_code >= 500 and len(part) > 1 and "affect row a second time" not in r.text:
            log.warning("Supabase 서버 오류 %s, 나눠서 재시도", r.status_code)
        if len(part) == 1:
            row = part[0]
            msg = f"저장 실패로 건너뜀: {row.get('tracse_id')} {row.get('session')}회차 — {r.status_code} {r.text[:300]}"
            log.warning(msg)
            if os.environ.get("GITHUB_ACTIONS"):
                print(f"::warning title=저장 실패 행::{msg}")
            self.failed_rows += 1
            return 0
        mid = len(part) // 2
        return self._upsert_part(part[:mid]) + self._upsert_part(part[mid:])

    def insert(self, rows: list[dict], batch: int = 500) -> int:
        """중복 검사 없이 추가 (시트 이전용)."""
        if not rows:
            return 0
        clean = [{c: r.get(c) for c in COLUMNS} for r in rows]
        if self.dry_run:
            log.info("[dry-run] insert %d행 생략", len(clean))
            return len(clean)
        for i in range(0, len(clean), batch):
            r = self.s.post(f"{self.base}/{TABLE}", json=clean[i:i + batch],
                            headers={"Prefer": "return=minimal"}, timeout=120)
            self._check(r)
        return len(clean)

    def count(self, query: str = "select=id") -> int:
        r = self.s.get(f"{self.base}/{TABLE}?{query}",
                       headers={"Prefer": "count=exact", "Range": "0-0"}, timeout=60)
        self._check(r)
        cr = r.headers.get("Content-Range", "*/0")
        return int(cr.split("/")[-1]) if cr.split("/")[-1].isdigit() else 0

    def merge_legacy_rows(self) -> Optional[int]:
        if self.dry_run:
            return None
        r = self.s.post(f"{self.base}/rpc/merge_legacy_rows", json={}, timeout=120)
        self._check(r)
        return r.json()
