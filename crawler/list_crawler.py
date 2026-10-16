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



TRACSE_ID_ANY_RE = re.compile(r"A[A-Z0-9]{2}\d{10,16}")


def _card_of(tag):
    """링크에서 위로 올라가며 과정 카드(텍스트가 충분하고 회차/훈련이 들어간 요소)를 찾는다."""
    card = tag
    for _ in range(8):
        if card.parent is None:
            break
        card = card.parent
        text = card.get_text("\n", strip=True)
        if len(text) > 80 and re.search(r"회차|훈련", text):
            break
    return card


INST_LINK_RE = re.compile(r"훈련\s*기관\s*정보|기관\s*정보")
COURSE_LINK_RE = re.compile(r"훈련\s*과정\s*정보|과정\s*정보")
INST_FUNC_RE = re.compile(r"Trainst|Inst(?:Info|Dtl)", re.I)


def clean_link_title(title: str) -> str:
    """'자바 과정 훈련과정 정보 새 창 열림' → '자바 과정'."""
    t = re.sub(r"\s*(?:훈련\s*)?(?:과정|기관)\s*정보.*$", "", title or "")
    t = re.sub(r"\s*새\s*창\s*열림\s*$", "", t)
    return t.strip()


def parse_list_html(html: str) -> list[CourseRef]:
    """목록 페이지 HTML → CourseRef 목록 (페이지 안 스크립트 없이 파이썬에서 분석)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    refs: dict[tuple, CourseRef] = {}
    for tag in soup.find_all(True):
        raw = " ".join(f"{k}='{v}'" if k.startswith("data-") else str(v)
                       for k, v in tag.attrs.items()
                       if k in ("onclick", "href") or k.startswith("data-"))
        if not raw or not (TRACSE_ID_ANY_RE.search(raw) or "tracse" in raw.lower()):
            continue
        ref = parse_course_ref(raw)
        if not ref:
            continue
        title_attr = tag.get("title") or ""
        text = tag.get_text(" ", strip=True)
        onclick = tag.get("onclick") or ""
        # 기관 링크(예: fn_viewTrainstInfo, title "OO 훈련기관정보 새 창 열림")에도 과정 ID가 들어 있다.
        # 그런 링크에서는 과정명을 가져오지 않는다.
        is_inst_link = bool(INST_LINK_RE.search(title_attr) or INST_FUNC_RE.search(onclick)) \
            and not COURSE_LINK_RE.search(title_attr)
        is_course_link = bool(COURSE_LINK_RE.search(title_attr))
        if is_inst_link:
            ref.title = ""
            inst = clean_link_title(title_attr) or text
            if 0 < len(inst) < 80:
                ref.institution = inst
        else:
            ref.title = clean_link_title(title_attr) or (text if 3 < len(text) < 150 else "")
        card = _card_of(tag)
        if not ref.institution:
            inst_el = card.find(attrs={"title": INST_LINK_RE})
            if inst_el is not None:
                inst = clean_link_title(inst_el.get("title") or "") or inst_el.get_text(" ", strip=True)
                if 0 < len(inst) < 80:
                    ref.institution = inst
        ref.card_text = card.get_text("\n", strip=True)[:1500]
        info = parse_card_text(ref.card_text, ref.title)
        if not ref.institution and info.get("institution"):
            ref.institution = info["institution"]
        if info.get("session"):
            ref.tracse_tme = max(ref.tracse_tme, info["session"])
        if ref.key in refs:
            cur = refs[ref.key]
            if is_course_link and ref.title:
                cur.title = ref.title                       # 과정 링크의 이름이 가장 정확
                cur.crse_tracse_se = ref.crse_tracse_se or cur.crse_tracse_se
            elif not cur.title:
                cur.title = ref.title
            cur.institution = cur.institution or ref.institution
            cur.tracse_tme = max(cur.tracse_tme, ref.tracse_tme)
        else:
            refs[ref.key] = ref
    return list(refs.values())


def find_page_link(html: str, target: int) -> Optional[tuple[str, str]]:
    """페이지 번호 target 링크(없으면 '다음' 버튼)를 찾아 ('onclick'|'href'|'text', 값)으로 돌려준다."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    clickable = soup.find_all(["a", "button"])
    label = lambda el: (el.get_text(" ", strip=True) + " " + (el.get("title") or "")).strip()  # noqa: E731
    next_btn = next((el for el in clickable if re.match(r"^다음(\s|$)|.*다음\s*페이지", label(el))), None)

    scope = soup
    if next_btn is not None:
        scope = next_btn.parent or soup
        for _ in range(3):
            if any(el.get_text(strip=True) == str(target) for el in scope.find_all(["a", "button"])):
                break
            scope = scope.parent or scope

    def describe(el):
        if el.get("onclick"):
            return ("onclick", el["onclick"])
        href = el.get("href") or ""
        if href and not href.startswith("javascript:void") and href != "#":
            return ("href", href)
        return ("text", el.get_text(strip=True))

    for el in scope.find_all(["a", "button"]):
        if el.get_text(strip=True) == str(target):
            return describe(el)
    if next_btn is not None:
        # 마지막 페이지에서는 '다음'이 숨겨지거나 비활성화된다
        cls = " ".join(next_btn.get("class") or [])
        style = (next_btn.get("style") or "").replace(" ", "")
        if "disabled" in cls or next_btn.has_attr("disabled") or "display:none" in style:
            return None
        return describe(next_btn)
    return None


def find_page_size_control(html: str) -> Optional[tuple[str, str, str]]:
    """'100개' 옵션이 있는 select의 id, 그 option 값, 근처 '적용' 버튼 id."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    for sel in soup.find_all("select"):
        opt = next((o for o in sel.find_all("option") if re.search(r"100\s*개", o.get_text())), None)
        if not opt or not sel.get("id"):
            continue
        btn_id = ""
        scope = sel
        for _ in range(4):
            scope = scope.parent
            if scope is None:
                break
            btn = next((b for b in scope.find_all(["button", "a", "input"])
                        if re.search(r"적용", b.get_text() or b.get("value", ""))), None)
            if btn is not None:
                btn_id = btn.get("id", "")
                break
        return sel["id"], opt.get("value", "100"), btn_id
    return None


def _notice(title: str, msg: str) -> None:
    import os
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice title={title}::{msg.replace(chr(10), ' ')[:1500]}")


def page_size_hint(html: str) -> str:
    """'개씩' 주변 HTML을 잘라서 보여준다."""
    i = (html or "").find("개씩")
    return re.sub(r"\s+", " ", html[max(0, i - 700):i + 500]) if i >= 0 else "('개씩' 없음)"


def css_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def safe_title(page) -> str:
    try:
        return page.title()
    except Exception:  # noqa: BLE001
        return ""


def log_diagnostics(url: str, title: str, html: str) -> None:
    """목록을 못 읽을 때 원인을 찾을 수 있도록 핵심 정보를 로그에 남긴다."""
    onclicks = re.findall(r'onclick\s*=\s*"([^"]{0,160})"', html or "")
    with_id = [o for o in onclicks if TRACSE_ID_ANY_RE.search(o)]
    funcs = sorted({m.group(1) for o in onclicks for m in [re.match(r"\s*(?:javascript:)?\s*([\w.$]+)\s*\(", o)] if m})
    log.info("[진단] 주소: %s", url)
    log.info("[진단] 제목: %s / HTML %d자 / onclick %d개 (과정ID 포함 %d개)",
             title, len(html or ""), len(onclicks), len(with_id))
    log.info("[진단] onclick 함수 이름: %s", ", ".join(funcs[:30]))
    for o in (with_id or onclicks)[:5]:
        log.info("[진단] onclick 예시: %s", o)
    ids = TRACSE_ID_ANY_RE.findall(html or "")
    log.info("[진단] HTML 안 과정ID 후보 %d개, 예: %s", len(ids), ", ".join(ids[:3]))
    import os
    if os.environ.get("GITHUB_ACTIONS"):
        sample = (with_id or onclicks or [""])[0].replace("\n", " ")[:140]
        print(f"::notice title=목록 페이지 진단::제목 {title} / HTML {len(html or '')}자 / onclick {len(onclicks)}개"
              f"(과정ID {len(with_id)}) / 함수 {', '.join(funcs[:8])} / 예시 {sample}")


# 목록 화면의 KDT 하위 구분 체크박스 코드
KDT_TYPE_CODES = {
    "일반": "kdgtal_tgcr_yn",
    "단기": "kdgtal_tgcr_shrt_yn",
    "기초역량": "kdgtal_def_tgcr_yn",
    "AI캠퍼스": "kdgtal_tgcr_ai_cam_yn",
}


def search_inputs_hint(html: str) -> str:
    """개강일자 입력칸 값 (진단용)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html or "", "html.parser")
    out = []
    for el in soup.find_all("input"):
        name = el.get("name") or el.get("id") or ""
        if re.search(r"^(start|end)Date", name) and el.get("value"):
            out.append(f"{name}={el.get('value')}")
    return " ".join(dict.fromkeys(out))


def total_count_hint(html: str) -> str:
    flat = re.sub(r"<[^>]+>", " ", html or "")
    flat = re.sub(r"\s+", " ", flat)
    m = re.search(r"총\s*[\d,]+\s*건", flat)
    return m.group(0) if m else ""


class ListCrawler:
    def __init__(self, url: str = LIST_URL, max_pages: int = 300, headless: bool = True,
                 dump_dir: Optional[str] = None, click_fallback: bool = True,
                 start_date: Optional[str] = None, end_date: Optional[str] = None,
                 kdt_types: Optional[list[str]] = None):
        """start_date/end_date: 'YYYYMMDD' 개강일자 범위. kdt_types: KDT_TYPE_CODES의 값 목록."""
        self.start_date = start_date
        self.end_date = end_date
        self.kdt_types = kdt_types or []
        self.url = url
        self.max_pages = max_pages
        self.headless = headless
        self.dump_dir = dump_dir
        self.click_fallback = click_fallback

    def crawl(self) -> dict[tuple, CourseRef]:
        from playwright.sync_api import sync_playwright

        found: dict[tuple, CourseRef] = {}
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            ctx = browser.new_context(locale="ko-KR", viewport={"width": 1400, "height": 1000})
            page = ctx.new_page()
            page.set_default_timeout(45000)
            page.goto(self.url, wait_until="domcontentloaded")
            self._settle(page)
            if self.start_date or self.end_date or self.kdt_types:
                self._apply_search(page)
            self._set_page_size(page)

            prev_sig = None
            for page_no in range(1, self.max_pages + 1):
                html = self._wait_for_courses(page)
                if self.dump_dir and page_no <= 2:
                    self._dump(page, f"list_page{page_no}")
                if page_no == 1:
                    log_diagnostics(page.url, safe_title(page), html)
                refs = self._extract(page, ctx, html)
                sig = tuple(sorted(r.key for r in refs))
                if not refs:
                    log.warning("%d페이지에서 과정을 못 찾음 — 중단", page_no)
                    if page_no > 1:
                        log_diagnostics(page.url, safe_title(page), html)
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

                if not self._go_next(page, html, page_no + 1):
                    log.info("다음 페이지 없음")
                    break
                self._settle(page)
            browser.close()
        return found

    # ------------------------------------------------------------------
    def _settle(self, page) -> None:
        from playwright.sync_api import TimeoutError as PwTimeout
        for state in ("load", "networkidle"):
            try:
                page.wait_for_load_state(state, timeout=20000)
            except PwTimeout:
                pass
        page.wait_for_timeout(800)

    def _html(self, page) -> str:
        """페이지 HTML. 이동 중이라 실패하면 잠시 후 다시 시도."""
        for _ in range(5):
            try:
                return page.content()
            except Exception as e:  # noqa: BLE001 - 페이지 이동 중
                log.info("HTML 읽기 재시도: %s", str(e)[:120])
                page.wait_for_timeout(1500)
        return ""

    def _wait_for_courses(self, page, timeout_s: int = 15) -> str:
        """과정 식별자가 HTML에 나타날 때까지 기다린다 (화면이 늦게 그려지는 경우)."""
        html = ""
        for _ in range(timeout_s):
            html = self._html(page)
            if TRACSE_ID_ANY_RE.search(html):
                return html
            page.wait_for_timeout(1000)
        return html

    def _apply_search(self, page) -> None:
        """개강일자 범위와 KDT 하위 구분을 넣고 검색 버튼을 누른다 (DOM 직접 조작)."""
        script = (
            "(() => { const setv = (names, v) => { if (!v) return; for (const n of names) {"
            "   for (const el of document.querySelectorAll(`input[name='${n}'], #${n}`)) {"
            "     el.value = v; el.dispatchEvent(new Event('change', {bubbles: true})); } } };"
            " setv(['startDate', 'startDate_datepicker'], %r);"
            " setv(['endDate', 'endDate_datepicker'], %r);"
            " for (const c of %r) { const el = document.getElementById('trSe' + c); if (el && !el.checked) el.click(); }"
            " const btns = [...document.querySelectorAll('button, a, input[type=button], input[type=submit]')];"
            " const b = btns.find(e => /^\\s*검색(하기)?\\s*$/.test(e.innerText || e.value || '') && e.offsetParent !== null);"
            " if (b) b.click(); })()"
        ) % (self.start_date or "", self.end_date or "", list(self.kdt_types))
        try:
            page.evaluate(script)
        except Exception as e:  # noqa: BLE001 - 반환값 직렬화 오류는 무시
            log.info("검색 조건 스크립트 반환 오류(무시): %s", str(e)[:120])
        self._settle(page)
        html = self._html(page)
        msg = f"개강일자 {search_inputs_hint(html)} / 구분 {self.kdt_types or '전체'} / {total_count_hint(html)}"
        log.info("검색 조건 적용: %s", msg)
        _notice("목록 검색 조건", msg)

    def _set_page_size(self, page) -> None:
        """'100개씩' 선택 후 '적용'.

        고용24 페이지는 사이트 스크립트가 브라우저 기본 객체를 덮어써서 Playwright의
        select/텍스트 읽기 기능 일부가 깨진다. 그래서 페이지 안에서 값을 직접 넣고
        버튼을 누른 뒤, 결과는 반환값 대신 HTML로 확인한다.
        """
        html = self._html(page)
        info = find_page_size_control(html)
        if not info:
            log.info("페이지 크기 선택 상자 없음")
            _notice("페이지 크기", "100개 옵션이 있는 select 없음: " + page_size_hint(html))
            return
        select_id, value, button_id = info
        script = (
            "(() => { const s = document.getElementById(%r); if (!s) return;"
            " s.value = %r; s.dispatchEvent(new Event('change', {bubbles: true}));"
            " const b = %s; if (b) b.click(); })()"
        ) % (select_id, value,
             f"document.getElementById({button_id!r})" if button_id else
             "[...document.querySelectorAll('button, a, input')].find(e => /적용/.test(e.innerText || e.value || ''))")
        try:
            page.evaluate(script)
        except Exception as e:  # noqa: BLE001 - 반환값 직렬화 오류는 무시 (동작은 이미 실행됨)
            log.info("페이지 크기 스크립트 반환 오류(무시): %s", str(e)[:120])
        self._settle(page)
        after = self._html(page)
        ok = bool(re.search(rf'<option[^>]*value="{re.escape(value)}"[^>]*selected', after)) or \
            len(set(TRACSE_ID_ANY_RE.findall(after))) > 15
        log.info("페이지 크기 변경: %s", "성공" if ok else "확인 안 됨")
        if not ok:
            _notice("페이지 크기", "적용 후에도 100개로 바뀌지 않음 (10개씩 계속 진행)")

    def _go_next(self, page, html: str, target: int) -> bool:
        """HTML에서 target 페이지 링크(없으면 '다음')를 찾아 누른다."""
        how = find_page_link(html, target)
        if not how:
            return False
        kind, value = how
        try:
            if kind == "onclick":
                page.locator(f'[onclick="{css_escape(value)}"]').first.click()
            elif kind == "href":
                page.locator(f'a[href="{css_escape(value)}"]').first.click()
            else:  # 텍스트로
                page.locator("a, button").filter(has_text=re.compile(rf"^\s*{re.escape(value)}\s*$")).last.click()
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("페이지 이동 실패(%s): %s", target, str(e)[:200])
            return False

    def _extract(self, page, ctx, html: str) -> list[CourseRef]:
        refs = parse_list_html(html)
        if refs or not self.click_fallback:
            return refs
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
