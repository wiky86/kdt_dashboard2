"""고용24 Open-API (국민내일배움카드 훈련과정) 클라이언트.

- 310L01 목록      : 회차 단위 목록. 공식 문서로 필드가 확인된 API라 기본 데이터는 여기서 받는다.
- 310L02 과정/기관정보 : 훈련시간·훈련일수·NCS 등 과정 단위 정보
- 310L03 훈련일정    : 회차별 수강인원·수료인원·취업률

310L02/310L03은 응답 필드명이 문서에서 확인되지 않아, 후보 이름 여러 개를
대소문자 무시로 찾는다(pick). 실제 응답이 다르면 `--inspect`로 원본 JSON을
저장해 FIELD 후보만 고치면 된다.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any, Iterable, Iterator, Optional

import requests

log = logging.getLogger(__name__)

BASE = "https://www.work24.go.kr/cm/openApi/call/hr"
URL_LIST = f"{BASE}/callOpenApiSvcInfo310L01.do"
URL_INFO = f"{BASE}/callOpenApiSvcInfo310L02.do"
URL_SCHEDULE = f"{BASE}/callOpenApiSvcInfo310L03.do"

KDT_CODE = "C0104"  # 훈련유형: K-디지털 트레이닝

# 필드 후보 (앞에 있을수록 우선)
FIELD = {
    # 310L01 목록 (공식 문서 확인)
    "tracse_id":        ["TRPR_ID", "trprId"],
    "session":          ["TRPR_DEGR", "trprDegr"],
    "trainst_cstmr_id": ["TRAINST_CST_ID", "trainstCstId", "instIno", "INST_INO"],
    "course_name":      ["TITLE", "trprNm"],
    "institution":      ["SUB_TITLE", "inoNm", "instNm"],
    "training_fee":     ["REAL_MAN", "realMan", "totTrco", "perTrco"],
    "capacity":         ["YARD_MAN", "yardMan", "totFxnum"],
    "applicants":       ["REG_COURSE_MAN", "regCourseMan", "totParMks"],
    "satisfaction":     ["STDG_SCOR", "stdgScor"],
    "employment_rate_3m": ["EI_EMPL_RATE3", "eiEmplRate3"],
    "employment_rate_6m": ["EI_EMPL_RATE6", "eiEmplRate6"],
    "start_date":       ["TRA_START_DATE", "traStartDate", "trStaDt"],
    "end_date":         ["TRA_END_DATE", "traEndDate", "trEndDt"],
    "ncs_code":         ["NCS_CD", "ncsCd"],
    # 310L02 과정/기관정보 (후보)
    "training_hours":   ["trtm", "TRTM", "totTraingTime", "trTime", "totTrtm"],
    "training_days":    ["trDcnt", "TR_DCNT", "totTraingDyct", "trDayCnt"],
    "ncs_job":          ["ncsNm", "NCS_NM"],
    "ncs_level":        ["ncsLvl", "ncsLevel", "NCS_LVL"],
    # 310L03 훈련일정 (후보)
    "confirmed":        ["totTrpCnt", "TOT_TRP_CNT", "trneeCnt"],
    "completed":        ["finiCnt", "FINI_CNT", "totFiniCnt"],
}


class ApiError(RuntimeError):
    pass


def pick(item: dict, name: str) -> Any:
    """FIELD 후보 중 처음으로 값이 있는 것을 돌려준다 (대소문자·밑줄 무시)."""
    if not isinstance(item, dict):
        return None
    norm = {k.lower().replace("_", ""): v for k, v in item.items()}
    for cand in FIELD[name]:
        v = norm.get(cand.lower().replace("_", ""))
        if v not in (None, "", "null"):
            return v
    return None


def find_records(payload: Any) -> list[dict]:
    """응답 JSON 안에서 레코드 목록(dict의 list)을 찾는다. 키 이름이 달라도 동작."""
    if isinstance(payload, list):
        if payload and all(isinstance(x, dict) for x in payload):
            return payload
        out: list[dict] = []
        for x in payload:
            out.extend(find_records(x))
        return out
    if isinstance(payload, dict):
        for key in ("srchList", "scn_list", "scnList", "list"):
            if key in payload:
                v = payload[key]
                if isinstance(v, dict):
                    # {"scn_list": {"scn_list": [...]}} 또는 단일 레코드
                    inner = find_records(v)
                    return inner if inner else [v]
                return find_records(v)
        best: list[dict] = []
        for v in payload.values():
            if isinstance(v, (list, dict)):
                r = find_records(v)
                if len(r) > len(best):
                    best = r
        return best
    return []


def find_dict(payload: Any, keys: Iterable[str]) -> Optional[dict]:
    """응답 안에서 주어진 키 중 하나를 가진 dict를 찾는다 (310L02 inst_base_info 등)."""
    keys_l = {k.lower().replace("_", "") for k in keys}
    if isinstance(payload, dict):
        if keys_l & {k.lower().replace("_", "") for k in payload}:
            return payload
        for v in payload.values():
            r = find_dict(v, keys)
            if r:
                return r
    elif isinstance(payload, list):
        for v in payload:
            r = find_dict(v, keys)
            if r:
                return r
    return None


class Work24Api:
    def __init__(self, auth_key: str, delay: float = 0.3, max_calls: int = 5000,
                 inspect_dir: Optional[str] = None):
        if not auth_key:
            raise ApiError("WORK24_API_KEY가 비어 있습니다.")
        self.auth_key = auth_key
        self.delay = delay
        self.max_calls = max_calls
        self.calls = 0
        self.inspect_dir = inspect_dir
        self._inspected: set[str] = set()
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "Mozilla/5.0 (kdt-dashboard collector)"

    # ------------------------------------------------------------------ core
    def _get(self, url: str, params: dict) -> Any:
        if self.calls >= self.max_calls:
            raise ApiError(f"API 호출 한도({self.max_calls}) 도달")
        params = {"authKey": self.auth_key, "returnType": "JSON", **params}
        last_exc: Optional[Exception] = None
        for attempt in range(4):
            try:
                self.calls += 1
                r = self.s.get(url, params=params, timeout=30)
                r.raise_for_status()
                time.sleep(self.delay)
                text = r.text.strip()
                if not text:
                    return {}
                if text.startswith("<"):
                    # 인증 오류 등은 XML/HTML로 오는 경우가 있다
                    raise ApiError(f"JSON이 아닌 응답: {text[:300]}")
                data = r.json()
                self._maybe_inspect(url, params, data)
                return data
            except (requests.RequestException, ValueError) as e:
                last_exc = e
                wait = 2 ** attempt * 3
                log.warning("API 호출 실패(%s), %ss 후 재시도: %s", url.rsplit("/", 1)[-1], wait, e)
                time.sleep(wait)
        raise ApiError(f"API 호출 실패: {last_exc}")

    def _maybe_inspect(self, url: str, params: dict, data: Any) -> None:
        """--inspect: API별로 첫 응답 원본을 저장 (인증키는 빼고)."""
        if not self.inspect_dir:
            return
        name = url.rsplit("/", 1)[-1].replace(".do", "")
        if name in self._inspected:
            return
        self._inspected.add(name)
        import json, os
        os.makedirs(self.inspect_dir, exist_ok=True)
        safe = {k: v for k, v in params.items() if k != "authKey"}
        with open(os.path.join(self.inspect_dir, f"{name}.json"), "w", encoding="utf-8") as f:
            json.dump({"params": safe, "response": data}, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ 310L01
    def list_sessions(self, start: date, end: date, crse_tracse_se: str = KDT_CODE,
                      page_size: int = 100, chunk_days: int = 31) -> Iterator[dict]:
        """개강일이 [start, end]인 회차 목록. 기간을 쪼개 페이지 한도(1000)를 피한다."""
        cur = start
        while cur <= end:
            chunk_end = min(cur + timedelta(days=chunk_days - 1), end)
            page = 1
            total = None
            while True:
                data = self._get(URL_LIST, {
                    "outType": "1",
                    "pageNum": str(page),
                    "pageSize": str(page_size),
                    "srchTraStDt": cur.strftime("%Y%m%d"),
                    "srchTraEndDt": chunk_end.strftime("%Y%m%d"),
                    "crseTracseSe": crse_tracse_se,
                    "sort": "ASC",
                    "sortCol": "2",
                })
                if total is None and isinstance(data, dict):
                    try:
                        total = int(str(data.get("scn_cnt") or data.get("scnCnt") or 0))
                    except ValueError:
                        total = 0
                recs = find_records(data)
                for r in recs:
                    yield r
                if len(recs) < page_size or page >= 1000 or (total and page * page_size >= total):
                    break
                page += 1
            log.info("목록 %s ~ %s: %s건", cur, chunk_end, total)
            cur = chunk_end + timedelta(days=1)

    # ------------------------------------------------------------------ 310L02
    def course_info(self, tracse_id: str, session: int | str, trainst_id: str) -> dict:
        data = self._get(URL_INFO, {
            "outType": "2",
            "srchTrprId": tracse_id,
            "srchTrprDegr": str(session),
            "srchTorgId": trainst_id,
        })
        keys = FIELD["training_hours"] + FIELD["training_days"] + FIELD["ncs_job"]
        return find_dict(data, keys) or {}

    # ------------------------------------------------------------------ 310L03
    def schedule(self, tracse_id: str, trainst_id: str) -> list[dict]:
        """과정의 회차별 일정·실적. 회차 번호를 빼고 요청해 전체 회차를 받는다."""
        data = self._get(URL_SCHEDULE, {
            "outType": "2",
            "srchTrprId": tracse_id,
            "srchTorgId": trainst_id,
        })
        return find_records(data)
