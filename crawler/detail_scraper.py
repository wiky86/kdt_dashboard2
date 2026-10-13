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
    m = _search([r"모집\s*정원" + GAP + r"(\d{1,4})", r"(?<![가-힣])정원" + GAP + r"(\d{1,4})\s*명"], t)
    if m:
        out["capacity"] = int(m.group(1))

    # 만족도: "만족도 4.9 (15명)" / "4.9점 (평가인원 15명)"
    m = _search([
        r"만족도\s*(?:점수)?" + GAP + r"(\d(?:\.\d{1,2})?)\s*점?\s*[\(（]\s*(?:평가\s*(?:인원)?\s*[:：]?\s*)?(\d{1,4})\s*명",
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
        out["completion_rate"] = float(m.group(1))

    # 취업률: "6개월 취업률 53.3%", "3개월 취업률 ..." ("해당없음"이면 안 넣음)
    m = re.search(r"6\s*개월\s*(?:후\s*)?취업률" + GAP + r"([\d.]{1,5})\s*%?", t)
    if m:
        out["employment_rate_6m"] = float(m.group(1))
    m = re.search(r"3\s*개월\s*(?:후\s*)?취업률" + GAP + r"([\d.]{1,5})\s*%?", t)
    if m:
        out["employment_rate_3m"] = float(m.group(1))
    if "employment_rate_6m" not in out:
        # 기간 표시 없이 "취업률 61.1%"만 있으면 6개월 취업률로 본다 (직종별/기관 취업률 제외)
        m = re.search(r"(?<!직종별 )(?<!기관 )(?<!직종 )취업률" + GAP + r"([\d.]{1,5})\s*%", t)
        if m:
            out["employment_rate_6m"] = float(m.group(1))

    return out


class DetailScraper:
    def __init__(self, delay: float = 1.2, max_pages: int = 1500, dump_dir: Optional[str] = None):
        self.delay = delay
        self.max_pages = max_pages
        self.pages = 0
        self.dump_dir = dump_dir
        self._dumped = 0
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
                if self.dump_dir and self._dumped < 5:
                    self._dump(tracse_id, session, r.text, text)
                got = parse_detail_text(text)
                self.consecutive_errors = 0
                # 기간·회차를 못 읽으면 없는 회차(또는 오류 페이지)로 본다
                if "start_date" not in got:
                    return None
                if got.get("session") and int(got["session"]) != int(session):
                    # 없는 회차를 요청하면 다른 회차로 넘어가는 경우
                    return None
                got.update({k: v for k, v in parse_names(r.text).items() if k not in got})
                return got
            except requests.RequestException as e:
                wait = 5 * (attempt + 1)
                log.warning("상세 페이지 실패(%s), %ss 후 재시도: %s", url, wait, e)
                time.sleep(wait)
        self.consecutive_errors += 1
        return None

    def _dump(self, tracse_id: str, session, html: str, text: str) -> None:
        import os
        os.makedirs(self.dump_dir, exist_ok=True)
        base = os.path.join(self.dump_dir, f"detail_{tracse_id}_{session}")
        with open(base + ".html", "w", encoding="utf-8") as f:
            f.write(html)
        with open(base + ".txt", "w", encoding="utf-8") as f:
            f.write(text)
        self._dumped += 1
