"""고용24 KDT 훈련과정 목록 크롤러 (Playwright).

목록 페이지는 과정 링크와 페이지 이동이 모두 자바스크립트(javascript:void(0))라서
실제 브라우저로 열고 페이지를 넘기며 과정 식별자를 모은다.

과정 식별자 추출은 두 가지 방법을 차례로 쓴다.
1. 링크의 onclick 속성 등에서 tracseId / trainstCstmrId 같은 값을 정규식으로 읽기
2. 그래도 못 찾으면 과정명 링크를 실제로 눌러 새 창(상세 페이지) 주소를 읽기
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# 사용자가 준 KDT 목록 주소 (serverToday 등 날짜 값은 뺌)
LIST_URL = (
    "https://www.work24.go.kr/hr/a/a/1100/trnnCrsInf2.do"
    "?dtlContextPath=&redirectUrl=%2Fa%2Fa%2F1100%2FtrnnCrsInf2Post.do&topArea="
    "&programMenuIdentification=EBG020000000000&menuPurpSecd=EBM01"
    "&currentMenuId=EBG020000000313&area=&crseTracseSe=&crseTracseSeKDT=&ncs=&gvrnInstt="
    "&selectNCSKeyword=&srchType=&compareArgArr=&action=trnnCrsInf2Post.do&pageId=6"
)

KDT_CODE = "C0104"

TRACSE_ID_RE = re.compile(r"^A[A-Z0-9]{2}\d{10,16}$")   # 예: AIG20233000936060
CSTMR_ID_RE = re.compile(r"^\d{9,13}$")                  # 예: 500020039555
CRSE_SE_RE = re.compile(r"^C\d{4}[A-Z]?$")               # 예: C0104
QUOTED_ARG_RE = re.compile(r"""['"]([^'"]*)['"]""")
NAMED_PARAM_RE = re.compile(
    r"(tracseId|tracseTme|crseTracseSe|trainstCstmrId)\s*[=:]\s*['\"]?([A-Za-z0-9]+)")


@dataclass
class CourseRef:
    tracse_id: str
    trainst_cstmr_id: str
    tracse_tme: int = 1
    crse_tracse_se: str = KDT_CODE
    title: str = ""
    institution: str = ""
    card_text: str = field(default="", repr=False)

    @property
    def key(self) -> tuple:
        return (self.tracse_id, self.trainst_cstmr_id)


def parse_course_ref(text: str) -> Optional[CourseRef]:
    """onclick 속성이나 상세 페이지 URL에서 CourseRef를 만든다. 못 찾으면 None."""
    if not text:
        return None
    named = dict(NAMED_PARAM_RE.findall(text))
    if "tracseId" in named and "trainstCstmrId" in named:
        return CourseRef(
            tracse_id=named["tracseId"],
            trainst_cstmr_id=named["trainstCstmrId"],
            tracse_tme=int(named["tracseTme"]) if named.get("tracseTme", "").isdigit() else 1,
            crse_tracse_se=named.get("crseTracseSe") or KDT_CODE,
        )
    # 함수 호출 형태: fnDetail('AIG2023...','2','C0104','500020039555', ...)
    args = [a.strip() for a in QUOTED_ARG_RE.findall(text)]
    tid = next((a for a in args if TRACSE_ID_RE.match(a)), None)
    if not tid:
        return None
    rest = args[args.index(tid) + 1:]
    cst = next((a for a in rest if CSTMR_ID_RE.match(a)), None)
    if not cst:
        return None
    se = next((a for a in rest if CRSE_SE_RE.match(a)), KDT_CODE)
    tme = next((a for a in rest if a.isdigit() and len(a) <= 4), "1")
    return CourseRef(tracse_id=tid, trainst_cstmr_id=cst, tracse_tme=int(tme), crse_tracse_se=se)


INST_HINT_RE = re.compile(r"(학원|캠퍼스|대학교?|센터|아카데미|교육원|훈련원|직업전문학교|㈜|\(주\)|주식회사|협회|진흥원|재단|연구원)")
BADGE_RE = re.compile(r"인증|우수|모집|훈련기관|참여 유형|본인부담|취업률|회차|시간|\d[\d,]*\s*원")


def parse_card_text(text: str, title: str = "") -> dict:
    """목록 카드 텍스트에서 회차·기관명 등 보조 정보."""
    out: dict = {}
    text = text or ""
    m = re.search(r"\(\s*(\d+)\s*회차\s*\)", text)
    if m:
        out["session"] = int(m.group(1))
    for line in (ln.strip() for ln in text.split("\n")):
        if not line or line == title or len(line) > 40 or BADGE_RE.search(line):
            continue
        if INST_HINT_RE.search(line):
            out["institution"] = line
            break
    return out


# 페이지 안에서 실행: 과정 링크 후보와 그 카드 텍스트를 모은다
_EXTRACT_JS = r"""
() => {
  const out = [];
  const idRe = /A[A-Z0-9]{2}\d{10,16}/;
  const els = document.querySelectorAll('[onclick], a[href*="tracseId"], [data-tracse-id], [data-tracseid]');
  for (const el of els) {
    const attrs = [el.getAttribute('onclick') || '', el.getAttribute('href') || ''];
    for (const a of el.attributes) { if (a.name.startsWith('data-')) attrs.push(`${a.name}='${a.value}'`); }
    const raw = attrs.join(' ');
    if (!idRe.test(raw) && !/tracse/i.test(raw)) continue;
    let card = el;
    for (let i = 0; i < 8 && card.parentElement; i++) {
      card = card.parentElement;
      if ((card.innerText || '').length > 80 && /회차|훈련/.test(card.innerText)) break;
    }
    const instEl = card.querySelector('[title*="기관"]');
    out.push({
      raw,
      text: (el.innerText || el.getAttribute('title') || '').trim(),
      title: el.getAttribute('title') || '',
      inst: instEl ? (instEl.innerText || '').trim() : '',
      card: (card.innerText || '').trim().slice(0, 1500),
    });
  }
  return out;
}
"""

# 페이지 안에서 실행: 다음 페이지로 이동. 'clicked:N' / 'next' / 'none' 반환
_NEXT_PAGE_JS = r"""
(target) => {
  const isVisible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const all = [...document.querySelectorAll('a, button')].filter(isVisible);
  const label = el => ((el.innerText || '') + ' ' + (el.getAttribute('title') || '')).trim();
  const nextBtn = all.find(el => /^다음(\s|$)|다음\s*페이지/.test(label(el)));
  let scope = nextBtn ? nextBtn.closest('nav, ul, div, .pagination, .paging') : document;
  for (let i = 0; i < 3 && scope && scope !== document; i++) {
    if ([...scope.querySelectorAll('a, button')].some(el => (el.innerText || '').trim() === String(target))) break;
    scope = scope.parentElement;
  }
  const cands = [...(scope || document).querySelectorAll('a, button')]
    .filter(isVisible)
    .filter(el => (el.innerText || '').trim() === String(target));
  if (cands.length) { cands[0].click(); return 'clicked:' + target; }
  if (nextBtn) { nextBtn.click(); return 'next'; }
  return 'none';
}
"""

# 페이지 크기 '100개씩'으로 바꾸고 '적용'
_PAGE_SIZE_JS = r"""
() => {
  for (const sel of document.querySelectorAll('select')) {
    const opt = [...sel.options].find(o => /100\s*개/.test(o.text));
    if (opt) {
      sel.value = opt.value;
      sel.dispatchEvent(new Event('change', { bubbles: true }));
      const btn = [...document.querySelectorAll('a, button, input[type=button], input[type=submit]')]
        .find(el => /적용/.test((el.innerText || el.value || '').trim()));
      if (btn) { btn.click(); return 'applied'; }
      return 'changed';
    }
  }
  return 'none';
}
"""


class ListCrawler:
    def __init__(self, url: str = LIST_URL, max_pages: int = 300, headless: bool = True,
                 dump_dir: Optional[str] = None, click_fallback: bool = True):
        self.url = url
        self.max_pages = max_pages
        self.headless = headless
        self.dump_dir = dump_dir
        self.click_fallback = click_fallback

    def crawl(self) -> dict[tuple, CourseRef]:
        from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

        found: dict[tuple, CourseRef] = {}
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            ctx = browser.new_context(locale="ko-KR", viewport={"width": 1400, "height": 1000})
            page = ctx.new_page()
            page.set_default_timeout(45000)
            page.goto(self.url, wait_until="domcontentloaded")
            self._settle(page)

            try:
                res = page.evaluate(_PAGE_SIZE_JS)
                log.info("페이지 크기 변경: %s", res)
                if res != "none":
                    self._settle(page)
            except Exception as e:  # noqa: BLE001
                log.warning("페이지 크기 변경 실패(무시): %s", e)

            prev_sig = None
            for page_no in range(1, self.max_pages + 1):
                if self.dump_dir and page_no <= 2:
                    self._dump(page, f"list_page{page_no}")
                refs = self._extract(page, ctx)
                sig = tuple(sorted(r.key for r in refs))
                if not refs:
                    log.warning("%d페이지에서 과정을 못 찾음 — 중단", page_no)
                    break
                if sig == prev_sig:
                    log.info("%d페이지가 이전과 같음 — 마지막 페이지로 판단", page_no)
                    break
                new = 0
                for r in refs:
                    if r.key not in found:
                        new += 1
                        found[r.key] = r
                    else:
                        old = found[r.key]
                        old.tracse_tme = max(old.tracse_tme, r.tracse_tme)
                log.info("목록 %d페이지: %d개 (신규 %d, 누적 %d)", page_no, len(refs), new, len(found))
                prev_sig = sig

                try:
                    moved = page.evaluate(_NEXT_PAGE_JS, page_no + 1)
                except Exception as e:  # noqa: BLE001
                    log.warning("페이지 이동 실패: %s", e)
                    break
                if moved == "none":
                    log.info("다음 페이지 없음")
                    break
                self._settle(page)
            browser.close()
        return found

    # ------------------------------------------------------------------
    def _settle(self, page) -> None:
        from playwright.sync_api import TimeoutError as PwTimeout
        try:
            page.wait_for_load_state("networkidle", timeout=20000)
        except PwTimeout:
            pass
        page.wait_for_timeout(800)

    def _extract(self, page, ctx) -> list[CourseRef]:
        items = page.evaluate(_EXTRACT_JS)
        refs: dict[tuple, CourseRef] = {}
        for it in items:
            ref = parse_course_ref(it["raw"])
            if not ref:
                continue
            title = re.sub(r"\s*훈련과정 정보.*$", "", it.get("title") or "").strip()
            if title and not ref.title:
                ref.title = title
            elif it.get("text") and len(it["text"]) > 3 and not ref.title:
                ref.title = it["text"]
            inst = (it.get("inst") or "").strip()
            if inst and len(inst) < 80:
                ref.institution = inst
            ref.card_text = it.get("card", "")
            card = parse_card_text(ref.card_text, ref.title)
            if not ref.institution and card.get("institution"):
                ref.institution = card["institution"]
            sess = card.get("session")
            if sess:
                ref.tracse_tme = max(ref.tracse_tme, sess)
            if ref.key in refs:
                cur = refs[ref.key]
                cur.title = cur.title or ref.title
                cur.institution = cur.institution or ref.institution
                cur.tracse_tme = max(cur.tracse_tme, ref.tracse_tme)
            else:
                refs[ref.key] = ref
        if refs or not self.click_fallback:
            return list(refs.values())
        return self._extract_by_click(page, ctx)

    def _extract_by_click(self, page, ctx) -> list[CourseRef]:
        """onclick에서 못 찾을 때: 과정명 링크를 눌러 새 창 주소를 읽는다."""
        links = page.locator("a[title*='훈련과정 정보'], a[title*='과정 정보']")
        n = links.count()
        log.info("onclick에서 못 찾아 링크 %d개를 직접 눌러 확인", n)
        refs = []
        for i in range(n):
            link = links.nth(i)
            try:
                with ctx.expect_page(timeout=15000) as pinfo:
                    link.click()
                popup = pinfo.value
                popup.wait_for_load_state("domcontentloaded")
                ref = parse_course_ref(popup.url)
                popup.close()
            except Exception as e:  # noqa: BLE001
                log.warning("링크 %d 클릭 실패: %s", i, e)
                continue
            if ref:
                ref.title = re.sub(r"\s*훈련과정 정보.*$", "", link.get_attribute("title") or "").strip()
                refs.append(ref)
        return refs

    def _dump(self, page, name: str) -> None:
        import os
        os.makedirs(self.dump_dir, exist_ok=True)
        with open(os.path.join(self.dump_dir, name + ".html"), "w", encoding="utf-8") as f:
            f.write(page.content())
        try:
            page.screenshot(path=os.path.join(self.dump_dir, name + ".png"), full_page=True)
        except Exception:  # noqa: BLE001
            pass
