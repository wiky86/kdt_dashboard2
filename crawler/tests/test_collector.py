from datetime import date, timedelta

import pytest

from crawler import main as M
from crawler.detail_scraper import parse_detail_text, html_to_text
from crawler.migrate_sheet import sheet_row_to_db
from crawler.work24_api import find_records, find_dict, pick


L01_ITEM = {
    "TRPR_ID": "AIG20233000936060", "TRPR_DEGR": "2", "TRAINST_CST_ID": "500020039555",
    "TITLE": "(산대특) Open API 기반 공공 빅데이터 자바 개발자 양성과정",
    "SUB_TITLE": "패스트캠퍼스천호학원", "REAL_MAN": "7,745,400", "YARD_MAN": "25",
    "REG_COURSE_MAN": "16", "STDG_SCOR": "4.9", "EI_EMPL_RATE3": "A", "EI_EMPL_RATE6": "53.3",
    "TRA_START_DATE": "2024-04-23", "TRA_END_DATE": "20241011", "NCS_CD": "20010202",
}


def test_from_api_list_item():
    r = M.from_api(L01_ITEM)
    assert r["tracse_id"] == "AIG20233000936060"
    assert r["session"] == 2
    assert r["training_fee"] == 7745400
    assert r["capacity"] == 25 and r["applicants"] == 16
    assert r["satisfaction"] == 4.9
    assert "employment_rate_3m" not in r          # 코드값 'A'는 버림
    assert r["employment_rate_6m"] == 53.3
    assert r["start_date"] == "2024-04-23" and r["end_date"] == "2024-10-11"


def test_pick_is_case_and_underscore_insensitive():
    assert pick({"tot_trp_cnt": "20"}, "confirmed") == "20"
    assert pick({"TOTTRPCNT": "21"}, "confirmed") == "21"
    assert pick({"x": 1}, "confirmed") is None


@pytest.mark.parametrize("payload", [
    {"scn_cnt": 2, "srchList": [{"a": 1}, {"a": 2}]},
    {"scn_list": [{"a": 1}, {"a": 2}]},
    {"HRDNet": {"scn_list": {"scn_list": [{"a": 1}, {"a": 2}]}}},
    {"returnJSON": {"data": [{"a": 1}, {"a": 2}], "meta": {"x": 1}}},
])
def test_find_records_shapes(payload):
    assert len(find_records(payload)) == 2


def test_find_dict_nested():
    payload = {"inst_base_info": {"trtm": "900", "trDcnt": "113", "ncsNm": "응용SW엔지니어링"}, "x": []}
    d = find_dict(payload, ["trtm"])
    r = M.from_api(d)
    assert r["training_hours"] == 900 and r["training_days"] == 113 and r["ncs_job"] == "응용SW엔지니어링"


DETAIL_TEXT = """
(산대특) Open API 기반 공공 빅데이터 자바 개발자 양성과정
패스트캠퍼스천호학원
수강확정
16명
수강신청
16명
정원
25명
훈련비
7,745,400원
만족도
4.9
(15명)
훈련기간
2024-04-23 ~ 2024-10-11 (2회차)
113일, 총900시간
실시회차 2/2
NCS 직종
응용SW엔지니어링(20010202)
5수준
"""


def test_parse_detail_text():
    got = parse_detail_text(DETAIL_TEXT)
    assert got["confirmed"] == 16
    assert got["capacity"] == 25
    assert got["satisfaction"] == 4.9 and got["evaluators"] == 15
    assert got["training_days"] == 113 and got["training_hours"] == 900
    assert got["ncs_job"] == "응용SW엔지니어링" and got["ncs_code"] == "20010202"
    assert got["ncs_level"] == 5


def test_parse_detail_from_html_table():
    html = """<html><body><table><tr><th>만족도</th><td>4.5점 (평가인원 13명)</td></tr>
    <tr><th>NCS</th><td>빅데이터분석 (20010602) / 6수준</td></tr>
    <tr><th>훈련시간</th><td>110일, 총 880시간</td></tr></table><script>var x=1;</script></body></html>"""
    got = parse_detail_text(html_to_text(html))
    assert got["satisfaction"] == 4.5 and got["evaluators"] == 13
    assert got["ncs_job"] == "빅데이터분석" and got["ncs_level"] == 6
    assert got["training_hours"] == 880


def test_derived_matches_existing_sheet_format():
    r = {"training_fee": 15245120, "training_hours": 880, "capacity": 24, "confirmed": 19, "completed": 17}
    M.fill_derived(r)
    assert r["hourly_fee"] == 17324          # 시트 값과 동일
    assert r["recruitment_rate"] == 79.2     # 시트 값 79.2%
    assert r["completion_rate"] == 89.5      # 시트 값 89.5%


def test_merge_never_erases():
    assert M.merge({"a": 1, "b": 2}, {"a": None, "b": 3, "c": ""}) == {"a": 1, "b": 3}


def test_sheet_row_to_db():
    row = ["멀티캠퍼스", "[멀티잇]데이터 분석", "15245120", "빅데이터분석", "6", "110", "880", "17324",
           "8", "2023-02-27", "24", "19", "3.9", "17", "79.2%", "89.5%", "53.3"]
    r = sheet_row_to_db(row)
    assert r["session"] == 8 and r["start_date"] == "2023-02-27"
    assert r["recruitment_rate"] == 79.2 and r["employment_rate_6m"] == 53.3
    assert r["tracse_id"] is None and r["source"] == "sheet_migration"


# ---------------------------------------------------------------------------
# 전체 흐름 (가짜 API / DB / 크롤러)
# ---------------------------------------------------------------------------

class FakeApi:
    calls = 0

    def __init__(self, *a, **k):
        pass

    def list_sessions(self, start, end, code):
        yield dict(L01_ITEM)
        yield dict(L01_ITEM, TRPR_DEGR="3", TRA_START_DATE="2025-01-06", TRA_END_DATE="20250620",
                   REG_COURSE_MAN="20", STDG_SCOR="0", EI_EMPL_RATE6="B")

    def course_info(self, tid, sess, cst):
        return {"trtm": "900", "trDcnt": "113", "ncsNm": "응용SW엔지니어링"}

    def schedule(self, tid, cst):
        return [
            {"trprDegr": "1", "trStaDt": "20231030", "trEndDt": "20240405", "totFxnum": "25",
             "totTrpCnt": "22", "finiCnt": "18", "eiEmplRate6": "61.1"},
            {"trprDegr": "2", "totTrpCnt": "16", "finiCnt": "14"},
        ]


class FakeDB:
    saved = []

    def __init__(self, *a, **k):
        pass

    def existing_for_courses(self, ids):
        return {}

    def upsert(self, rows):
        FakeDB.saved = rows
        return len(rows)

    def merge_legacy_rows(self):
        return 0


class FakeScraper:
    def __init__(self, *a, **k):
        self.n = 0

    @property
    def exhausted(self):
        return False

    def fetch(self, tid, sess, code, cst):
        self.n += 1
        return {"ncs_level": 5, "evaluators": 15 if sess == 2 else 10, "confirmed": 99}


def test_run_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setattr(M, "Work24Api", FakeApi)
    monkeypatch.setattr(M, "SupabaseDB", FakeDB)
    monkeypatch.setattr(M, "DetailScraper", FakeScraper)
    args = M.parse_args(["--csv", str(tmp_path / "out.csv")])
    assert M.run(args) == 0

    by = {r["session"]: r for r in FakeDB.saved}
    assert set(by) == {1, 2, 3}                       # 1회차는 일정 API로 추가됨
    r2 = by[2]
    assert r2["confirmed"] == 16                       # API 값이 크롤링 값(99)보다 우선
    assert r2["completed"] == 14 and r2["completion_rate"] == 87.5
    assert r2["training_hours"] == 900 and r2["hourly_fee"] == round(7745400 / 900)
    assert r2["ncs_level"] == 5 and r2["evaluators"] == 15
    r1 = by[1]
    assert r1["institution"] == "패스트캠퍼스천호학원"  # 과정 공통값 상속
    assert r1["employment_rate_6m"] == 61.1 and r1["recruitment_rate"] == 88.0
    assert by[3].get("satisfaction") is None          # 만족도 0점(평가 전)은 빈 값
    assert (tmp_path / "out.csv").exists()
