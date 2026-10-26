"""고용24 훈련과정 상세 페이지(회차별) 크롤러.

상세 페이지는 일반 GET 요청으로도 내용이 오므로 브라우저 없이 requests로 읽는다.
화면의 CSS 클래스 대신 '보이는 텍스트'의 라벨+값을 정규식으로 읽어서,
디자인이 조금 바뀌어도 버티게 했다. 못 읽은 값은 결과에 넣지 않고,
수집기는 기존 DB 값을 빈 값으로 덮어쓰지 않는다.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Optional

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

DETAIL_URL = "https://www.work24.go.kr/hr/a/a/3100/selectTracseDetl.do"


def detail_url(tracse_id: str, session: int | str, crse_tracse_se: str, trainst_id: str) -> str:
    return (f"{DETAIL_URL}?tracseId={tracse_id}&tracseTme={session}"
            f"&crseTracseSe={crse_tracse_se}&trainstCstmrId={trainst_id}")


def _norm(text: str) -> str:
    text = text.replace("\xa0", " ").replace("​", "")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip()


def _int(s: Optional[str]) -> Optional[int]:
    if s is None:
        return None
    d = re.sub(r"[^\d]", "", s)
    return int(d) if d else None


def _rate(s: Optional[str]) -> Optional[float]:
    """'53.3' → 53.3. 숫자가 아니거나 0~100 밖이면 None (잘못 읽은 값이 저장되지 않게)."""
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return v if 0 <= v <= 100 else None


def _search(patterns: list[str], text: str) -> Optional[re.Match]:
    for p in patterns:
        m = re.search(p, text, re.S)
        if m:
            return m
    return None


def _date(y: str, m: str, d: str) -> str:
    return f"{y}-{int(m):02d}-{int(d):02d}"


# 라벨과 값 사이에 줄바꿈·콜론·공백이 섞여도 되도록 최대 30자까지 허용
GAP = r"[\s:：]{0,30}"
DATE = r"(\d{4})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{1,2})"


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return _norm(soup.get_text("\n"))


def parse_names(html: str) -> dict:
    """과정명·기관명 보조 추출 (목록/DB에 이름이 없을 때만 쓰임)."""
    soup = BeautifulSoup(html, "html.parser")
    out: dict = {}
    og = soup.find("meta", attrs={"property": "og:title"})
    cands = []
    if og and og.get("content"):
        cands.append(og["content"])
    for tag in soup.find_all(["h2", "h3", "h4", "strong"], limit=40):
        t = _norm(tag.get_text(" "))
        if 6 <= len(t) <= 120 and ("과정" in t or "양성" in t or "개발" in t or "]" in t):
            cands.append(t)
    junk = re.compile(r"고용24|훈련과정\s*(상세|정보)|검색|로그인|메뉴")
    for c in cands:
        if not junk.search(c):
            out["course_name"] = c.strip()
            break
    return out


def _set(out: dict, key: str, value) -> None:
    if value is not None:
        out[key] = value


def parse_detail_text(text: str) -> dict:
    """상세 페이지 텍스트 → 값 dict (못 찾은 키는 넣지 않음)."""
    t = _norm(text)
    out: dict = {}

    # 훈련기간 + 회차: "2024-04-23 ~ 2024-10-11 (2회차)"
    m = re.search(DATE + r"\s*~\s*" + DATE + r"\s*\(?\s*(\d{1,4})\s*회차", t)
    if m:
        out["start_date"] = _date(*m.group(1, 2, 3))
        out["end_date"] = _date(*m.group(4, 5, 6))
        out["session"] = int(m.group(7))
    else:
        m = re.search(r"훈련\s*기간" + GAP + DATE + r"\s*~\s*" + DATE, t)
        if m:
            out["start_date"] = _date(*m.group(1, 2, 3))
            out["end_date"] = _date(*m.group(4, 5, 6))

    # 훈련유형: "훈련유형 K-디지털 트레이닝" / "K-디지털 기초역량훈련"
    m = re.search(r"훈련\s*유형\s*[:：]?\s*([^\n]{2,30}?)\s*(?:훈련\s*기간|\n|$)", t)
    if m:
        out["training_type"] = m.group(1).strip()

    # 실시회차 "2/2" → 이 과정의 총 회차 수
    m = re.search(r"실시\s*회차" + GAP + r"(\d{1,4})\s*/\s*(\d{1,4})", t)
    if m:
        out["max_session"] = max(int(m.group(1)), int(m.group(2)))

    # NCS: "응용SW엔지니어링(20010202)" / "5수준"
    m = re.search(r"([가-힣A-Za-z0-9·ㆍ/&]+(?: [가-힣A-Za-z0-9·ㆍ/&]+){0,4})\s*\(\s*(\d{8,10})\s*\)", t)
    if m:
        out["ncs_job"] = m.group(1).strip()
        out["ncs_code"] = m.group(2)
    m = _search([r"(?<!\d)([1-8])\s*수준", r"NCS\s*수준" + GAP + r"([1-8])", r"수준" + GAP + r"([1-8])(?!\d)"], t)
    if m:
        out["ncs_level"] = int(m.group(1))

    # 훈련일수·총 훈련시간: "113일, 총900시간"
    m = re.search(r"(\d{1,4})\s*일\s*[,/]?\s*총\s*([\d,]{1,6})\s*시간", t)
    if m:
        out["training_days"] = int(m.group(1))
        out["training_hours"] = _int(m.group(2))
    else:
        m = _search([r"총\s*훈련\s*시간" + GAP + r"([\d,]{1,6})\s*시간",
                     r"총\s*([\d,]{1,6})\s*시간"], t)
        if m:
            out["training_hours"] = _int(m.group(1))

    # 훈련비 (본인부담금이 아닌 전체 훈련비)
    m = _search([
        r"(?<![가-힣])훈련비" + GAP + r"([\d,]{4,})\s*원",
        r"총\s*훈련비" + GAP + r"([\d,]{4,})\s*원",
        r"실제\s*훈련비" + GAP + r"([\d,]{4,})\s*원",
    ], t)
    if m:
        out["training_fee"] = _int(m.group(1))

    # 인원: "수강확정 16명", "수강신청 16명", "정원 25명"
    m = _search([r"수강\s*확정\s*(?:인원)?" + GAP + r"(\d{1,4})\s*명?",
                 r"확정\s*인원" + GAP + r"(\d{1,4})"], t)
    if m:
        out["confirmed"] = int(m.group(1))
    m = re.search(r"수강\s*신청\s*(?:인원)?" + GAP + r"(\d{1,4})\s*명?", t)
    if m:
        out["applicants"] = int(m.group(1))
    m = _search([r"모집\s*(?:정원|인원)" + GAP + r"(\d{1,4})", r"(?<![가-힣])정원" + GAP + r"(\d{1,4})\s*명"], t)
    if m:
        out["capacity"] = int(m.group(1))

    # 만족도: 실제 고용24 표기 "만족도 (4.3) 수강평 8개" — 과정 전체 평균과 수강평 수
    m = re.search(r"만족도\s*[\(（]\s*(\d(?:\.\d{1,2})?)\s*[\)）]\s*(?:수강평\s*(\d{1,5})\s*개)?", t)
    if m:
        sat = float(m.group(1))
        if sat > 0:
            out["satisfaction"] = sat
        if m.group(2) is not None:
            out["evaluators"] = int(m.group(2))
    # 다른 표기: "만족도 4.9 (15명)" / "4.9점 (평가인원 15명)"
    m = None if "satisfaction" in out or "evaluators" in out else _search([
        r"만족도\s*(?:점수)?" + GAP + r"(\d(?:\.\d{1,2})?)\s*점?\s*[\(（]\s*(?:평가\s*(?:인원)?\s*[:：]?\s*)?(\d{1,4})\s*(?:명|건|개)?\s*[\)）]",
        r"만족도\s*(?:점수)?" + GAP + r"(\d(?:\.\d{1,2})?)\s*점?",
    ], t)
    if m:
        sat = float(m.group(1))
        if sat > 0:
            out["satisfaction"] = sat
        if m.lastindex and m.lastindex >= 2:
            out["evaluators"] = int(m.group(2))
    if "evaluators" not in out:
        m = re.search(r"평가\s*(?:인원|자\s*수)" + GAP + r"(\d{1,4})", t)
        if m:
            out["evaluators"] = int(m.group(1))

    # 수료인원/수료율 (있을 때만)
    m = re.search(r"수료\s*인원" + GAP + r"(\d{1,4})", t)
    if m:
        out["completed"] = int(m.group(1))
    m = re.search(r"수료율" + GAP + r"([\d.]{1,5})\s*%", t)
    if m:
        _set(out, "completion_rate", _rate(m.group(1)))

    # 취업률: "6개월 취업률 53.3%", "3개월 취업률 ..." ("해당없음"이면 안 넣음)
    m = re.search(r"6\s*개월\s*(?:후\s*)?취업률" + GAP + r"([\d.]{1,5})\s*%?", t)
    if m:
        _set(out, "employment_rate_6m", _rate(m.group(1)))
    m = re.search(r"3\s*개월\s*(?:후\s*)?취업률" + GAP + r"([\d.]{1,5})\s*%?", t)
    if m:
        _set(out, "employment_rate_3m", _rate(m.group(1)))
    if "employment_rate_6m" not in out:
        # 기간 표시 없이 "취업률 61.1%"만 있으면 6개월 취업률로 본다 (직종별/기관 취업률 제외)
        m = re.search(r"(?<!직종별 )(?<!기관 )(?<!직종 )취업률" + GAP + r"([\d.]{1,5})\s*%", t)
        if m:
            _set(out, "employment_rate_6m", _rate(m.group(1)))

    return out


def notice_snippets(name: str, text: str) -> None:
    """GitHub Actions 알림으로 주요 단어 주변 글자를 남긴다 (정규식 맞추기용)."""
    import os
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    t = re.sub(r"\s+", " ", text)
    parts = []
    for kw in ("수강확정인원", "만족도 ", "수료", "취업률", "훈련기간", "훈련시간", "NCS직무분류", "실시현황"):
        idx = [m.start() for m in re.finditer(kw, t)][:2]
        for i in idx:
            parts.append(f"[{kw}] {t[max(0, i - 25):i + 45]}")
    msg = " | ".join(parts)[:3800].replace("::", ":")
    print(f"::notice title=상세 페이지 {name}::{msg}")


# ---------------------------------------------------------------------------
# '다른회차 정보보기' 영역: 한 페이지에 그 과정의 모든 회차 실적이 들어 있다
#   "28회차 모집마감 훈련비 13,762,240 원 ... 훈련기간 2024-10-15 ~ 2025-04-04 ...
#    모집인원 25명 수강확정인원 15명 수강신청인원 (…): 15명 만족도 100점 기준84.7 점 (14 명)
#    취업률 고용보험가입 3개월 44.4% (4/9) 취업률 고용보험가입 6개월 66.7% (6/9)
#    취업률 고용보험미가입 3개월 11.1% (1/9) 취업률 고용보험미가입 6개월 11.1% (1/9) … 실시여부 Y"
#   아직 집계 전이면 취업률 자리에 '훈련진행중' 같은 글자가 온다.
# ---------------------------------------------------------------------------

BLOCK_START_RE = re.compile(r"(\d{1,4})\s*회차\s+(?:[가-힣]{2,6}\s+)?훈련비\s+([\d,]+)\s*원")


def _emp(block: str, label: str) -> tuple[Optional[float], Optional[int], Optional[int]]:
    m = re.search(label + r"\s*([\d.]+)\s*%\s*\(\s*(\d+)\s*/\s*(\d+)\s*\)", block)
    if not m:
        return None, None, None
    return _rate(m.group(1)), int(m.group(2)), int(m.group(3))


def parse_session_blocks(text: str) -> dict[int, dict]:
    """상세 페이지 전체 텍스트 → {회차: 값}. 영역이 없으면 빈 dict."""
    t = re.sub(r"\s+", " ", text or "")
    starts = list(BLOCK_START_RE.finditer(t))
    out: dict[int, dict] = {}
    for i, m in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else min(len(t), m.end() + 1500)
        block = t[m.start():end]
        if "취업률" not in block and "수강확정인원" not in block:
            continue  # 페이지 위쪽의 현재 회차 요약 등 다른 영역
        sess = int(m.group(1))
        v: dict = {"training_fee": _int(m.group(2))}
        d = re.search(DATE + r"\s*~\s*" + DATE, block)
        if d:
            v["start_date"] = _date(*d.group(1, 2, 3))
            v["end_date"] = _date(*d.group(4, 5, 6))
        for key, pat in (("capacity", r"모집\s*인원\s*(?:\(\s*정원\s*\))?\s*(\d{1,4})\s*명"),
                         ("confirmed", r"수강\s*확정\s*인원\s*(\d{1,4})\s*명"),
                         ("applicants", r"수강\s*신청\s*인원[^0-9]{0,40}?(\d{1,4})\s*명")):
            mm = re.search(pat, block)
            if mm:
                v[key] = int(mm.group(1))
        # "만족도 100점 기준91.1 점 (4.6 / 16명)" 또는 "만족도 100점 기준84.7 점 (14 명)"
        mm = re.search(r"100\s*점\s*기준\s*([\d.]+)\s*점\s*\(\s*(?:([\d.]+)\s*/\s*)?(\d*)\s*명\s*\)", block)
        if mm:
            score = float(mm.group(1))
            cnt = int(mm.group(3)) if mm.group(3) else 0
            if score > 0 and cnt > 0:
                five = float(mm.group(2)) if mm.group(2) else round(score / 20, 1)   # 5점 척도 (기존 시트와 같음)
                v["satisfaction"] = five
                v["evaluators"] = cnt
        r3, _, _ = _emp(block, r"고용보험\s*가입\s*3\s*개월")
        r6, hired6, base6 = _emp(block, r"고용보험\s*가입\s*6\s*개월")
        u6, uhired6, _ = _emp(block, r"고용보험\s*미가입\s*6\s*개월")
        if r3 is not None:
            v["employment_rate_3m"] = r3
        if r6 is not None:
            v["employment_rate_6m"] = r6
        if base6 is not None:
            v["employment_base"] = base6            # 취업률 산정 대상 인원
        mm = re.search(r"실시\s*여부\s*([YN])\b", block)
        if mm:
            v["held"] = mm.group(1) == "Y"
        out[sess] = v
    return out


class DetailScraper:
    def __init__(self, delay: float = 1.2, max_pages: int = 1500, dump_dir: Optional[str] = None):
        self.delay = delay
        self.max_pages = max_pages
        self.pages = 0
        self.dump_dir = dump_dir
        self._dumped = 0
        self._noticed = 0
        self._block_notes = 0
        self.consecutive_errors = 0
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"),
            "Accept-Language": "ko-KR,ko;q=0.9",
        })

    @property
    def exhausted(self) -> bool:
        # 한도를 다 썼거나, 연속 실패가 많으면(차단 의심) 멈춘다
        return self.pages >= self.max_pages or self.consecutive_errors >= 15

    def fetch(self, tracse_id: str, session: int | str, crse_tracse_se: str,
              trainst_id: str) -> Optional[dict]:
        """회차 상세 페이지를 읽어 dict로. 회차가 없거나 실패하면 None."""
        if self.exhausted:
            return None
        url = detail_url(tracse_id, session, crse_tracse_se, trainst_id)
        self.pages += 1
        for attempt in range(3):
            try:
                r = self.s.get(url, timeout=30)
                r.raise_for_status()
                r.encoding = r.apparent_encoding or "utf-8"
                time.sleep(self.delay)
                text = html_to_text(r.text)
                got = parse_detail_text(text)
                if self.dump_dir and self._dumped < 5:
                    self._dump(tracse_id, session, r.text, text)
                if self.dump_dir and "start_date" in got and self._noticed < 2:
                    self._noticed += 1
                    notice_snippets(f"{tracse_id} {session}회차", text)
                self.consecutive_errors = 0
                # 기간·회차를 못 읽으면 없는 회차(또는 오류 페이지)로 본다
                if "start_date" not in got:
                    return None
                if got.get("session") and int(got["session"]) != int(session):
                    # 없는 회차를 요청하면 다른 회차로 넘어가는 경우
                    return None
                got.update({k: v for k, v in parse_names(r.text).items() if k not in got})
                # '다른회차 정보보기' 탭: 페이지가 열린 뒤 별도 요청으로 불러온다 (과정의 모든 회차 실적)
                got["sessions"] = self.fetch_sessions(tracse_id, session)
                return got
            except (ValueError, TypeError, AttributeError, IndexError) as e:
                log.warning("상세 페이지 해석 실패(%s): %s", url, e)
                return None
            except requests.RequestException as e:
                wait = 5 * (attempt + 1)
                log.warning("상세 페이지 실패(%s), %ss 후 재시도: %s", url, wait, e)
                time.sleep(wait)
        self.consecutive_errors += 1
        return None

    OTHER_TME_URL = "https://www.work24.go.kr/hr/a/a/3100/selectOtherTracseTmeTab.do"

    def fetch_sessions(self, tracse_id: str, session: int | str) -> dict[int, dict]:
        """'다른회차 정보보기' 탭 HTML을 받아 {회차: 실적}으로. 실패하면 빈 dict.

        tracseTme(실제로 있는 회차 아무거나)를 같이 보내야 취업률 칸이 채워져서 온다.
        """
        for attempt in range(2):
            try:
                r = self.s.post(self.OTHER_TME_URL, data={"tracseId": tracse_id, "tracseTme": str(session), "mobileYn": "N"},
                                headers={"X-Requested-With": "XMLHttpRequest"}, timeout=30)
                r.raise_for_status()
                r.encoding = r.apparent_encoding or "utf-8"
                time.sleep(self.delay / 2)
                blocks = parse_session_blocks(BeautifulSoup(r.text, "html.parser").get_text(" "))
                n_emp = sum(1 for v in blocks.values() if v.get("employment_rate_6m") is not None)
                if self.dump_dir and self._block_notes < 4 and n_emp:
                    self._block_notes += 1
                    import os
                    if os.environ.get("GITHUB_ACTIONS"):
                        flat = re.sub(r"\s+", " ", BeautifulSoup(r.text, "html.parser").get_text(" "))
                        m = re.search(r"고용보험가입 6개월\s*[\d.]+\s*%", flat)
                        i = m.start() if m else 0
                        ex = [(k, v.get("employment_rate_3m"), v.get("employment_rate_6m"), v.get("satisfaction"))
                              for k, v in sorted(blocks.items()) if v.get("employment_rate_6m") is not None][:4]
                        print(f"::notice title=다른회차 취업률 {tracse_id[-6:]}::파싱 {len(blocks)}회차 중 6개월 취업률 {n_emp} / "
                              f"예 {ex} / 원문: {flat[max(0, i - 300):i + 200]}"[:1500])
                return blocks
            except (requests.RequestException, ValueError) as e:
                log.warning("다른회차 탭 실패(%s): %s", tracse_id, e)
                time.sleep(3)
        return {}

    def _dump(self, tracse_id: str, session, html: str, text: str) -> None:
        import os
        os.makedirs(self.dump_dir, exist_ok=True)
        base = os.path.join(self.dump_dir, f"detail_{tracse_id}_{session}")
        with open(base + ".html", "w", encoding="utf-8") as f:
            f.write(html)
        with open(base + ".txt", "w", encoding="utf-8") as f:
            f.write(text)
        self._dumped += 1
