"""고용24 훈련과정 상세 페이지에서 오픈API에 없는 값만 보충한다.

대상 값: NCS 수준, 만족도 평가인원, 수강확정인원, (API에 없을 때) 훈련시간·훈련일수·NCS 직무명.

화면의 CSS 클래스 대신 '보이는 텍스트'의 라벨+값을 정규식으로 읽어서,
화면 디자인이 조금 바뀌어도 버티게 했다. 못 읽은 값은 None으로 두고
기존 DB 값을 덮어쓰지 않는다.
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


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return _norm(soup.get_text("\n"))


# 라벨과 값 사이에 줄바꿈·콜론·공백이 섞여도 되도록 최대 30자까지 허용
GAP = r"[\s:：]{0,30}"


def parse_detail_text(text: str) -> dict:
    """상세 페이지 텍스트 → 보충 값 dict (못 찾은 키는 넣지 않음)."""
    t = _norm(text)
    out: dict = {}

    # NCS: "응용SW엔지니어링(20010202)" / "5수준"
    m = re.search(r"([가-힣A-Za-z0-9·ㆍ/&]+(?: [가-힣A-Za-z0-9·ㆍ/&]+){0,4})\s*\(\s*(\d{8,10})\s*\)", t)
    if m:
        out["ncs_job"] = m.group(1).strip()
        out["ncs_code"] = m.group(2)
    m = _search([r"(?<!\d)([1-8])\s*수준", r"NCS\s*수준" + GAP + r"([1-8])", r"수준" + GAP + r"([1-8])(?!\d)"], t)
    if m:
        out["ncs_level"] = int(m.group(1))

    # 훈련일수·총 훈련시간: "113일, 총900시간" / "훈련시간 900시간"
    m = re.search(r"(\d{1,4})\s*일\s*[,/]?\s*총\s*([\d,]{1,6})\s*시간", t)
    if m:
        out["training_days"] = int(m.group(1))
        out["training_hours"] = _int(m.group(2))
    else:
        m = _search([r"총\s*훈련\s*시간" + GAP + r"([\d,]{1,6})\s*시간",
                     r"총\s*([\d,]{1,6})\s*시간"], t)
        if m:
            out["training_hours"] = _int(m.group(1))

    # 인원: "수강확정 16명", "수강신청 16명", "정원 25명"
    m = _search([r"수강\s*확정\s*(?:인원)?" + GAP + r"(\d{1,4})\s*명?",
                 r"확정\s*인원" + GAP + r"(\d{1,4})"], t)
    if m:
        out["confirmed"] = int(m.group(1))
    m = _search([r"모집\s*정원" + GAP + r"(\d{1,4})", r"(?<![가-힣])정원" + GAP + r"(\d{1,4})\s*명"], t)
    if m:
        out["capacity"] = int(m.group(1))

    # 만족도: "만족도 4.9 (15명)" / "4.9점 (평가인원 15명)"
    m = _search([
        r"만족도\s*(?:점수)?" + GAP + r"(\d(?:\.\d{1,2})?)\s*점?\s*[\(（]\s*(?:평가\s*(?:인원)?\s*[:：]?\s*)?(\d{1,4})\s*명",
        r"만족도\s*(?:점수)?" + GAP + r"(\d(?:\.\d{1,2})?)\s*점?",
    ], t)
    if m:
        out["satisfaction"] = float(m.group(1))
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

    return out


class DetailScraper:
    def __init__(self, delay: float = 1.5, max_pages: int = 300, dump_dir: Optional[str] = None):
        self.delay = delay
        self.max_pages = max_pages
        self.pages = 0
        self.dump_dir = dump_dir
        self._dumped = 0
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"),
            "Accept-Language": "ko-KR,ko;q=0.9",
        })

    @property
    def exhausted(self) -> bool:
        return self.pages >= self.max_pages

    def fetch(self, tracse_id: str, session: int | str, crse_tracse_se: str,
              trainst_id: str) -> Optional[dict]:
        if self.exhausted:
            return None
        url = detail_url(tracse_id, session, crse_tracse_se, trainst_id)
        self.pages += 1
        for attempt in range(3):
            try:
                r = self.s.get(url, timeout=30)
                r.raise_for_status()
                r.encoding = r.apparent_encoding or "utf-8"
                text = html_to_text(r.text)
                time.sleep(self.delay)
                if self.dump_dir and self._dumped < 5:
                    self._dump(tracse_id, session, r.text, text)
                if "훈련" not in text:
                    log.warning("상세 페이지 내용이 비어 있음: %s", url)
                    return None
                return parse_detail_text(text)
            except requests.RequestException as e:
                wait = 5 * (attempt + 1)
                log.warning("상세 페이지 실패(%s), %ss 후 재시도: %s", url, wait, e)
                time.sleep(wait)
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
