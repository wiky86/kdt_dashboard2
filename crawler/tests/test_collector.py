from datetime import date, datetime, timedelta, timezone

from crawler import main as M
from crawler.detail_scraper import html_to_text, parse_detail_text, parse_names
from crawler.list_crawler import CourseRef, parse_card_text, parse_course_ref
from crawler.migrate_sheet import sheet_row_to_db


# ---------------------------------------------------------------------------
# 목록 페이지
# ---------------------------------------------------------------------------

def test_parse_course_ref_from_function_call():
    r = parse_course_ref("javascript:fnTrnnCrsDtl('AIG20233000936060','2','C0104','500020039555','N');")
    assert (r.tracse_id, r.tracse_tme, r.crse_tracse_se, r.trainst_cstmr_id) == \
        ("AIG20233000936060", 2, "C0104", "500020039555")


def test_parse_course_ref_from_url():
    r = parse_course_ref("https://www.work24.go.kr/hr/a/a/3100/selectTracseDetl.do?tracseId=AIG20233000936060"
                         "&tracseTme=2&crseTracseSe=C0061&trainstCstmrId=500020039555")
    assert r.tracse_id == "AIG20233000936060" and r.tracse_tme == 2 and r.crse_tracse_se == "C0061"


def test_parse_course_ref_rejects_unrelated():
    assert parse_course_ref("fnCompare('abc', '12')") is None
    assert parse_course_ref("") is None


def test_parse_card_text():
    card = "5년인증 우수훈련기관\n패스트캠퍼스천호학원\n자바 개발자 양성과정\n모집중\n7,745,400 원\n2026-10-13 ~ 2027-03-20 (3회차)"
    got = parse_card_text(card, "자바 개발자 양성과정")
    assert got == {"session": 3, "institution": "패스트캠퍼스천호학원"}


# ---------------------------------------------------------------------------
# 상세 페이지
# ---------------------------------------------------------------------------

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
NCS직종 훈련기관 취업률 58%
6개월 취업률
53.3%
"""


def test_parse_detail_text():
    got = parse_detail_text(DETAIL_TEXT)
    assert got["start_date"] == "2024-04-23" and got["end_date"] == "2024-10-11" and got["session"] == 2
    assert got["max_session"] == 2
    assert got["confirmed"] == 16 and got["applicants"] == 16 and got["capacity"] == 25
    assert got["training_fee"] == 7745400
    assert got["satisfaction"] == 4.9 and got["evaluators"] == 15
    assert got["training_days"] == 113 and got["training_hours"] == 900
    assert got["ncs_job"] == "응용SW엔지니어링" and got["ncs_code"] == "20010202" and got["ncs_level"] == 5
    assert got["employment_rate_6m"] == 53.3          # 기관 취업률(58%)이 아니라 6개월 취업률


def test_parse_detail_ignores_institution_rate_and_na():
    got = parse_detail_text("2025-01-06 ~ 2025-06-20 (3회차)\n취업률\n해당없음\nNCS직종 훈련기관 취업률 58%")
    assert "employment_rate_6m" not in got


def test_parse_detail_from_html_table():
    html = """<html><head><meta property="og:title" content="[멀티잇]데이터 분석 서비스 개발자 취업캠프"></head>
    <body><table><tr><th>훈련기간</th><td>2023.02.27 ~ 2023.07.14 (8회차)</td></tr>
    <tr><th>만족도</th><td>3.9점 (평가인원 17명)</td></tr>
    <tr><th>NCS</th><td>빅데이터분석 (20010602) / 6수준</td></tr>
    <tr><th>훈련시간</th><td>110일, 총 880시간</td></tr>
    <tr><th>수료인원</th><td>17명</td></tr></table><script>var x=1;</script></body></html>"""
    got = parse_detail_text(html_to_text(html))
    assert got["start_date"] == "2023-02-27" and got["session"] == 8
    assert got["satisfaction"] == 3.9 and got["evaluators"] == 17
    assert got["ncs_job"] == "빅데이터분석" and got["ncs_level"] == 6
    assert got["training_hours"] == 880 and got["completed"] == 17
    assert parse_names(html)["course_name"] == "[멀티잇]데이터 분석 서비스 개발자 취업캠프"


def test_satisfaction_zero_is_empty():
    got = parse_detail_text("2026-10-13 ~ 2027-03-20 (3회차)\n만족도 0.0 (0명)")
    assert "satisfaction" not in got and got["evaluators"] == 0


# ---------------------------------------------------------------------------
# 계산·병합
# ---------------------------------------------------------------------------

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


def test_plan_tasks_priorities():
    today = date(2026, 10, 13)
    now = datetime(2026, 10, 13, tzinfo=timezone.utc)
    ck = ("AIG1", "500")
    courses = {ck: CourseRef("AIG1", "500", 3), ("AIG2", "600"): CourseRef("AIG2", "600", 1)}
    rows = {
        ("AIG1", "500", 1): {"end_date": "2023-01-01", "confirmed": 20, "satisfaction": 4.1,
                             "web_scraped_at": "2026-01-01T00:00:00+00:00"},   # 끝난 지 오래 → 제외
        ("AIG1", "500", 2): {"end_date": "2026-08-01", "web_scraped_at": "2026-10-01T00:00:00+00:00"},  # 진행 중·오래됨
        ("AIG2", "600", 1): {"end_date": "2026-12-01", "web_scraped_at": "2026-10-12T00:00:00+00:00"},  # 어제 읽음
    }
    tasks = M.plan_tasks(courses, rows, {}, active={ck}, today=today, now=now, rescrape_days=7)
    keys = [t[1:] for t in tasks]
    assert ("AIG1", "500", 1) not in keys
    assert ("AIG2", "600", 1) not in keys
    assert keys[:2] == [("AIG1", "500", 4), ("AIG1", "500", 2)]   # 다음 회차 확인, 진행 중 회차
    assert ("AIG1", "500", 3) in keys                              # 아직 없는 회차


# ---------------------------------------------------------------------------
# 전체 흐름 (가짜 목록 / 상세 / DB)
# ---------------------------------------------------------------------------

PAGES = {
    1: "2023-10-30 ~ 2024-04-05 (1회차)\n수강확정 22명\n정원 25명\n수료인원 18명\n만족도 4.6 (12명)\n6개월 취업률 61.1%",
    2: DETAIL_TEXT,
}


class FakeList:
    def __init__(self, *a, **k):
        pass

    def crawl(self):
        return {("AIG20233000936060", "500020039555"):
                CourseRef("AIG20233000936060", "500020039555", 2, "C0104",
                          title="(산대특) Open API 기반 공공 빅데이터 자바 개발자 양성과정",
                          institution="패스트캠퍼스천호학원")}


class FakeScraper:
    def __init__(self, *a, **k):
        self.pages = 0

    @property
    def exhausted(self):
        return False

    def fetch(self, tid, sess, se, cst):
        self.pages += 1
        if sess not in PAGES:
            return None
        return parse_detail_text(PAGES[sess])


class FakeDB:
    saved: dict = {}
    skips: list = []

    def __init__(self, *a, **k):
        FakeDB.saved, FakeDB.skips = {}, []

    def existing_all(self):
        return {}

    def skips_all(self):
        return {}

    def upsert(self, rows):
        for r in rows:
            FakeDB.saved[r["session"]] = dict(r)
        return len(rows)

    def upsert_skips(self, keys, ts):
        FakeDB.skips += keys

    def merge_legacy_rows(self):
        return 0


def test_run_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setattr(M, "ListCrawler", FakeList)
    monkeypatch.setattr(M, "DetailScraper", FakeScraper)
    monkeypatch.setattr(M, "SupabaseDB", FakeDB)
    assert M.run(M.parse_args(["--csv", str(tmp_path / "out.csv")])) == 0

    by = FakeDB.saved
    assert set(by) == {1, 2}
    assert ("AIG20233000936060", "500020039555", 3) in FakeDB.skips   # 다음 회차는 아직 없음
    r1, r2 = by[1], by[2]
    assert r1["institution"] == "패스트캠퍼스천호학원"
    assert r1["training_hours"] == 900 and r1["ncs_level"] == 5        # 2회차 페이지의 과정 공통값 상속
    assert r1["recruitment_rate"] == 88.0 and r1["completion_rate"] == 81.8
    assert r1["employment_rate_6m"] == 61.1 and r1["evaluators"] == 12
    assert r2["hourly_fee"] == round(7745400 / 900) and r2["recruitment_rate"] == 64.0
    assert r2["crse_tracse_se"] == "C0104" and r2["source"] == "crawler"
    assert (tmp_path / "out.csv").exists()
