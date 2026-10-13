"""Supabase(PostgREST) 저장소. 추가 패키지 없이 requests로 REST API를 호출한다."""

from __future__ import annotations

import logging
from typing import Iterable, Iterator, Optional

import requests

log = logging.getLogger(__name__)

TABLE = "training_sessions"
CONFLICT_COLS = "tracse_id,trainst_cstmr_id,session"

# 수집기가 쓰는 컬럼 (id, created_at 등 DB가 관리하는 컬럼 제외)
COLUMNS = [
    "tracse_id", "trainst_cstmr_id", "session", "institution", "course_name",
    "training_fee", "ncs_code", "ncs_job", "ncs_level", "training_days", "training_hours",
    "hourly_fee", "start_date", "end_date", "capacity", "applicants", "confirmed",
    "completed", "satisfaction", "evaluators", "recruitment_rate", "completion_rate",
    "employment_rate_3m", "employment_rate_6m", "source", "api_synced_at", "web_scraped_at",
]


class SupabaseError(RuntimeError):
    pass


class SupabaseDB:
    def __init__(self, url: str, service_key: str, dry_run: bool = False):
        if not url or not service_key:
            raise SupabaseError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY가 비어 있습니다.")
        self.base = url.rstrip("/") + "/rest/v1"
        self.dry_run = dry_run
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

    def existing_since(self, start_date: str) -> dict[tuple, dict]:
        """개강일이 start_date 이후인 수집 행을 (tracse_id, trainst_cstmr_id, session) 키로."""
        out = {}
        q = f"select=*&tracse_id=not.is.null&start_date=gte.{start_date}"
        for row in self.select_all(q):
            out[(row["tracse_id"], row["trainst_cstmr_id"], int(row["session"]))] = row
        return out

    def existing_for_courses(self, tracse_ids: Iterable[str]) -> dict[tuple, dict]:
        """특정 과정들의 기존 행 (개강일 범위 밖의 옛 회차 포함)."""
        out = {}
        ids = sorted(set(tracse_ids))
        for i in range(0, len(ids), 100):
            chunk = ",".join(f'"{x}"' for x in ids[i:i + 100])
            for row in self.select_all(f"select=*&tracse_id=in.({chunk})"):
                out[(row["tracse_id"], row["trainst_cstmr_id"], int(row["session"]))] = row
        return out

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
            part = clean[i:i + batch]
            r = self.s.post(
                f"{self.base}/{TABLE}?on_conflict={CONFLICT_COLS}",
                json=part,
                headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
                timeout=120,
            )
            self._check(r)
            n += len(part)
        return n

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
