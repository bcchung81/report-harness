#!/usr/bin/env python3
"""kordoc generate_document 산출 hwpx를 양식 정합으로 후처리한다 (stdlib-only).

기능:
  --star-footnote  ＊ 시작 문단의 run charPrIDRef를 참고 스타일(header.xml에서
                    height=1300·fontRef=맑은고딕 계열)로 치환한다. kordoc은 ※만
                    참고 스타일로 인식하고 전각 ＊는 본문 스타일로 남는 결함의 후처리
                    (기존 수동 zip 패치의 스크립트화, R011).
  --spacing         계층 전환 지점(발신줄→□/□→ㅇ/ㅇ→-/-→＊/※·＊→ㅇ(R038)/＊→표/블록
                    구분)의 간격을 원본 KCA 양식 실측값(스페이서 문단 방식)으로 재현한다.
                    전환 지점에 이미 빈 문단이 있으면 그 charPr 높이를 치환하고,
                    없으면 새 스페이서 문단을 삽입한다. 같은 묶음으로 표 캡션 내장
                    (hp:caption side=TOP, CENTER+볼드, R034)·표 배치 정렬(콘텐츠 표
                    RIGHT·배너 LEFT·제목 박스 CENTER, R015 정정·R035)·표 셀 텍스트
                    가운데 정렬(배너 제목 셀 제외)·붙임/참고 배너 제목 셀
                    양쪽정렬(R037)·본문 계층 양쪽정렬(R032)·본문 괄호 13pt(R033 —
                    run 경계 넘는 구간도 분할 처리, R039)·`==문구==` 노란 음영
                    하이라이트(shadeColor=#FFFF00+볼드, R040)·
                    서술 중 ＊ 위첨자(R031)·제목 박스 테두리 제거,
                    제목 박스 상단 여백 제거(앵커 줄간격 100%·outMargin top 0 — 상단
                    그라데이션 밴드 행은 양식 원형이므로 유지, R022)·표 캡션/셀
                    12pt(R023)·□ 절 제목 볼드(R024)·☞ 계층 띄어쓰기(R025)도 적용한다.
  --sender-size N   발신 줄(classify=="sending") 문단 run들의 charPr을 폰트는 유지한 채
                    높이만 N(pt)로 치환한다. --all에는 포함되지 않는다(값 필요, 별도 지정).
  --header-banner   KCA 머리말 배너(로고+슬로건 표)를 주입한다(R030). 주입 시 앵커 문단
                    lineSpacing을 100%로 강제하고 subList textWidth를 본문 폭으로
                    보정한다(R041 — 도너 앵커 150%가 본문을 4.6mm 밀어낸 실원인 정정).
                    hp:header 기존재 시 주입은 건너뛰되 앵커 기하 보정은 소급
                    적용한다(멱등). 자산: assets/kca-header-banner/.
  --all             --star-footnote·--spacing·--header-banner를 적용.

실측 근거(20260722 하네스-AI성과-관리체계 건, 양식 문단간격 추출 — 원 작업폴더는 보관 종료):
계층 간격은 paraPr 위/아래 간격이 아니라 글자크기를 줄인 빈 스페이서 문단으로 구현된다
(문단모양 자체 간격 필드는 전부 0). 확정값은 format-profile.kca.md §7에 승계돼 있다.
"""
import sys, json, re, copy, math, zipfile, pathlib, tempfile, os
import xml.etree.ElementTree as ET

NS = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
}
for _prefix, _uri in NS.items():
    ET.register_namespace(_prefix, _uri)

SECTION_RE = re.compile(r"^Contents/section\d+\.xml$")
SENDING_RE = re.compile(r"^<\s*'?\d")  # "< '26. 7. 22.(수), ... >" 형 발신 줄
CAPTION_RE = re.compile(r"^[\[<]")     # "[ 표 제목 ]" / "< 표 제목 >" 형 캡션
DAE, STAR, CHAM, DASH, ARROW = "□", "＊", "※", "-", "☞"
YO_CHARS = ("ㅇ", "○")

# 전환 유형 → (이름, 스페이서 charPr 높이 HWPUNIT = pt*100)
TRANSITIONS = {
    ("sending", "dae"): ("sending_to_dae", 1200),   # 제목표 직후 첫 □ 12pt (R060)
    ("dae", "yo"): ("dae_to_yo", 600),
    ("yo", "yo"): ("yo_to_yo", 600),            # 연속 ㅇ 문단 사이 (사용자 확정)
    ("dash", "yo"): ("dash_to_yo", 600),        # 하위 대시에서 다음 ㅇ 복귀
    ("yo", "dash"): ("yo_to_dash", 600),
    ("dash", "star"): ("dash_to_star", 300),
    ("yo", "star"): ("yo_to_star", 300),        # 양식 미실측 전환 — dash→star 3pt 유추 적용
    # ※·＊ 단서/각주 뒤 ㅇ 복귀(R038) — 양식·실무본 모두 해당 전환 실물이 없어 실측 불가,
    # R013 체계의 X→ㅇ 전환(□→ㅇ·ㅇ→ㅇ·대시→ㅇ)이 전부 6pt인 정합값 적용
    ("cham", "yo"): ("cham_to_yo", 600),
    ("star", "yo"): ("star_to_yo", 600),
    ("star", "caption"): ("star_to_caption", 1000),
    ("caption", "table"): ("caption_to_table", 300),   # 캡션→표 3pt(사용자 확정 '26.7.22)
    ("table", "cham"): ("table_to_cham", 300),         # 표→※ 3pt
    ("yo", "caption"): ("yo_to_caption", 600),         # 문단→캡션 6pt
    ("dash", "caption"): ("dash_to_caption", 600),
    ("cham", "caption"): ("cham_to_caption", 600),
    # 캡션 내장(R034) 후에는 캡션 자리에서 곧장 표를 만난다 — 기존 X→caption 값 승계
    ("yo", "table"): ("yo_to_table", 600),
    ("dash", "table"): ("dash_to_table", 600),
    ("cham", "table"): ("cham_to_table", 600),
    ("star", "table"): ("star_to_table", 1000),
    # ☞ 결론 유도 기호(R025) — ※·＊ 인접 간격(3pt) 준용
    ("cham", "arrow"): ("cham_to_arrow", 300),
    ("star", "arrow"): ("star_to_arrow", 300),
    ("yo", "arrow"): ("yo_to_arrow", 300),
    ("dash", "arrow"): ("dash_to_arrow", 300),
    ("table", "arrow"): ("table_to_arrow", 300),
}
BLOCK_BOUNDARY_HEIGHT = 800  # 두 번째 이후 □ 상단 8pt (R060 — 종전 1500)


class PostprocessError(Exception):
    """치명적 후처리 오류(참고 스타일 미발견 등) — exit 2 대상."""


def qn(prefix, local):
    return f"{{{NS[prefix]}}}{local}"


# ---------------------------------------------------------------------------
# 문단 판독
# ---------------------------------------------------------------------------

def para_text(p):
    """문단 직속 hp:run들의 hp:t 텍스트를 이어붙인다(중첩 표 셀 내부는 별도 문단이므로 무관)."""
    texts = []
    for run in p.findall(qn("hp", "run")):
        t = run.find(qn("hp", "t"))
        if t is not None and t.text:
            texts.append(t.text)
    return "".join(texts)


def para_has_table(p):
    for run in p.findall(qn("hp", "run")):
        if run.find(qn("hp", "tbl")) is not None:
            return True
    return False


def classify(p):
    """문단 선두 기호로 계층 유형을 판정한다."""
    if para_has_table(p):
        return "table"
    text = para_text(p).strip()
    if not text:
        return "empty"
    if text.startswith(DAE):
        return "dae"
    if text[0] in YO_CHARS:
        return "yo"
    if text.startswith(STAR):
        return "star"
    if text.startswith(CHAM):
        return "cham"
    if text.startswith(ARROW):
        return "arrow"
    if SENDING_RE.match(text):
        return "sending"
    if CAPTION_RE.match(text):
        return "caption"
    if text.startswith(DASH):
        return "dash"
    return "other"


def transition_for(prev_kind, next_kind):
    if prev_kind is None or next_kind is None:
        return None
    key = (prev_kind, next_kind)
    if key in TRANSITIONS:
        return TRANSITIONS[key]
    if next_kind == "dae" and prev_kind != "sending":
        return ("block_boundary", BLOCK_BOUNDARY_HEIGHT)
    return None


# ---------------------------------------------------------------------------
# ＊ 각주 charPr 치환
# ---------------------------------------------------------------------------

def _hangul_fontfaces(header_root):
    """{font id: face} — 최초(HANGUL) lang 테이블만 사용(전 lang 동일 face 목록)."""
    fonts = {}
    for ff in header_root.iter(qn("hh", "fontface")):
        for f in ff.findall(qn("hh", "font")):
            fonts.setdefault(f.get("id"), f.get("face"))
        break
    return fonts


def find_ref_charpr_id(header_root):
    """height=1300·fontRef=맑은고딕(공백 없는 표기 우선) charPr id를 탐색한다."""
    fonts = _hangul_fontfaces(header_root)
    fallback = None
    for cp in header_root.iter(qn("hh", "charPr")):
        if cp.get("height") != "1300":
            continue
        fr = cp.find(qn("hh", "fontRef"))
        if fr is None:
            continue
        face = fonts.get(fr.get("hangul"), "")
        if face == "맑은고딕":
            return cp.get("id")
        if fallback is None and "맑은고딕" in face.replace(" ", ""):
            fallback = cp.get("id")
    return fallback


def apply_star_footnote(header_root, section_roots):
    ref_id = find_ref_charpr_id(header_root)
    if ref_id is None:
        raise PostprocessError(
            "참고 charPr(header.xml height=1300·fontRef=맑은고딕 계열)을 찾지 못했습니다"
        )
    stars_found = 0
    runs_changed = 0
    for sec_root in section_roots:
        for p in sec_root.iter(qn("hp", "p")):
            if not para_text(p).strip().startswith(STAR):
                continue
            stars_found += 1
            for run in p.findall(qn("hp", "run")):
                if run.get("charPrIDRef") != ref_id:
                    run.set("charPrIDRef", ref_id)
                    runs_changed += 1
    return {"ref_charpr_id": ref_id, "stars_found": stars_found, "runs_changed": runs_changed}


# ---------------------------------------------------------------------------
# 계층 간격 스페이서
# ---------------------------------------------------------------------------

def ensure_charpr_height(header_root, height):
    """height(HWPUNIT)와 일치하는 charPr id를 재사용하거나, 없으면 id0을 복제해 새로 등록한다."""
    height_s = str(height)
    charprops = header_root.find(f".//{qn('hh', 'charProperties')}")
    for cp in charprops.findall(qn("hh", "charPr")):
        if cp.get("height") == height_s:
            return cp.get("id")
    template = charprops.find(qn("hh", "charPr"))
    new_cp = copy.deepcopy(template)
    max_id = max(int(cp.get("id")) for cp in charprops.findall(qn("hh", "charPr")))
    new_id = str(max_id + 1)
    new_cp.set("id", new_id)
    new_cp.set("height", height_s)
    charprops.append(new_cp)
    charprops.set("itemCnt", str(int(charprops.get("itemCnt", "0")) + 1))
    return new_id


def ensure_neutral_parapr(header_root):
    """margin.prev=margin.next=0인 paraPr id를 재사용하거나, 없으면 새로 등록한다.
    (스페이서 문단은 문단 자체 간격이 아니라 글자크기로만 간격을 내야 하므로 margin은 0이어야 한다.)"""
    paraprops = header_root.find(f".//{qn('hh', 'paraProperties')}")
    for pp in paraprops.findall(qn("hh", "paraPr")):
        margin = pp.find(qn("hh", "margin"))
        if margin is None:
            continue
        prev = margin.find(qn("hc", "prev"))
        nxt = margin.find(qn("hc", "next"))
        if prev is not None and nxt is not None and prev.get("value") == "0" and nxt.get("value") == "0":
            return pp.get("id")
    template = paraprops.find(qn("hh", "paraPr"))
    new_pp = copy.deepcopy(template)
    max_id = max(int(pp.get("id")) for pp in paraprops.findall(qn("hh", "paraPr")))
    new_id = str(max_id + 1)
    new_pp.set("id", new_id)
    margin = new_pp.find(qn("hh", "margin"))
    if margin is not None:
        for tag in ("intent", "left", "right", "prev", "next"):
            el = margin.find(qn("hc", tag))
            if el is not None:
                el.set("value", "0")
    paraprops.append(new_pp)
    paraprops.set("itemCnt", str(int(paraprops.get("itemCnt", "0")) + 1))
    return new_id


def make_spacer_paragraph(parapr_id, charpr_id):
    p = ET.Element(qn("hp", "p"), {"paraPrIDRef": parapr_id, "styleIDRef": "0"})
    run = ET.SubElement(p, qn("hp", "run"), {"charPrIDRef": charpr_id})
    ET.SubElement(run, qn("hp", "t"))
    return p


def apply_spacing_section(header_root, sec_root):
    """sec_root(hs:sec)의 최상위 hp:p 시퀀스를 훑어 전환 지점마다 스페이서를 적용한다.
    반환: 적용 이벤트 목록({"type": "insert"|"modify", "transition": ..., "height": ...})."""
    p_tag = qn("hp", "p")
    children = list(sec_root)
    kinds = [classify(c) if c.tag == p_tag else None for c in children]
    n = len(children)
    out = []
    events = []
    prev_content_kind = None
    for i, child in enumerate(children):
        if child.tag != p_tag:
            out.append(child)
            continue
        kind = kinds[i]
        if kind == "empty":
            next_kind = None
            for j in range(i + 1, n):
                if children[j].tag == p_tag and kinds[j] != "empty":
                    next_kind = kinds[j]
                    break
            trans = transition_for(prev_content_kind, next_kind)
            if trans:
                name, height = trans
                cp_id = ensure_charpr_height(header_root, height)
                run = child.find(qn("hp", "run"))
                if run is not None:
                    run.set("charPrIDRef", cp_id)
                events.append({"type": "modify", "transition": name, "height": height})
            out.append(child)
            continue
        prev_item_is_empty = i > 0 and kinds[i - 1] == "empty"
        if prev_content_kind is not None and not prev_item_is_empty:
            trans = transition_for(prev_content_kind, kind)
            if trans:
                name, height = trans
                cp_id = ensure_charpr_height(header_root, height)
                pp_id = ensure_neutral_parapr(header_root)
                out.append(make_spacer_paragraph(pp_id, cp_id))
                events.append({"type": "insert", "transition": name, "height": height})
        out.append(child)
        prev_content_kind = kind
    sec_root[:] = out
    return events


def apply_spacing(header_root, section_roots):
    events = []
    for sec_root in section_roots:
        events.extend(apply_spacing_section(header_root, sec_root))
    return {"events": events, "inserted": sum(1 for e in events if e["type"] == "insert"),
            "modified": sum(1 for e in events if e["type"] == "modify")}


def ensure_aligned_clone(header_root, base_id, horizontal, cache):
    """base paraPr을 복제해 align horizontal=horizontal인 paraPr id를 반환(중복 생성 방지 캐시)."""
    key = (base_id, horizontal)
    if key in cache:
        return cache[key]
    paraprops = header_root.find(f".//{qn('hh', 'paraProperties')}")
    base = None
    for pp in paraprops.findall(qn("hh", "paraPr")):
        if pp.get("id") == base_id:
            base = pp
            break
    if base is None:
        return base_id
    align = base.find(qn("hh", "align"))
    if align is not None and align.get("horizontal") == horizontal:
        cache[key] = base_id
        return base_id
    new_pp = copy.deepcopy(base)
    max_id = max(int(pp.get("id")) for pp in paraprops.findall(qn("hh", "paraPr")))
    new_id = str(max_id + 1)
    new_pp.set("id", new_id)
    na = new_pp.find(qn("hh", "align"))
    if na is not None:
        na.set("horizontal", horizontal)
    paraprops.append(new_pp)
    paraprops.set("itemCnt", str(len(paraprops.findall(qn("hh", "paraPr")))))
    cache[key] = new_id
    return new_id


def ensure_centered_clone(header_root, base_id, cache):
    """(호환 래퍼) CENTER 정렬 복제본."""
    return ensure_aligned_clone(header_root, base_id, "CENTER", cache)


def apply_table_alignment(header_root, section_roots):
    """표 래퍼 문단(treatAsChar 표) 배치 정렬(R015 정정 — 사용자 확정 '26.7.28):
    본문 콘텐츠 표 RIGHT · 붙임/참고 배너 표 LEFT(R035) · 제목 박스 CENTER 유지.
    잔존 캡션 문단(내장 실패분)은 CENTER를 유지한다."""
    p_tag = qn("hp", "p")
    cache = {}
    counts = {"caption": 0, "table_right": 0, "banner_left": 0, "title_center": 0}
    seen_dae = False
    for sec_root in section_roots:
        for child in sec_root:
            if child.tag != p_tag:
                continue
            kind = classify(child)
            if kind == "dae":
                seen_dae = True
                continue
            if kind not in ("caption", "table"):
                continue
            base_id = child.get("paraPrIDRef")
            if base_id is None:
                continue
            if kind == "caption":
                horizontal, label = "CENTER", "caption"
            else:
                tbls = [tbl for run in child.findall(qn("hp", "run"))
                        for tbl in run.findall(qn("hp", "tbl"))]
                if not seen_dae:
                    horizontal, label = "CENTER", "title_center"
                elif any(_is_banner_table(t) for t in tbls):
                    horizontal, label = "LEFT", "banner_left"
                else:
                    horizontal, label = "RIGHT", "table_right"
            new_id = ensure_aligned_clone(header_root, base_id, horizontal, cache)
            if new_id != base_id:
                child.set("paraPrIDRef", new_id)
            counts[label] += 1
    return {"aligned": counts,
            "new_parapr": {f"{k[0]}->{k[1]}": v for k, v in cache.items() if k[0] != v}}


def _iter_content_tables(section_roots):
    """(hp:tbl 요소, is_title_box) 쌍을 문서 순서대로 생성한다.
    첫 □ 문단 이전에 나오는 표는 제목 박스(is_title_box=True)로 판정한다."""
    p_tag = qn("hp", "p")
    seen_dae = False
    for sec_root in section_roots:
        for child in sec_root:
            if child.tag != p_tag:
                continue
            kind = classify(child)
            if kind == "dae":
                seen_dae = True
                continue
            if kind != "table":
                continue
            for run in child.findall(qn("hp", "run")):
                tbl = run.find(qn("hp", "tbl"))
                if tbl is not None:
                    yield tbl, not seen_dae


def apply_center_cell_text(header_root, section_roots):
    """본문 콘텐츠 표(제목 박스 제외)의 hp:tbl 내부 subList 문단 전부를 가운데 정렬한다.
    붙임·참고 배너 표(R027)의 제목 셀(3번째)은 제외 — R037 양쪽정렬(JUSTIFY)은
    apply_annex_banner가 배정한다(라벨·스페이서 셀은 CENTER 현행 유지)."""
    p_tag = qn("hp", "p")
    cache = {}
    tables = 0
    paragraphs = 0
    for tbl, is_title in _iter_content_tables(section_roots):
        if is_title:
            continue
        skip_pids = set()
        if _is_banner_table(tbl):
            title_cell = _banner_sorted_cells(tbl)[-1]
            skip_pids = {id(p) for p in title_cell.iter(p_tag)}
        tables += 1
        for cell_p in tbl.iter(p_tag):
            if id(cell_p) in skip_pids:
                continue
            base_id = cell_p.get("paraPrIDRef")
            if base_id is None:
                continue
            new_id = ensure_centered_clone(header_root, base_id, cache)
            if new_id != base_id:
                cell_p.set("paraPrIDRef", new_id)
            paragraphs += 1
    return {"tables": tables, "paragraphs": paragraphs}


BORDER_TAGS = ("leftBorder", "rightBorder", "topBorder", "bottomBorder")


def ensure_borderless_variant(header_root, base_id, cache):
    """base_id borderFill의 배경(fillBrush·그라데이션)은 보존하고 4변 테두리만
    NONE으로 바꾼 변형 id를 반환한다 — hwpx는 테두리·배경이 borderFill 한 엔티티라
    통째 교체 시 배경이 소실되므로, 원본별 무테두리 변형을 복제 생성한다."""
    if base_id in cache:
        return cache[base_id]
    borderfills = header_root.find(f".//{qn('hh', 'borderFills')}")
    base = None
    for bf in borderfills.findall(qn("hh", "borderFill")):
        if bf.get("id") == base_id:
            base = bf
            break
    if base is None:
        cache[base_id] = base_id
        return base_id
    if all((el := base.find(qn("hh", t))) is not None and el.get("type") == "NONE"
           for t in BORDER_TAGS):
        cache[base_id] = base_id
        return base_id
    new_bf = copy.deepcopy(base)
    max_id = max(int(bf.get("id")) for bf in borderfills.findall(qn("hh", "borderFill")))
    new_id = str(max_id + 1)
    new_bf.set("id", new_id)
    for t in BORDER_TAGS:
        el = new_bf.find(qn("hh", t))
        if el is not None:
            el.set("type", "NONE")
    borderfills.append(new_bf)
    borderfills.set("itemCnt", str(int(borderfills.get("itemCnt", "0")) + 1))
    cache[base_id] = new_id
    return new_id


def apply_title_box_borderless(header_root, section_roots):
    """제목 박스(첫 □ 이전 표)의 hp:tbl·hp:tc 등 borderFillIDRef를 '원본 배경 보존 +
    테두리만 NONE' 변형으로 교체한다(그라데이션 등 fillBrush 유지)."""
    title_tables = [tbl for tbl, is_title in _iter_content_tables(section_roots) if is_title]
    if not title_tables:
        return {"found": False, "fills_replaced": 0}
    cache = {}
    replaced = 0
    for tbl in title_tables:
        for el in tbl.iter():
            ref = el.get("borderFillIDRef")
            if ref is None:
                continue
            new_ref = ensure_borderless_variant(header_root, ref, cache)
            if new_ref != ref:
                el.set("borderFillIDRef", new_ref)
                replaced += 1
    return {"found": True, "fills_replaced": replaced,
            "variants": {k: v for k, v in cache.items() if k != v}}


def ensure_linespacing_parapr(header_root, base_id, percent, cache):
    """base_id paraPr의 lineSpacing value만 percent로 바꾼 복제본 id를 반환한다."""
    key = (base_id, percent)
    if key in cache:
        return cache[key]
    paraprops = header_root.find(f".//{qn('hh', 'paraProperties')}")
    base = None
    for pp in paraprops.findall(qn("hh", "paraPr")):
        if pp.get("id") == base_id:
            base = pp
            break
    if base is None:
        cache[key] = base_id
        return base_id
    ls = base.find(qn("hh", "lineSpacing"))
    if ls is not None and ls.get("value") == str(percent):
        cache[key] = base_id
        return base_id
    new_pp = copy.deepcopy(base)
    max_id = max(int(pp.get("id")) for pp in paraprops.findall(qn("hh", "paraPr")))
    new_id = str(max_id + 1)
    new_pp.set("id", new_id)
    nls = new_pp.find(qn("hh", "lineSpacing"))
    if nls is not None:
        nls.set("value", str(percent))
    paraprops.append(new_pp)
    paraprops.set("itemCnt", str(len(paraprops.findall(qn("hh", "paraPr")))))
    cache[key] = new_id
    return new_id


def apply_title_box_topgap(header_root, section_roots):
    """제목 박스(첫 □ 이전 표) 위 여백을 제거한다(R022 개정 '26.7.24 — 행 삭제 금지).
    양식 실측(20260722건): 제목표는 3행 원형이고 상단 얇은 행(3.8pt)은 그라데이션 배경
    밴드이므로 유지해야 한다. 여백의 실원인은 앵커 문단(treatAsChar 표를 담은 문단)의
    줄간격 160%가 표 높이의 60%를 여백으로 벌리는 것 — 앵커 문단 줄간격을 100%로 치환하고
    표 outMargin top을 0으로 조인다."""
    p_tag = qn("hp", "p")
    cache = {}
    anchors_fixed = 0
    outmargins_fixed = 0
    title_ids = set()
    for tbl, is_title in _iter_content_tables(section_roots):
        if not is_title:
            continue
        title_ids.add(id(tbl))
        out = tbl.find(qn("hp", "outMargin"))
        if out is not None and out.get("top") not in (None, "0"):
            out.set("top", "0")
            outmargins_fixed += 1
    if not title_ids:
        return {"anchors_fixed": 0, "outmargins_fixed": 0}
    for sec_root in section_roots:
        for child in sec_root:
            if child.tag != p_tag:
                continue
            has_title = any(
                id(tbl) in title_ids
                for run in child.findall(qn("hp", "run"))
                for tbl in run.findall(qn("hp", "tbl"))
            )
            if not has_title:
                continue
            base_id = child.get("paraPrIDRef")
            if base_id is None:
                continue
            new_id = ensure_linespacing_parapr(header_root, base_id, 100, cache)
            if new_id != base_id:
                child.set("paraPrIDRef", new_id)
                anchors_fixed += 1
    return {"anchors_fixed": anchors_fixed, "outmargins_fixed": outmargins_fixed}


BANNER_LABEL_RE = re.compile(r"^(붙\s*임\s*\d*|참고\s*\d*)$")


def _is_banner_table(tbl):
    """붙임·참고 배너 표(1행 3열, 첫 셀이 '붙 임'/'붙임 N'/'참고N') 판정 (R009·R027)."""
    rows = tbl.findall(qn("hp", "tr"))
    if len(rows) != 1:
        return False
    cells = rows[0].findall(qn("hp", "tc"))
    if len(cells) != 3:
        return False
    first_texts = [t.text or "" for t in cells[0].iter(qn("hp", "t"))]
    return bool(BANNER_LABEL_RE.match("".join(first_texts).strip()))


def _banner_sorted_cells(tbl):
    """배너 표(1행 3열)의 셀을 colAddr 순으로 반환한다 — [라벨, 스페이서, 제목]."""
    row = tbl.find(qn("hp", "tr"))
    cells = row.findall(qn("hp", "tc"))
    return sorted(
        cells,
        key=lambda tc: int(
            tc.find(qn("hp", "cellAddr")).get("colAddr", "0")
            if tc.find(qn("hp", "cellAddr")) is not None else 0))


def apply_caption_table_font(header_root, section_roots, pt=12):
    """표 캡션 문단과 본문 콘텐츠 표(제목 박스·붙임/참고 배너 제외) 셀 문단의 charPr 크기를
    pt로 치환한다(R023 — 사용자 확정 '26.7.24). 폰트는 유지하고 높이만 바꾼다."""
    height = int(round(pt * 100))
    p_tag = qn("hp", "p")
    cache = {}
    caption_runs = 0
    cell_runs = 0
    for sec_root in section_roots:
        for child in sec_root:
            if child.tag != p_tag or classify(child) != "caption":
                continue
            for run in child.findall(qn("hp", "run")):
                base_id = run.get("charPrIDRef")
                if base_id is None:
                    continue
                new_id = ensure_charpr_sized(header_root, base_id, height, cache)
                if new_id != base_id:
                    run.set("charPrIDRef", new_id)
                    caption_runs += 1
    for tbl, is_title in _iter_content_tables(section_roots):
        if is_title or _is_banner_table(tbl):
            continue
        for cell_p in tbl.iter(p_tag):
            for run in cell_p.findall(qn("hp", "run")):
                base_id = run.get("charPrIDRef")
                if base_id is None:
                    continue
                new_id = ensure_charpr_sized(header_root, base_id, height, cache)
                if new_id != base_id:
                    run.set("charPrIDRef", new_id)
                    cell_runs += 1
    return {"height": height, "caption_runs_changed": caption_runs,
            "cell_runs_changed": cell_runs}


def ensure_charpr_font_size(header_root, base_id, face, height, cache):
    """base_id charPr을 전 lang fontRef=face 폰트 id·height로 바꾼 복제본 id를 반환한다."""
    key = (base_id, face, height)
    if key in cache:
        return cache[key]
    fonts = _hangul_fontfaces(header_root)
    font_id = next((fid for fid, f in fonts.items() if f == face), None)
    if font_id is None:
        cache[key] = base_id
        return base_id
    charprops = header_root.find(f".//{qn('hh', 'charProperties')}")
    base = None
    for cp in charprops.findall(qn("hh", "charPr")):
        if cp.get("id") == base_id:
            base = cp
            break
    if base is None:
        cache[key] = base_id
        return base_id
    fr = base.find(qn("hh", "fontRef"))
    if (base.get("height") == str(height) and fr is not None
            and fr.get("hangul") == font_id):
        cache[key] = base_id
        return base_id
    new_cp = copy.deepcopy(base)
    max_id = max(int(cp.get("id")) for cp in charprops.findall(qn("hh", "charPr")))
    new_id = str(max_id + 1)
    new_cp.set("id", new_id)
    new_cp.set("height", str(height))
    nfr = new_cp.find(qn("hh", "fontRef"))
    if nfr is not None:
        for lang in ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user"):
            if nfr.get(lang) is not None:
                nfr.set(lang, font_id)
    charprops.append(new_cp)
    charprops.set("itemCnt", str(int(charprops.get("itemCnt", "0")) + 1))
    cache[key] = new_id
    return new_id


def ensure_pagebreak_parapr(header_root, base_id, cache):
    """base_id paraPr의 breakSetting pageBreakBefore="1" 복제본 id를 반환한다."""
    if base_id in cache:
        return cache[base_id]
    paraprops = header_root.find(f".//{qn('hh', 'paraProperties')}")
    base = None
    for pp in paraprops.findall(qn("hh", "paraPr")):
        if pp.get("id") == base_id:
            base = pp
            break
    if base is None:
        cache[base_id] = base_id
        return base_id
    bs = base.find(qn("hh", "breakSetting"))
    if bs is not None and bs.get("pageBreakBefore") == "1":
        cache[base_id] = base_id
        return base_id
    new_pp = copy.deepcopy(base)
    max_id = max(int(pp.get("id")) for pp in paraprops.findall(qn("hh", "paraPr")))
    new_id = str(max_id + 1)
    new_pp.set("id", new_id)
    nbs = new_pp.find(qn("hh", "breakSetting"))
    if nbs is None:
        nbs = ET.SubElement(new_pp, qn("hh", "breakSetting"))
    nbs.set("pageBreakBefore", "1")
    paraprops.append(new_pp)
    paraprops.set("itemCnt", str(len(paraprops.findall(qn("hh", "paraPr")))))
    cache[base_id] = new_id
    return new_id


# 양식 '참고1' 배너 셀 스타일 실측 (250609 양식 hwp OLE 디코딩, '26.7.24 재실측 확정 —
# COLORREF는 0x00BBGGRR(리틀엔디언)이므로 저장 hex를 그대로 읽으면 R/B가 뒤집힌다.
# 최초 실측('26.7.24 오전)이 이 바이트 순서를 놓쳐 #60171B/#632D2B(적갈)로 오기록했고,
# 실제 양식은 남색 계열이다. 교차검증: 본문 표 헤더 bf14=#D2EBEE(연하늘) 음영 일치.
#   라벨 셀(bf17): 4변 SOLID 0.5mm #1B1760 + 채움 #2B2D63, 글자 흰색 HY헤드라인M 16pt
#   스페이서(bf7): 좌변만 SOLID 0.5mm #1B1760, 채움 없음
#   제목 셀(bf8):  상·하변 SOLID 0.5mm #1B1760, 채움 없음, 글자 HY헤드라인M 16pt
#   행 높이 28.3pt(2830) · 셀 폭 라벨 5968(21.1mm)/스페이서 565(2.0mm)/제목 잔여
BANNER_LINE = ("SOLID", "0.5 mm", "#1B1760")
BANNER_NONE = ("NONE", "0.1 mm", "#000000")
BANNER_CELL_SPECS = [
    {"borders": {"left": BANNER_LINE, "right": BANNER_LINE,
                 "top": BANNER_LINE, "bottom": BANNER_LINE}, "fill": "#2B2D63"},
    {"borders": {"left": BANNER_LINE, "right": BANNER_NONE,
                 "top": BANNER_NONE, "bottom": BANNER_NONE}, "fill": None},
    {"borders": {"left": BANNER_NONE, "right": BANNER_NONE,
                 "top": BANNER_LINE, "bottom": BANNER_LINE}, "fill": None},
]
BANNER_ROW_HEIGHT = 2830
BANNER_CELL_WIDTHS = [5968, 565]  # 라벨·스페이서 실측 폭, 제목 셀은 표 폭 잔여


def _borderfill_matches(bf, spec):
    for side, (btype, bwidth, bcolor) in spec["borders"].items():
        el = bf.find(qn("hh", f"{side}Border"))
        if el is None or el.get("type") != btype:
            return False
        if btype != "NONE" and (el.get("width") != bwidth or el.get("color") != bcolor):
            return False
    brush = bf.find(f"{qn('hc', 'fillBrush')}/{qn('hc', 'winBrush')}")
    if spec["fill"] is None:
        return brush is None
    return brush is not None and brush.get("faceColor") == spec["fill"]


def ensure_banner_fill(header_root, spec, cache):
    """spec(4변 테두리 + 채움색)에 맞는 borderFill id를 재사용 또는 복제 생성한다."""
    key = str(spec)
    if key in cache:
        return cache[key]
    borderfills = header_root.find(f".//{qn('hh', 'borderFills')}")
    for bf in borderfills.findall(qn("hh", "borderFill")):
        if _borderfill_matches(bf, spec):
            cache[key] = bf.get("id")
            return bf.get("id")
    template = borderfills.find(qn("hh", "borderFill"))
    new_bf = copy.deepcopy(template)
    max_id = max(int(bf.get("id")) for bf in borderfills.findall(qn("hh", "borderFill")))
    new_id = str(max_id + 1)
    new_bf.set("id", new_id)
    for side, (btype, bwidth, bcolor) in spec["borders"].items():
        el = new_bf.find(qn("hh", f"{side}Border"))
        if el is not None:
            el.set("type", btype)
            el.set("width", bwidth)
            el.set("color", bcolor)
    old_brush = new_bf.find(qn("hc", "fillBrush"))
    if old_brush is not None:
        new_bf.remove(old_brush)
    if spec["fill"] is not None:
        brush = ET.SubElement(new_bf, qn("hc", "fillBrush"))
        ET.SubElement(brush, qn("hc", "winBrush"),
                      {"faceColor": spec["fill"], "hatchColor": "#999999", "alpha": "0"})
    borderfills.append(new_bf)
    borderfills.set("itemCnt", str(int(borderfills.get("itemCnt", "0")) + 1))
    cache[key] = new_id
    return new_id


def ensure_charpr_color(header_root, base_id, color, cache):
    """base_id charPr의 textColor만 color로 바꾼 복제본 id를 반환한다."""
    key = (base_id, color)
    if key in cache:
        return cache[key]
    charprops = header_root.find(f".//{qn('hh', 'charProperties')}")
    base = None
    for cp in charprops.findall(qn("hh", "charPr")):
        if cp.get("id") == base_id:
            base = cp
            break
    if base is None or base.get("textColor") == color:
        cache[key] = base_id
        return base_id
    new_cp = copy.deepcopy(base)
    max_id = max(int(cp.get("id")) for cp in charprops.findall(qn("hh", "charPr")))
    new_id = str(max_id + 1)
    new_cp.set("id", new_id)
    new_cp.set("textColor", color)
    charprops.append(new_cp)
    charprops.set("itemCnt", str(int(charprops.get("itemCnt", "0")) + 1))
    cache[key] = new_id
    return new_id


def apply_annex_banner(header_root, section_roots):
    """붙임·참고 배너를 양식 참고 블록 정합으로 처리한다(R027 — 사용자 확정 '26.7.24):
    ① 배너 앵커 문단 pageBreakBefore=1 (별도 페이지 시작)
    ② 배너 셀 글자 HY헤드라인M 16pt (라벨 셀은 흰색)
    ③ 셀별 테두리·채움을 양식 '참고1' 실측값으로 배정 (BANNER_CELL_SPECS)
    ④ 행 높이 28.3pt · 셀 폭 라벨 5968/스페이서 565/제목 잔여 (BANNER_CELL_WIDTHS)
    ⑤ 제목 셀(3번째) 문단 정렬 JUSTIFY(양쪽 정렬) — R037, 사용자 확정 '26.7.28.
       라벨·스페이서 셀은 CENTER 유지(apply_center_cell_text가 배정, 제목 셀은 거기서 제외)."""
    p_tag = qn("hp", "p")
    char_cache = {}
    color_cache = {}
    pb_cache = {}
    fill_cache = {}
    align_cache = {}
    banners = 0
    cell_runs = 0
    fills_set = 0
    title_justified = 0
    for sec_root in section_roots:
        for child in sec_root:
            if child.tag != p_tag:
                continue
            banner_tbls = [
                tbl for run in child.findall(qn("hp", "run"))
                for tbl in run.findall(qn("hp", "tbl"))
                if _is_banner_table(tbl)
            ]
            if not banner_tbls:
                continue
            banners += len(banner_tbls)
            base_pp = child.get("paraPrIDRef")
            if base_pp is not None:
                new_pp = ensure_pagebreak_parapr(header_root, base_pp, pb_cache)
                if new_pp != base_pp:
                    child.set("paraPrIDRef", new_pp)
            for tbl in banner_tbls:
                cells_sorted = _banner_sorted_cells(tbl)
                sz = tbl.find(qn("hp", "sz"))
                if sz is not None and sz.get("height") is not None:
                    sz.set("height", str(BANNER_ROW_HEIGHT))
                total_w = sum(
                    int(tc.find(qn("hp", "cellSz")).get("width", "0"))
                    for tc in cells_sorted if tc.find(qn("hp", "cellSz")) is not None)
                cell_widths = None
                if len(cells_sorted) == 3 and total_w > sum(BANNER_CELL_WIDTHS):
                    cell_widths = BANNER_CELL_WIDTHS + [total_w - sum(BANNER_CELL_WIDTHS)]
                for idx, tc in enumerate(cells_sorted):
                    spec = BANNER_CELL_SPECS[min(idx, len(BANNER_CELL_SPECS) - 1)]
                    fill_id = ensure_banner_fill(header_root, spec, fill_cache)
                    if tc.get("borderFillIDRef") != fill_id:
                        tc.set("borderFillIDRef", fill_id)
                        fills_set += 1
                    csz = tc.find(qn("hp", "cellSz"))
                    if csz is not None:
                        csz.set("height", str(BANNER_ROW_HEIGHT))
                        if cell_widths is not None:
                            csz.set("width", str(cell_widths[idx]))
                    for cell_p in tc.iter(p_tag):
                        if idx == 2:  # 제목 셀 문단 → JUSTIFY (R037)
                            base_pid = cell_p.get("paraPrIDRef")
                            if base_pid is not None:
                                new_pid = ensure_aligned_clone(
                                    header_root, base_pid, "JUSTIFY", align_cache)
                                if new_pid != base_pid:
                                    cell_p.set("paraPrIDRef", new_pid)
                                    title_justified += 1
                        for run in cell_p.findall(qn("hp", "run")):
                            base_id = run.get("charPrIDRef")
                            if base_id is None:
                                continue
                            new_id = ensure_charpr_font_size(
                                header_root, base_id, "HY헤드라인M", 1600, char_cache)
                            if idx == 0:
                                new_id = ensure_charpr_color(
                                    header_root, new_id, "#FFFFFF", color_cache)
                            if new_id != base_id:
                                run.set("charPrIDRef", new_id)
                                cell_runs += 1
    return {"banners": banners, "cell_runs_changed": cell_runs, "fills_set": fills_set,
            "title_justified": title_justified}


# KCA 머리말 배너(로고+슬로건) 주입 자산 — 실무 문서 실측 이식본 (R030, '26.7.28)
# 원천: 한컴 저장 실사용 보고서(260331_AI OCR 결과 보고.hwpx)의 hp:header ctrl 서브트리.
# 양식 원형(250609 표준양식 .hwp)도 Section0 첫 문단에 동일 구조(head ctrl: 1×2 표 + gso 2개)를 가진다.
BANNER_ASSETS_DIR = pathlib.Path(__file__).resolve().parent.parent / "assets" / "kca-header-banner"
BANNER_BIN_ITEMS = (
    ("kcaHdrLogo", "kcaHdrLogo.png", "image/png"),      # KCA 로고+기관명 (좌측 셀)
    ("kcaHdrSlogan", "kcaHdrSlogan.bmp", "image/bmp"),  # Digital WAVE 슬로건 (우측 셀)
)


def _max_id(container, tag):
    vals = [int(el.get("id")) for el in container.findall(tag)
            if (el.get("id") or "").isdigit()]
    return max(vals) if vals else 0


def _fix_header_anchor_geometry(header_root, section_roots, header_el):
    """머리말 배너 앵커 문단의 lineSpacing을 PERCENT 100으로 강제하고, 머리말 subList
    textWidth를 현재 문서 본문 폭으로 보정한다(R041 — '26.7.28 실기동 A/B 실측 확정).

    제목표 상단 여백의 실원인: 도너(260331 실무본)에서 이식된 앵커 paraPr의
    lineSpacing 150%가 treatAsChar 배너 표(11.3mm)의 줄 높이를 17.0mm로 부풀려
    머리말 영역 15mm를 초과시키고, 한글이 신규 조판 시 본문 시작을 그만큼(≈4.6mm)
    밀어낸다. 100% 치환 시 제목표 위치가 실무본과 0.3mm 이내로 일치한다.
    배너 셀 내부 문단 paraPr(160%)은 건드리지 않는다 — 앵커 문단만 대상.
    textWidth 51026(=도너 좌우 15mm 문서의 본문 폭 180mm)도 현 문서 pagePr 실측
    본문 폭으로 치환한다. 이미 정합이면 무변경(멱등)."""
    result = {"anchor_parapr": None, "linespacing_fixed": 0, "textwidth_fixed": None}
    sub = header_el.find(qn("hp", "subList"))
    if sub is None:
        return result
    anchor_p = next((p for p in sub.findall(qn("hp", "p"))
                     if any(r.find(qn("hp", "tbl")) is not None
                            for r in p.findall(qn("hp", "run")))), None)
    if anchor_p is not None:
        aid = anchor_p.get("paraPrIDRef")
        result["anchor_parapr"] = aid
        for pp in header_root.iter(qn("hh", "paraPr")):
            if pp.get("id") != aid:
                continue
            # hp:switch 양 분기(hp:case·hp:default)의 lineSpacing을 모두 치환
            for ls in pp.iter(qn("hh", "lineSpacing")):
                if ls.get("type") != "PERCENT" or ls.get("value") != "100":
                    ls.set("type", "PERCENT")
                    ls.set("value", "100")
                    result["linespacing_fixed"] += 1
            break
    text_w = 0
    for sec_root in section_roots:
        for pagepr in sec_root.iter(qn("hp", "pagePr")):
            margin = pagepr.find(qn("hp", "margin"))
            if margin is not None:
                text_w = (int(pagepr.get("width", "0")) - int(margin.get("left", "0"))
                          - int(margin.get("right", "0")) - int(margin.get("gutter", "0")))
            break
        if text_w:
            break
    if text_w > 0 and sub.get("textWidth") not in (None, str(text_w)):
        result["textwidth_fixed"] = {"old": sub.get("textWidth"), "new": text_w}
        sub.set("textWidth", str(text_w))
    return result


def apply_header_banner(header_root, section_roots, data):
    """KCA 머리말 배너(로고 표)를 주입한다(R030 — '26.7.28 제목표 상단여백 3차 조사 확정).

    제목표 상단여백의 잔존 원인: 앵커 줄간격·outMargin·편집용지(R020·R022)를 모두 양식값으로
    맞춰도 kordoc 산출물에는 머리말(hp:header)이 없어 위 10mm + 머리말 15mm = 25mm가 통째로
    빈 흰 띠로 남는다. 양식 원형·실무 문서는 이 머리말 영역을 KCA 로고 배너 표(1×2, 높이
    11.3mm)가 채우므로 제목표 위가 비어 보이지 않는다. 실무 문서에서 이식한 배너를
    머리말 부재 시 주입한다. 이미 hp:header가 있으면 건너뛴다(멱등)."""
    hdr_tag = qn("hp", "header")
    for sec_root in section_roots:
        for hdr in sec_root.iter(hdr_tag):
            # 기주입 문서도 앵커 기하(R041)는 보정한다 — 150% 잔존분 소급 수리(멱등)
            geo = _fix_header_anchor_geometry(header_root, section_roots, hdr)
            return {"injected": 0, "reason": "header_exists", "geometry": geo}
    frag_path = BANNER_ASSETS_DIR / "fragment.xml"
    res_path = BANNER_ASSETS_DIR / "resources.xml"
    if not (frag_path.exists() and res_path.exists()
            and all((BANNER_ASSETS_DIR / f).exists() for _, f, _ in BANNER_BIN_ITEMS)):
        return {"injected": 0, "reason": "assets_missing"}

    borderfills = header_root.find(f".//{qn('hh', 'borderFills')}")
    paraprops = header_root.find(f".//{qn('hh', 'paraProperties')}")
    charprops = header_root.find(f".//{qn('hh', 'charProperties')}")
    if borderfills is None or paraprops is None or charprops is None:
        return {"injected": 0, "reason": "header_containers_missing"}

    bf_base = _max_id(borderfills, qn("hh", "borderFill"))
    pp_base = _max_id(paraprops, qn("hh", "paraPr"))
    cp_base = _max_id(charprops, qn("hh", "charPr"))
    zmax = 0
    for sec_root in section_roots:
        for el in sec_root.iter():
            z = el.get("zOrder")
            if z and z.isdigit():
                zmax = max(zmax, int(z))
    oid = 9700000  # 문서 내 개체 id와 충돌하지 않는 고정 대역
    mapping = {
        "__KHB_BF0__": str(bf_base + 1), "__KHB_BF1__": str(bf_base + 2),
        "__KHB_BFPLAIN__": "1",  # 도너 '무테두리' borderFill → 대상 기본(전변 NONE) id
        "__KHB_PP0__": str(pp_base + 1), "__KHB_PP1__": str(pp_base + 2),
        "__KHB_PP2__": str(pp_base + 3),
        "__KHB_CP0__": str(cp_base + 1), "__KHB_CP1__": str(cp_base + 2),
        "__KHB_IMG0__": BANNER_BIN_ITEMS[0][0], "__KHB_IMG1__": BANNER_BIN_ITEMS[1][0],
        "__KHB_HID__": str(oid + 100),
        "__KHB_OID0__": str(oid + 1), "__KHB_OID1__": str(oid + 2),
        "__KHB_OID2__": str(oid + 3),
        "__KHB_INST0__": str(oid + 4), "__KHB_INST1__": str(oid + 5),
        "__KHB_Z0__": str(zmax + 1), "__KHB_Z1__": str(zmax + 2),
        "__KHB_Z2__": str(zmax + 3),
    }

    def subst(text):
        for k, v in mapping.items():
            text = text.replace(k, v)
        if "__KHB_" in text:
            raise PostprocessError("header banner 자산 토큰 치환 누락")
        return text

    res_root = ET.fromstring(subst(res_path.read_text(encoding="utf-8")))
    appended = {"borderFill": 0, "paraPr": 0, "charPr": 0}
    for child in list(res_root):
        if child.tag == qn("hh", "borderFill"):
            borderfills.append(child)
            appended["borderFill"] += 1
        elif child.tag == qn("hh", "paraPr"):
            paraprops.append(child)
            appended["paraPr"] += 1
        elif child.tag == qn("hh", "charPr"):
            charprops.append(child)
            appended["charPr"] += 1
    for container, tag in ((borderfills, qn("hh", "borderFill")),
                           (paraprops, qn("hh", "paraPr")),
                           (charprops, qn("hh", "charPr"))):
        container.set("itemCnt", str(len(container.findall(tag))))

    ns_decl = " ".join(f'xmlns:{p}="{u}"' for p, u in NS.items())
    wrapper = ET.fromstring(
        f"<khbWrap {ns_decl}>" + subst(frag_path.read_text(encoding="utf-8")) + "</khbWrap>")
    ctrl = wrapper[0]  # <hp:ctrl><hp:header>…</hp:header></hp:ctrl>

    first_p = section_roots[0].find(qn("hp", "p"))
    if first_p is None:
        return {"injected": 0, "reason": "no_paragraph"}
    run = first_p.find(qn("hp", "run"))
    if run is None:
        return {"injected": 0, "reason": "no_run"}
    # 양식 원형과 동일하게 secd/cold 계열 ctrl 뒤·표(제목박스) 앞에 배치
    insert_at = 0
    for idx, child in enumerate(list(run)):
        if child.tag in (qn("hp", "secPr"), qn("hp", "ctrl")):
            insert_at = idx + 1
    run.insert(insert_at, ctrl)

    # 앵커 lineSpacing 100%·subList textWidth 본문 폭 보정 (R041)
    geo = _fix_header_anchor_geometry(header_root, section_roots, ctrl.find(qn("hp", "header")))

    for item_id, fname, _mt in BANNER_BIN_ITEMS:
        data["BinData/" + fname] = (BANNER_ASSETS_DIR / fname).read_bytes()
    hpf_name = "Contents/content.hpf"
    if hpf_name in data:
        hpf = data[hpf_name].decode("utf-8")
        if "</opf:manifest>" in hpf and BANNER_BIN_ITEMS[0][0] not in hpf:
            items = "".join(
                f'<opf:item id="{iid}" href="BinData/{fn}" media-type="{mt}" isEmbeded="1"/>'
                for iid, fn, mt in BANNER_BIN_ITEMS)
            data[hpf_name] = hpf.replace("</opf:manifest>", items + "</opf:manifest>").encode("utf-8")
    return {"injected": 1, "resources_appended": appended,
            "bin_items": [f for _, f, _ in BANNER_BIN_ITEMS], "geometry": geo}


def ensure_charpr_bold(header_root, base_id, cache):
    """base_id charPr에 볼드가 없으면 <hh:bold/>를 더한 복제본 id를 반환한다(있으면 그대로)."""
    if base_id in cache:
        return cache[base_id]
    charprops = header_root.find(f".//{qn('hh', 'charProperties')}")
    base = None
    for cp in charprops.findall(qn("hh", "charPr")):
        if cp.get("id") == base_id:
            base = cp
            break
    if base is None:
        cache[base_id] = base_id
        return base_id
    if base.find(qn("hh", "bold")) is not None:
        cache[base_id] = base_id
        return base_id
    new_cp = copy.deepcopy(base)
    max_id = max(int(cp.get("id")) for cp in charprops.findall(qn("hh", "charPr")))
    new_id = str(max_id + 1)
    new_cp.set("id", new_id)
    ET.SubElement(new_cp, qn("hh", "bold"))
    charprops.append(new_cp)
    charprops.set("itemCnt", str(int(charprops.get("itemCnt", "0")) + 1))
    cache[base_id] = new_id
    return new_id


def apply_dae_bold(header_root, section_roots):
    """□ 절 제목 문단 run의 charPr을 볼드 변형으로 치환한다(R024 — 사용자 확정 '26.7.24)."""
    p_tag = qn("hp", "p")
    cache = {}
    found = 0
    changed = 0
    for sec_root in section_roots:
        for child in sec_root:
            if child.tag != p_tag or classify(child) != "dae":
                continue
            found += 1
            for run in child.findall(qn("hp", "run")):
                base_id = run.get("charPrIDRef")
                if base_id is None:
                    continue
                new_id = ensure_charpr_bold(header_root, base_id, cache)
                if new_id != base_id:
                    run.set("charPrIDRef", new_id)
                    changed += 1
    return {"dae_found": found, "runs_changed": changed}


# ---------------------------------------------------------------------------
# 캡션 내장 (R034) · 본문 양쪽정렬 (R032) · ＊ 위첨자 (R031) · 괄호 13pt (R033)
# ---------------------------------------------------------------------------

# hp:caption 원형 — 260331 실무본 실측: side=TOP, outMargin과 inMargin 사이에 위치,
# 캡션 문단은 CENTER + 볼드 + 12pt (paraPr45 CENTER·charPr49 height=1200+bold)
CAPTION_ATTRS = {"side": "TOP", "fullSz": "0", "width": "8504", "gap": "850"}


def apply_caption_embed(header_root, section_roots):
    """표 바깥 캡션 문단(`[ … ]`)을 바로 다음 콘텐츠 표의 hp:caption(side=TOP)으로 내장한다
    (R034 — 사용자 확정 '26.7.28). 실무본 실측 구조: hp:tbl 안 outMargin 다음 위치,
    subList/p 로 캡션 문단 이동, CENTER + 볼드(크기는 R023 12pt 일괄 처리에 위임).
    캡션과 표 사이의 빈 문단(캡션→표 스페이서)은 제거한다. 제목 박스·배너 표는 제외."""
    p_tag = qn("hp", "p")
    align_cache = {}
    bold_cache = {}
    embedded = 0
    orphans = 0
    for sec_root in section_roots:
        children = list(sec_root)
        remove = []
        for i, child in enumerate(children):
            if child.tag != p_tag or classify(child) != "caption":
                continue
            # 다음 콘텐츠 문단(빈 문단 건너뜀) 탐색
            target_tbl = None
            gap_empties = []
            for j in range(i + 1, len(children)):
                nxt = children[j]
                if nxt.tag != p_tag:
                    break
                kind = classify(nxt)
                if kind == "empty":
                    gap_empties.append(nxt)
                    continue
                if kind == "table":
                    tbls = [tbl for run in nxt.findall(qn("hp", "run"))
                            for tbl in run.findall(qn("hp", "tbl"))]
                    if tbls and not _is_banner_table(tbls[0]):
                        target_tbl = tbls[0]
                break
            if target_tbl is None:
                orphans += 1
                continue
            existing = target_tbl.find(qn("hp", "caption"))
            if existing is not None:
                ex_text = "".join(t.text or "" for t in existing.iter(qn("hp", "t"))).strip()
                if ex_text == para_text(child).strip():
                    remove.append(child)  # 동일 캡션 기내장 — 중복 문단만 제거(멱등)
                    remove.extend(gap_empties)
                else:
                    orphans += 1
                continue
            # 캡션 요소 조립 (실무본 원형: outMargin 다음, inMargin 앞)
            cap = ET.Element(qn("hp", "caption"), dict(CAPTION_ATTRS))
            sz = target_tbl.find(qn("hp", "sz"))
            cap.set("lastWidth", sz.get("width", "0") if sz is not None else "0")
            sub = ET.SubElement(cap, qn("hp", "subList"), {
                "id": "", "textDirection": "HORIZONTAL", "lineWrap": "BREAK",
                "vertAlign": "TOP", "linkListIDRef": "0", "linkListNextIDRef": "0",
                "textWidth": "0", "textHeight": "0", "hasTextRef": "0", "hasNumRef": "0"})
            # 캡션 문단을 통째로 이동 — CENTER 정렬 + 볼드 배정
            base_pp = child.get("paraPrIDRef")
            if base_pp is not None:
                new_pp = ensure_aligned_clone(header_root, base_pp, "CENTER", align_cache)
                if new_pp != base_pp:
                    child.set("paraPrIDRef", new_pp)
            for run in child.findall(qn("hp", "run")):
                base_cp = run.get("charPrIDRef")
                if base_cp is not None:
                    new_cp = ensure_charpr_bold(header_root, base_cp, bold_cache)
                    if new_cp != base_cp:
                        run.set("charPrIDRef", new_cp)
            sub.append(child)
            insert_at = 0
            for idx, tc in enumerate(list(target_tbl)):
                if tc.tag in (qn("hp", "sz"), qn("hp", "pos"), qn("hp", "outMargin")):
                    insert_at = idx + 1
            target_tbl.insert(insert_at, cap)
            remove.append(child)
            remove.extend(gap_empties)
            embedded += 1
        for el in remove:
            sec_root.remove(el)
    return {"embedded": embedded, "orphan_captions": orphans}


JUSTIFY_KINDS = ("dae", "yo", "dash", "cham", "star")  # ※·＊도 양쪽정렬 (R061)


def apply_body_justify(header_root, section_roots):
    """본문 계층 문단(□·ㅇ·대시)과 ※·＊ 단서·각주의 정렬을 JUSTIFY로 치환한다
    (R032 + R061). 캡션·발신 줄은 기존 정렬 유지."""
    p_tag = qn("hp", "p")
    cache = {}
    found = 0
    changed = 0
    for sec_root in section_roots:
        for child in sec_root:
            if child.tag != p_tag or classify(child) not in JUSTIFY_KINDS:
                continue
            found += 1
            base_id = child.get("paraPrIDRef")
            if base_id is None:
                continue
            new_id = ensure_aligned_clone(header_root, base_id, "JUSTIFY", cache)
            if new_id != base_id:
                child.set("paraPrIDRef", new_id)
                changed += 1
    return {"found": found, "changed": changed}


LINE_FIT_KINDS = ("dae", "yo", "dash", "cham", "star")
MIN_SPACING = -10   # 자간 하한 (R062 — -10 미만 금지)
MIN_RATIO = 90      # 장평 하한 (R062)


def _para_text(p):
    out = []
    for run in p.findall(qn("hp", "run")):
        for t in run.findall(qn("hp", "t")):
            out.append("".join(t.itertext()))
    return "".join(out)


def _weighted_len(text):
    """한글·전각 1.0, 영숫자·기호 0.5로 가중한 글자 폭 환산 길이."""
    w = 0.0
    for ch in text:
        if ch.isspace():
            w += 0.5
        elif ord(ch) > 0x2000:
            w += 1.0
        else:
            w += 0.5
    return w


def _text_width_pt(sec_root):
    pp = sec_root.find(f".//{qn('hp', 'pagePr')}")
    if pp is None:
        return 481.9
    mg = pp.find(qn("hp", "margin"))
    w = int(pp.get("width", "59528"))
    left = int(mg.get("left", "5669")) if mg is not None else 5669
    right = int(mg.get("right", "5669")) if mg is not None else 5669
    return (w - left - right) / 100.0


def _para_indent_pt(header_root, para_pr_id):
    for pr in header_root.iter(qn("hh", "paraPr")):
        if pr.get("id") != para_pr_id:
            continue
        mg = pr.find(qn("hh", "margin"))
        if mg is None:
            return 0.0
        left = mg.find(qn("hc", "left"))
        lv = int(left.get("value", "0")) if left is not None else 0
        return lv / 100.0
    return 0.0


def _charpr_metrics(header_root, cid):
    for cp in header_root.iter(qn("hh", "charPr")):
        if cp.get("id") != cid:
            continue
        h = int(cp.get("height", "1500")) / 100.0
        ratio = cp.find(qn("hh", "ratio"))
        rv = int(ratio.get("hangul", "100")) if ratio is not None else 100
        sp = cp.find(qn("hh", "spacing"))
        sv = int(sp.get("hangul", "0")) if sp is not None else 0
        return h, rv, sv
    return 15.0, 100, 0


def ensure_charpr_fitted(header_root, base_id, ratio, spacing, cache):
    """base charPr에서 장평·자간만 바꾼 복제본 id를 반환한다."""
    key = (base_id, ratio, spacing)
    if key in cache:
        return cache[key]
    charprops = header_root.find(f".//{qn('hh', 'charProperties')}")
    base = None
    for cp in charprops.findall(qn("hh", "charPr")):
        if cp.get("id") == base_id:
            base = cp
            break
    if base is None:
        cache[key] = base_id
        return base_id
    new_cp = copy.deepcopy(base)
    new_id = str(max(int(cp.get("id")) for cp in charprops.findall(qn("hh", "charPr"))) + 1)
    new_cp.set("id", new_id)
    for tag, attr_val in (("ratio", ratio), ("spacing", spacing)):
        el = new_cp.find(qn("hh", tag))
        if el is None:
            el = ET.SubElement(new_cp, qn("hh", tag))
        for k in ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user"):
            el.set(k, str(attr_val))
    charprops.append(new_cp)
    charprops.set("itemCnt", str(len(charprops.findall(qn("hh", "charPr")))))
    cache[key] = new_id
    return new_id


def apply_line_fit(header_root, section_roots, max_lines=2):
    """계층 서술 문단이 max_lines(기본 2줄)를 넘으면 자간·장평을 조여 맞춘다 (R062).

    자간은 -10, 장평은 90이 하한이며 그래도 초과하는 문단은 overflow로 보고한다
    (타이포로 못 줄이는 분량이므로 본문 텍스트를 줄여야 한다)."""
    p_tag = qn("hp", "p")
    cache = {}
    fitted, overflow, scanned = [], [], 0
    for sec_root in section_roots:
        width = _text_width_pt(sec_root)
        for child in sec_root:
            if child.tag != p_tag or classify(child) not in LINE_FIT_KINDS:
                continue
            text = _para_text(child)
            if not text.strip():
                continue
            scanned += 1
            runs = child.findall(qn("hp", "run"))
            if not runs:
                continue
            base_cid = runs[0].get("charPrIDRef")
            if base_cid is None:
                continue
            h, ratio0, sp0 = _charpr_metrics(header_root, base_cid)
            avail = width - _para_indent_pt(header_root, child.get("paraPrIDRef") or "")
            wl = _weighted_len(text)

            def lines_at(ratio, spacing):
                adv = h * (ratio / 100.0 + spacing / 100.0)
                if adv <= 0:
                    return 99
                return math.ceil(wl / max(1.0, avail / adv))

            if lines_at(ratio0, sp0) <= max_lines:
                continue
            chosen = None
            for spacing in range(sp0, MIN_SPACING - 1, -1):
                if lines_at(ratio0, spacing) <= max_lines:
                    chosen = (ratio0, spacing)
                    break
            if chosen is None:
                for ratio in range(ratio0, MIN_RATIO - 1, -1):
                    if lines_at(ratio, MIN_SPACING) <= max_lines:
                        chosen = (ratio, MIN_SPACING)
                        break
            if chosen is None:
                overflow.append({"text": text[:40], "chars": len(text),
                                 "lines": lines_at(MIN_RATIO, MIN_SPACING)})
                continue
            new_cid = ensure_charpr_fitted(header_root, base_cid, chosen[0], chosen[1], cache)
            for run in runs:
                if run.get("charPrIDRef") == base_cid:
                    run.set("charPrIDRef", new_cid)
            fitted.append({"text": text[:30], "ratio": chosen[0], "spacing": chosen[1]})
    return {"scanned": scanned, "fitted": len(fitted), "overflow": len(overflow),
            "overflow_detail": overflow[:10], "min_spacing": MIN_SPACING, "min_ratio": MIN_RATIO}


def estimate_layout(header_root, section_roots):
    """조판 부피를 추정해 export 인도 시 보고한다 (R067).

    린트·구조검증은 전부 통과해도 실제 조판이 15페이지가 되는 일이 있었다 — 정적 검사가
    "몇 줄로 렌더되는가"를 보지 않기 때문이다. 문단별 예상 줄 수와 표 부피로 쪽수를
    가늠해 **분량이 목표를 넘으면 인도 전에 드러나게** 한다."""
    p_tag = qn("hp", "p")
    line_h, lines, tbl_rows, over2, tbl_h = 0, 0, 0, 0, 0.0
    for sec_root in section_roots:
        width = _text_width_pt(sec_root)
        for child in sec_root:
            if child.tag != p_tag:
                continue
            for tbl in child.iter(qn("hp", "tbl")):
                rows = int(tbl.get("rowCnt", "1"))
                cols = max(1, int(tbl.get("colCnt", "1")))
                tbl_rows += rows
                # 행 높이는 셀 텍스트가 열 폭 안에서 몇 줄로 접히는지로 결정된다 —
                # 긴 셀을 가진 표가 쪽수를 지배하므로 평면 상수로 세면 크게 빗나간다
                col_chars = max(4.0, (_text_width_pt(sec_root) / cols) / 6.5)  # 표 12pt 기준
                for tr in tbl.iter(qn("hp", "tr")):
                    tallest = 1
                    for tc in tr.iter(qn("hp", "tc")):
                        ln = _weighted_len("".join(t for t in tc.itertext()))
                        tallest = max(tallest, math.ceil(ln / col_chars))
                    tbl_h += tallest * 12.0 * 1.6 + 4.0
            kind = classify(child)
            text = _para_text(child)
            if not text.strip():
                continue
            runs = child.findall(qn("hp", "run"))
            if not runs:
                continue
            h, ratio, sp = _charpr_metrics(header_root, runs[0].get("charPrIDRef") or "")
            line_h = max(line_h, h)
            avail = width - _para_indent_pt(header_root, child.get("paraPrIDRef") or "")
            adv = h * (ratio / 100.0 + sp / 100.0)
            n = math.ceil(_weighted_len(text) / max(1.0, avail / max(adv, 0.1)))
            lines += n
            if kind in LINE_FIT_KINDS and n > 2:
                over2 += 1
    body_pt = lines * line_h * 1.6            # 줄간격 160%
    pages = max(1, math.ceil((body_pt + tbl_h) / 700.0))   # A4 본문 높이 ≈ 700pt
    return {"paragraph_lines": lines, "table_rows": tbl_rows,
            "over_two_lines": over2, "est_pt": round(body_pt + tbl_h), "est_pages": pages}


def apply_table_pagination(section_roots, rows_per_page=22):
    """표가 페이지를 벗어날 때의 처리를 강제한다 (R063).

    ① 셀 단위 페이지 분할 허용(pageBreak=CELL) ② 첫 행 제목 반복(repeatHeader=1)을
    모든 콘텐츠 표에 보장하고, 한 페이지를 넘길 것으로 보이는 표는 oversized로 보고한다."""
    fixed, oversized = 0, []
    for sec_root in section_roots:
        for tbl in sec_root.iter(qn("hp", "tbl")):
            rows = int(tbl.get("rowCnt", "1"))
            cols = int(tbl.get("colCnt", "1"))
            if tbl.get("pageBreak") != "CELL":
                tbl.set("pageBreak", "CELL")
                fixed += 1
            if rows > 1 and tbl.get("repeatHeader") != "1":
                tbl.set("repeatHeader", "1")
                fixed += 1
            cells = tbl.findall(f".//{qn('hp', 'tc')}")
            texts = ["".join(t.itertext()) for c in cells for t in c.iter(qn("hp", "t"))]
            longest = max((len(t) for t in texts), default=0)
            if rows >= rows_per_page or (rows >= 6 and longest >= 90):
                oversized.append({"rows": rows, "cols": cols, "longest_cell": longest})
    return {"attrs_fixed": fixed, "oversized": len(oversized), "detail": oversized[:10],
            "rule": "pageBreak=CELL + repeatHeader=1"}


def apply_formula_box(header_root, section_roots):
    """1행 1열 표를 산식 박스로 규격화한다 (R064) — 본문 폭 전체·가운데 정렬."""
    boxed = 0
    p_tag = qn("hp", "p")
    for sec_root in section_roots:
        # 제목 박스·머리글 배너는 첫 □ 이전에 온다 — 산식 박스 대상에서 제외
        seen_dae = False
        for child in sec_root:
            if child.tag != p_tag:
                continue
            if classify(child) == "dae":
                seen_dae = True
            if not seen_dae:
                continue
            for tbl in child.iter(qn("hp", "tbl")):
                if tbl.get("rowCnt") != "1" or tbl.get("colCnt") != "1":
                    continue
                for tc in tbl.iter(qn("hp", "tc")):
                    for p in tc.iter(qn("hp", "p")):
                        pid = p.get("paraPrIDRef")
                        if pid is None:
                            continue
                        p.set("paraPrIDRef",
                              ensure_aligned_clone(header_root, pid, "CENTER", {}))
                boxed += 1
    return {"formula_boxes": boxed}


def ensure_charpr_supscript(header_root, base_id, cache):
    """base_id charPr에 <hh:supscript/>를 더한 복제본 id를 반환한다(이미 있으면 그대로).
    위첨자 인코딩 실측: 실무본·260223 AX전략 hwpx 모두 charPr 자식 <hh:supscript/>
    (height·offset은 그대로 두고 한글이 축소 렌더)."""
    if base_id in cache:
        return cache[base_id]
    charprops = header_root.find(f".//{qn('hh', 'charProperties')}")
    base = None
    for cp in charprops.findall(qn("hh", "charPr")):
        if cp.get("id") == base_id:
            base = cp
            break
    if base is None or base.find(qn("hh", "supscript")) is not None:
        cache[base_id] = base_id
        return base_id
    new_cp = copy.deepcopy(base)
    max_id = max(int(cp.get("id")) for cp in charprops.findall(qn("hh", "charPr")))
    new_id = str(max_id + 1)
    new_cp.set("id", new_id)
    ET.SubElement(new_cp, qn("hh", "supscript"))
    charprops.append(new_cp)
    charprops.set("itemCnt", str(int(charprops.get("itemCnt", "0")) + 1))
    cache[base_id] = new_id
    return new_id


def _split_run(p, run, segments):
    """run(자식이 hp:t 하나뿐)을 (text, charpr_id) 시퀀스로 교체한다. 빈 텍스트는 건너뜀."""
    pos = list(p).index(run)
    p.remove(run)
    inserted = 0
    for text, cp_id in segments:
        if not text:
            continue
        new_run = ET.Element(qn("hp", "run"), {"charPrIDRef": cp_id})
        t = ET.SubElement(new_run, qn("hp", "t"))
        t.text = text
        p.insert(pos + inserted, new_run)
        inserted += 1
    return inserted


def apply_superscript_star(header_root, section_roots):
    """본문 서술 중 용어 뒤 ＊ 표지를 위첨자 charPr로 분리한다(R031 — 사용자 확정 '26.7.28).
    `＊ 용어 : 설명` 각주 문단(선두 ＊)은 평문 유지. 표 셀 내부 문단도 동일 처리."""
    p_tag = qn("hp", "p")
    cache = {}
    stars = 0
    for sec_root in section_roots:
        for p in sec_root.iter(p_tag):
            text = para_text(p).strip()
            if not text or text.startswith(STAR):
                continue
            if STAR not in text:
                continue
            for run in list(p.findall(qn("hp", "run"))):
                t = run.find(qn("hp", "t"))
                if t is None or not t.text or STAR not in t.text or len(list(run)) != 1:
                    continue
                base_cp = run.get("charPrIDRef")
                if base_cp is None:
                    continue
                sup_cp = ensure_charpr_supscript(header_root, base_cp, cache)
                if sup_cp == base_cp:
                    continue  # 이미 위첨자 run(멱등)
                segments = []
                for piece in re.split(f"({STAR})", t.text):
                    segments.append((piece, sup_cp if piece == STAR else base_cp))
                stars += sum(1 for s, _ in segments if s == STAR)
                _split_run(p, run, segments)
    return {"stars_superscripted": stars}


PAREN_RE = re.compile(r"\([^()]*\)")
PAREN_KINDS = ("dae", "yo", "dash")
LEAD_MARKERS = {"", "□", "-", "ㅇ", "○"}


def _para_run_infos(p):
    """문단 직속 run들의 (run, text, start, end, simple) 목록과 전체 텍스트를 반환한다.
    simple = 자식이 순수 텍스트 hp:t 하나뿐이고 charPrIDRef가 있어 _split_run 분할 가능."""
    infos = []
    full = ""
    for run in p.findall(qn("hp", "run")):
        t = run.find(qn("hp", "t"))
        text = (t.text or "") if t is not None else ""
        simple = (t is not None and len(list(run)) == 1 and len(list(t)) == 0
                  and run.get("charPrIDRef") is not None)
        infos.append({"run": run, "text": text, "start": len(full),
                      "end": len(full) + len(text), "simple": simple})
        full += text
    return infos, full


def apply_paren_small(header_root, section_roots, pt=13):
    """본문 계층 문단(□·ㅇ·대시) 서술 중 `(…)` 괄호 구간을 13pt로 축소한다
    (R033 — 사용자 확정 '26.7.28 / R039 개정 '26.7.28: run 경계를 넘는 구간도 처리).
    ㅇ 선두 괄호 리드(R016 라벨)는 제외 — 본문 서술이 아니라 볼드 라벨이므로 15pt 유지.
    표 셀·＊※ 각주·캡션은 대상 아님.

    괄호 구간은 run이 아니라 **문단 전체 텍스트** 기준으로 찾고, 구간에 걸친 run들을
    각각 분할해 걸친 부분만 각 run 고유 charPr의 13pt 복제본으로 치환한다 — 문장 안
    볼드(`**T1**` 등)로 run이 쪼개져도 볼드 등 서식은 보존된다(볼드 run 안 괄호는
    13pt 볼드). cross_run_skipped는 분할 불가 run(중첩 개체 등)에 걸린 구간만 남는다."""
    height = int(round(pt * 100))
    p_tag = qn("hp", "p")
    cache = {}
    heights = {cp.get("id"): cp.get("height")
               for cp in header_root.iter(qn("hh", "charPr"))}
    spans = 0
    lead_skipped = 0
    cross_run = 0
    for sec_root in section_roots:
        for child in sec_root:
            if child.tag != p_tag or classify(child) not in PAREN_KINDS:
                continue
            infos, full = _para_run_infos(child)
            if "(" not in full or ")" not in full:
                continue
            jobs = []
            for m in PAREN_RE.finditer(full):
                if full[:m.start()].strip() in LEAD_MARKERS:
                    lead_skipped += 1  # ㅇ (교 육) 등 선두 리드 — 제외
                    continue
                overlapped = [i for i in infos
                              if i["text"] and i["end"] > m.start() and i["start"] < m.end()]
                if not overlapped or not all(i["simple"] for i in overlapped):
                    cross_run += 1  # 분할 불가 run(그림·중첩 요소 등)에 걸침 — 건너뜀
                    continue
                if all(heights.get(i["run"].get("charPrIDRef")) == str(height)
                       for i in overlapped):
                    continue  # 이미 전 구간 13pt — 재실행 멱등
                jobs.append((m.start(), m.end()))
            if not jobs:
                continue
            spans += len(jobs)
            for info in infos:
                if not info["text"]:
                    continue
                r_s, r_e, text = info["start"], info["end"], info["text"]
                overlaps = [(max(s, r_s) - r_s, min(e, r_e) - r_s)
                            for s, e in jobs if e > r_s and s < r_e]
                if not overlaps:
                    continue
                base_cp = info["run"].get("charPrIDRef")
                small_cp = ensure_charpr_sized(header_root, base_cp, height, cache)
                if small_cp == base_cp:
                    continue  # 이 run은 이미 13pt — 그대로 둔다
                segments = []
                pos = 0
                for s, e in overlaps:
                    segments.append((text[pos:s], base_cp))
                    segments.append((text[s:e], small_cp))
                    pos = e
                segments.append((text[pos:], base_cp))
                _split_run(child, info["run"], segments)
    return {"paren_spans": spans, "lead_skipped": lead_skipped, "cross_run_skipped": cross_run,
            "height": height}


# '특히 강조' = 노란색 음영 하이라이트 (R040 — 사용자 확정 '26.7.28).
# 인코딩 실측: 260331 실무본 'AI검증 후 최종결과물 변환' run(charPr id=82) —
# charPr 속성 shadeColor="#FFFF00" + <hh:bold/> (높이·폰트는 본문 그대로).
# hwpx XML 색은 #RRGGBB 직독 — #FFFF00=노랑(사용자 관찰 정합). COLORREF 0x00BBGGRR
# 바이트 반전(R027)은 hwp OLE 바이너리 전용이며 hwpx XML에는 적용되지 않는다
# (교차검증: 같은 실무본 제목박스 그라데이션 #3057B9가 RGB 직독으로 남색 — BGR로 읽으면
# #B95730 적갈색이 되어 실물과 불일치).
HIGHLIGHT_RE = re.compile(r"==(.+?)==")
HIGHLIGHT_SHADE = "#FFFF00"


def ensure_charpr_highlight(header_root, base_id, cache):
    """base_id charPr에 shadeColor=#FFFF00(노란 음영)과 볼드를 더한 복제본 id를 반환한다
    (이미 두 속성을 모두 가지면 그대로). 폰트·크기 등 나머지 서식은 보존한다."""
    if base_id in cache:
        return cache[base_id]
    charprops = header_root.find(f".//{qn('hh', 'charProperties')}")
    base = None
    for cp in charprops.findall(qn("hh", "charPr")):
        if cp.get("id") == base_id:
            base = cp
            break
    if base is None or (base.get("shadeColor") == HIGHLIGHT_SHADE
                        and base.find(qn("hh", "bold")) is not None):
        cache[base_id] = base_id
        return base_id
    new_cp = copy.deepcopy(base)
    max_id = max(int(cp.get("id")) for cp in charprops.findall(qn("hh", "charPr")))
    new_id = str(max_id + 1)
    new_cp.set("id", new_id)
    new_cp.set("shadeColor", HIGHLIGHT_SHADE)
    if new_cp.find(qn("hh", "bold")) is None:
        ET.SubElement(new_cp, qn("hh", "bold"))
    charprops.append(new_cp)
    charprops.set("itemCnt", str(int(charprops.get("itemCnt", "0")) + 1))
    cache[base_id] = new_id
    return new_id


def apply_highlight(header_root, section_roots):
    """초안 `==문구==` 하이라이트 마커를 노란 음영+볼드 run으로 치환한다(R040 —
    사용자 확정 '26.7.28, 260331 실무본 실측 인코딩: charPr shadeColor=#FFFF00 + bold).
    마커(`==`)는 제거하고 안쪽 구간만 하이라이트 charPr 복제본으로 분할 배정한다 —
    구간이 run 경계를 넘어도(안쪽 볼드 등) run별 분할로 처리하고 각 run 서식은 보존.
    마커 잔존 방지를 위해 표 셀 포함 전체 문단을 훑는다. 분할 불가 run에 걸친 마커와
    짝이 안 맞는 `==`는 그대로 두고 보고한다(초안 lint highlight-unpaired가 1차 방어)."""
    p_tag = qn("hp", "p")
    cache = {}
    highlights = 0
    skipped = 0
    for sec_root in section_roots:
        for child in sec_root.iter(p_tag):
            infos, full = _para_run_infos(child)
            if "==" not in full:
                continue
            jobs = []  # (전체 시작, 전체 끝, 내용 시작, 내용 끝)
            for m in HIGHLIGHT_RE.finditer(full):
                overlapped = [i for i in infos
                              if i["text"] and i["end"] > m.start() and i["start"] < m.end()]
                if not overlapped or not all(i["simple"] for i in overlapped):
                    skipped += 1
                    continue
                jobs.append((m.start(), m.end(), m.start(1), m.end(1)))
            if not jobs:
                continue
            highlights += len(jobs)
            for info in infos:
                if not info["text"]:
                    continue
                r_s, r_e, text = info["start"], info["end"], info["text"]
                marks = []  # run-로컬 (시작, 끝, 종류) — drop=마커 토큰, hl=하이라이트 내용
                for s, e, cs, ce in jobs:
                    for a, b, kind in ((s, cs, "drop"), (cs, ce, "hl"), (ce, e, "drop")):
                        a2, b2 = max(a, r_s), min(b, r_e)
                        if a2 < b2:
                            marks.append((a2 - r_s, b2 - r_s, kind))
                if not marks:
                    continue
                marks.sort()
                base_cp = info["run"].get("charPrIDRef")
                hl_cp = ensure_charpr_highlight(header_root, base_cp, cache)
                segments = []
                pos = 0
                for a, b, kind in marks:
                    if a > pos:
                        segments.append((text[pos:a], base_cp))
                    if kind == "hl":
                        segments.append((text[a:b], hl_cp))
                    pos = b
                segments.append((text[pos:], base_cp))
                _split_run(child, info["run"], segments)
    return {"highlights": highlights, "skipped": skipped, "shade": HIGHLIGHT_SHADE}


# KCA 양식 편집용지 여백 (HWPUNIT, 7200/inch): 좌우 20mm·위 10mm·아래 15mm·머리말 15mm·꼬리말 10mm
PAGE_MARGINS = {"left": "5669", "right": "5669", "top": "2835", "bottom": "4252",
                "header": "4252", "footer": "2835"}


def apply_page_margins(section_roots):
    """pagePr 여백을 KCA 양식 규격으로 강제한다 (kordoc preset은 위 15mm로 생성 —
    양식은 위 10mm라 제목표 위에 5mm 초과 여백이 생기는 결함의 후처리, R020)."""
    changed = 0
    for sec_root in section_roots:
        for pagepr in sec_root.iter(qn("hp", "pagePr")):
            margin = pagepr.find(qn("hp", "margin"))
            if margin is None:
                continue
            for k, v in PAGE_MARGINS.items():
                if margin.get(k) != v:
                    margin.set(k, v)
                    changed += 1
    return {"attrs_changed": changed}


HIERARCHY_SPACES = {"dae": 0, "yo": 1, "dash": 3, "star": 5, "cham": 5, "arrow": 5}
# 줄바꿈 시 둘째 줄 들여쓰기(=본문 시작 위치, HWPUNIT). 첫 줄은 intent=-left로 0에서 시작
# ※ 값은 폰트 크기가 아니라 "그 폰트 글자폭의 배수"(□1.5글자·ㅇ2글자·대시2.5글자·＊4글자) — 사용자 보고 시 글자 단위 병기
# (리터럴 공백이 마커 위치를 잡고, 랩된 줄은 left 위치에 정렬 — 사용자 확정 '26.7.22)
# 산출: 공백폭=글자크기/2 — dae 0+□15+공백7.5 / yo 공백7.5+ㅇ15+7.5 / dash 22.5+대시7.5+7.5
#       star·cham(13pt) 공백 5×6.5+기호13+6.5 / arrow(15pt 본문) 공백 5×7.5+기호15+7.5 (R025)
HIERARCHY_HANG = {"dae": 2250, "yo": 3000, "dash": 3750, "star": 5200, "cham": 5200,
                  "arrow": 6000}


def ensure_hang_parapr(header_root, base_id, hang, cache):
    """base paraPr 복제 — left=hang·intent=-hang(첫 줄 0에서 시작, 랩 줄은 hang 위치 정렬),
    prev·next=0. hang=0이면 전부 0(내어쓰기 불필요 계층)."""
    key = (base_id, hang)
    if key in cache:
        return cache[key]
    paraprops = header_root.find(f".//{qn('hh', 'paraProperties')}")
    base = None
    for pp in paraprops.findall(qn("hh", "paraPr")):
        if pp.get("id") == base_id:
            base = pp
            break
    if base is None:
        cache[key] = base_id
        return base_id
    # 한글 내어쓰기 의미론: 음수 intent = "첫 줄은 left 위치, 랩 줄은 left+|intent|"
    # → 첫 줄을 0(리터럴 띄어쓰기만)에 두려면 left=0·intent=-hang (원본 양식도 이 인코딩)
    want = {"left": "0", "intent": str(-hang), "prev": "0", "next": "0"}
    margin = base.find(qn("hh", "margin"))
    if margin is not None and all(
        (el := margin.find(qn("hc", t))) is not None and el.get("value") == v
        for t, v in want.items()
    ):
        cache[key] = base_id
        return base_id
    new_pp = copy.deepcopy(base)
    max_id = max(int(pp.get("id")) for pp in paraprops.findall(qn("hh", "paraPr")))
    new_id = str(max_id + 1)
    new_pp.set("id", new_id)
    nm = new_pp.find(qn("hh", "margin"))
    if nm is not None:
        for t, v in want.items():
            el = nm.find(qn("hc", t))
            if el is not None:
                el.set("value", v)
    paraprops.append(new_pp)
    paraprops.set("itemCnt", str(len(paraprops.findall(qn("hh", "paraPr")))))
    cache[key] = new_id
    return new_id


def apply_space_hierarchy(header_root, section_roots):
    """계층 표현을 paraPr 들여쓰기 대신 리터럴 띄어쓰기로 전환한다(사용자 확정 '26.7.22):
    □ 0칸 / ㅇ 1칸 / 대시 3칸 / ＊·※ 5칸. 해당 문단 paraPr의 left·intent는 0화(복제 배정)."""
    p_tag = qn("hp", "p")
    cache = {}
    changed = {"prefixed": 0, "flattened": 0}
    for sec_root in section_roots:
        for child in sec_root:
            if child.tag != p_tag:
                continue
            kind = classify(child)
            if kind not in HIERARCHY_SPACES:
                continue
            spaces = " " * HIERARCHY_SPACES[kind]
            for run in child.findall(qn("hp", "run")):
                t = run.find(qn("hp", "t"))
                if t is not None and t.text and t.text.strip():
                    canonical = spaces + t.text.lstrip(" ")
                    if t.text != canonical:
                        t.text = canonical
                        changed["prefixed"] += 1
                    break
            base_id = child.get("paraPrIDRef")
            if base_id is not None:
                hang = HIERARCHY_HANG.get(kind, 0)
                new_id = ensure_hang_parapr(header_root, base_id, hang, cache)
                if new_id != base_id:
                    child.set("paraPrIDRef", new_id)
                    changed["flattened"] += 1
    return changed


def ensure_charpr_sized(header_root, base_id, height, cache):
    """base_id charPr을 폰트는 유지한 채 height(HWPUNIT)만 바꾼 복제본 id를 반환한다."""
    key = (base_id, height)
    if key in cache:
        return cache[key]
    charprops = header_root.find(f".//{qn('hh', 'charProperties')}")
    base = None
    for cp in charprops.findall(qn("hh", "charPr")):
        if cp.get("id") == base_id:
            base = cp
            break
    if base is None:
        cache[key] = base_id
        return base_id
    if base.get("height") == str(height):
        cache[key] = base_id
        return base_id
    new_cp = copy.deepcopy(base)
    max_id = max(int(cp.get("id")) for cp in charprops.findall(qn("hh", "charPr")))
    new_id = str(max_id + 1)
    new_cp.set("id", new_id)
    new_cp.set("height", str(height))
    charprops.append(new_cp)
    charprops.set("itemCnt", str(int(charprops.get("itemCnt", "0")) + 1))
    cache[key] = new_id
    return new_id



FIT_PAGE_SLACK = 283  # HWPUNIT(1.0mm) — R042: 총 폭은 본문 폭 '미만'이어야 한다(같으면 줄바꿈)


def apply_fit_page_width(section_roots):
    """표(머리말 배너·제목 박스 포함)의 총 폭이 본문 폭 - FIT_PAGE_SLACK을 넘으면 비례 축소한다.

    근거(R036): KCA 실보고서 12건 전수 실측 결과 머리말 배너 표 폭 == 본문 폭이 항상 성립한다
    (좌우 20mm 문서는 배너 170mm, 좌우 15mm 문서는 배너 179mm+여백 = 180mm). 배너 자산을
    좌우 15mm 문서에서 이식하면 좌우 20mm 문서에서 10mm 초과해 머리말이 밀리고 제목 박스
    상단에 여백이 남는다. 표 폭·셀 폭·내부 이미지 크기를 같은 비율로 줄여 정합을 맞춘다.

    정정(R042, '26.7.28 6차): 축소 목표가 '본문 폭과 정확히 같게'(여유 0)면 안 된다 — 같은
    문단에 표보다 앞선 요소가 있으면 한컴 엔진이 표를 다음 줄로 내려 표 위에 15pt 빈 줄이
    생긴다(제목표 실기동 A/B: slack 0 → 상단 30.29mm / 폭 축소 → 25.03mm). 그래서 목표를
    본문 폭 - FIT_PAGE_SLACK(283 hu = 1.0mm — 제목표·배너 자산의 outMargin 퀀텀과 동일한
    문서 그리드 최소 단위, 축소가 눈에 안 띄면서 등호 실패에서 충분히 멀다)으로 잡고,
    slack이 이미 FIT_PAGE_SLACK 이상인 표(본문 표 slack 1801 등)는 건드리지 않는다.
    축소 시 내부 그림의 파생 캐시(scaMatrix e1/e5 = curSz/orgSz, rotationInfo center =
    curSz/2)도 재계산한다 — sz·curSz만 줄이면 도너 원값 캐시가 스테일로 남는다.
    """
    adjusted = []
    for sec_root in section_roots:
        pagepr = None
        for pp in sec_root.iter(qn("hp", "pagePr")):
            pagepr = pp
            break
        if pagepr is None:
            continue
        margin = pagepr.find(qn("hp", "margin"))
        if margin is None:
            continue
        text_w = (int(pagepr.get("width", "0")) - int(margin.get("left", "0"))
                  - int(margin.get("right", "0")) - int(margin.get("gutter", "0")))
        if text_w <= 0:
            continue
        limit = text_w - FIT_PAGE_SLACK    # R042: 총 폭 상한(미만이 아니라 이하 — slack ≥ 566 보장)
        if limit <= 0:
            continue
        for tbl in sec_root.iter(qn("hp", "tbl")):
            sz = tbl.find(qn("hp", "sz"))
            om = tbl.find(qn("hp", "outMargin"))
            if sz is None:
                continue
            tw = int(sz.get("width", "0"))
            om_l = int(om.get("left", "0")) if om is not None else 0
            om_r = int(om.get("right", "0")) if om is not None else 0
            total = tw + om_l + om_r
            if total <= limit or tw <= 0:
                continue
            target = limit - om_l - om_r
            if target <= 0:            # 여백만으로도 초과 — 여백을 0으로 내리고 재계산
                if om is not None:
                    om.set("left", "0")
                    om.set("right", "0")
                om_l = om_r = 0
                target = limit
            ratio = target / tw
            sz.set("width", str(target))
            # 셀 폭: 마지막 셀에 반올림 잔차를 몰아 합계를 정확히 맞춘다
            rows = tbl.findall(qn("hp", "tr"))
            for tr in rows:
                cells = tr.findall(qn("hp", "tc"))
                widths, acc = [], 0
                for tc in cells:
                    csz = tc.find(qn("hp", "cellSz"))
                    widths.append(int(csz.get("width", "0")) if csz is not None else 0)
                new, run_sum = [], 0
                for i, w in enumerate(widths):
                    v = target - run_sum if i == len(widths) - 1 else int(round(w * ratio))
                    new.append(max(v, 1))
                    run_sum += new[-1]
                for tc, v in zip(cells, new):
                    csz = tc.find(qn("hp", "cellSz"))
                    if csz is not None:
                        csz.set("width", str(v))
            # 셀 안 그림도 같은 비율로 축소 (배너 로고·슬로건)
            pics = 0
            for pic in tbl.iter(qn("hp", "pic")):
                for tag in ("curSz", "sz"):
                    el = pic.find(qn("hp", tag))
                    if el is None:
                        continue
                    for attr in ("width", "height"):
                        v = el.get(attr)
                        if v is not None:
                            el.set(attr, str(max(int(round(int(v) * ratio)), 1)))
                # 파생 캐시 재계산 (R042 위생): scaMatrix e1/e5 = curSz/orgSz,
                # rotationInfo center = curSz/2 — sz·curSz만 줄이면 도너 원값이 스테일로 남는다.
                # transMatrix·scaMatrix의 e3/e6은 offset 파생이라 (offset 불변이므로) 건드리지 않는다.
                org = pic.find(qn("hp", "orgSz"))
                cur = pic.find(qn("hp", "curSz"))
                if org is not None and cur is not None:
                    ow, oh = int(org.get("width", "0")), int(org.get("height", "0"))
                    cw, ch = int(cur.get("width", "0")), int(cur.get("height", "0"))
                    ri = pic.find(qn("hp", "renderingInfo"))
                    sca = ri.find(qn("hc", "scaMatrix")) if ri is not None else None
                    if sca is not None and ow > 0 and oh > 0:
                        sca.set("e1", f"{cw / ow:.6f}")
                        sca.set("e5", f"{ch / oh:.6f}")
                    rot = pic.find(qn("hp", "rotationInfo"))
                    if rot is not None:
                        rot.set("centerX", str(cw // 2))
                        rot.set("centerY", str(ch // 2))
                pics += 1
            adjusted.append({"before_mm": round(total / 7200 * 25.4, 1),
                             "after_mm": round((target + om_l + om_r) / 7200 * 25.4, 1),
                             "ratio": round(ratio, 4), "pics_scaled": pics})
    return {"tables_fitted": len(adjusted), "detail": adjusted}


# 발신 줄 크기 실측값(R018, format-profile.kca.md §서체) — --all이 이 값을 기본 적용한다.
# 종전에는 호출자가 --sender-size 12를 매번 손으로 넘겨야 해 9곳 문서에 값이 복제됐고,
# 빠뜨리면 규칙 위반본이 그대로 나갔다.
SENDER_SIZE_PT = 12


def apply_sender_size(header_root, section_roots, pt):
    """발신 줄(classify=='sending') 문단 run의 charPr 크기를 pt로 치환한다."""
    height = int(round(pt * 100))
    p_tag = qn("hp", "p")
    cache = {}
    found = 0
    changed = 0
    for sec_root in section_roots:
        for child in sec_root:
            if child.tag != p_tag or classify(child) != "sending":
                continue
            found += 1
            for run in child.findall(qn("hp", "run")):
                base_id = run.get("charPrIDRef")
                if base_id is None:
                    continue
                new_id = ensure_charpr_sized(header_root, base_id, height, cache)
                if new_id != base_id:
                    run.set("charPrIDRef", new_id)
                    changed += 1
    return {"height": height, "sending_found": found, "runs_changed": changed}


def ensure_indent_parapr(header_root, base_id, left, intent, cache):
    """base_id paraPr을 margin.left=left·margin.intent=intent(HWPUNIT, 음수 허용)로
    바꾼 복제본 id를 반환한다. prev/next 여백은 base 값을 그대로 유지한다."""
    key = (base_id, left, intent)
    if key in cache:
        return cache[key]
    paraprops = header_root.find(f".//{qn('hh', 'paraProperties')}")
    base = None
    for pp in paraprops.findall(qn("hh", "paraPr")):
        if pp.get("id") == base_id:
            base = pp
            break
    if base is None:
        cache[key] = base_id
        return base_id
    margin = base.find(qn("hh", "margin"))
    if margin is not None:
        cur_left = margin.find(qn("hc", "left"))
        cur_intent = margin.find(qn("hc", "intent"))
        if (cur_left is not None and cur_left.get("value") == str(left)
                and cur_intent is not None and cur_intent.get("value") == str(intent)):
            cache[key] = base_id
            return base_id
    new_pp = copy.deepcopy(base)
    max_id = max(int(pp.get("id")) for pp in paraprops.findall(qn("hh", "paraPr")))
    new_id = str(max_id + 1)
    new_pp.set("id", new_id)
    nmargin = new_pp.find(qn("hh", "margin"))
    if nmargin is not None:
        nleft = nmargin.find(qn("hc", "left"))
        nintent = nmargin.find(qn("hc", "intent"))
        if nleft is not None:
            nleft.set("value", str(left))
        if nintent is not None:
            nintent.set("value", str(intent))
    paraprops.append(new_pp)
    paraprops.set("itemCnt", str(int(paraprops.get("itemCnt", "0")) + 1))
    cache[key] = new_id
    return new_id


CONTENT_KINDS = {"sending", "dae", "yo", "dash", "star", "cham", "arrow", "caption", "table",
                 "other"}


def apply_zero_margins(header_root, section_roots):
    """본문 최상위 콘텐츠 문단이 참조하는 paraPr의 위/아래 여백(prev/next)을 0으로.
    원본 양식 실측: 문단 여백 전부 0, 간격은 스페이서 문단만 담당 — kordoc preset이 넣는
    큰 위 여백(□ 30pt·ㅇ 20pt·대시 12pt)과 스페이서의 이중 간격을 제거한다."""
    p_tag = qn("hp", "p")
    used = set()
    for sec_root in section_roots:
        for child in sec_root:
            if child.tag == p_tag and classify(child) in CONTENT_KINDS:
                pid = child.get("paraPrIDRef")
                if pid is not None:
                    used.add(pid)
    zeroed = []
    for para_pr in header_root.iter(qn("hh", "paraPr")):
        if para_pr.get("id") not in used:
            continue
        margin = para_pr.find(qn("hh", "margin"))
        if margin is None:
            continue
        changed = {}
        for name in ("prev", "next"):
            el = margin.find(qn("hc", name))
            if el is not None and el.get("value") not in (None, "0"):
                changed[name] = el.get("value")
                el.set("value", "0")
        if changed:
            zeroed.append({"paraPr": para_pr.get("id"), "old": changed})
    return {"zeroed": zeroed, "count": len(zeroed)}


def effective_gaps(header_root, section_roots):
    """인접 콘텐츠 문단 쌍의 실효 간격(pt) = 사이 스페이서/빈 문단 charPr 높이 합
    + 다음 문단 paraPr.prev 여백. 검증 리포트용."""
    heights = {c.get("id"): int(c.get("height", "0")) for c in header_root.iter(qn("hh", "charPr"))}
    prevs = {}
    for para_pr in header_root.iter(qn("hh", "paraPr")):
        el = para_pr.find(qn("hh", "margin") + "/" + qn("hc", "prev")) if False else None
        margin = para_pr.find(qn("hh", "margin"))
        v = 0
        if margin is not None:
            pe = margin.find(qn("hc", "prev"))
            if pe is not None:
                v = int(pe.get("value", "0"))
        prevs[para_pr.get("id")] = v
    p_tag = qn("hp", "p")
    gaps = []
    for sec_root in section_roots:
        pending = 0
        prev_label = None
        for child in sec_root:
            if child.tag != p_tag:
                continue
            kind = classify(child)
            if kind == "empty":
                run = child.find(qn("hp", "run"))
                cid = run.get("charPrIDRef") if run is not None else None
                pending += heights.get(cid, 0)
                continue
            if kind in CONTENT_KINDS:
                if prev_label is not None:
                    total = pending + prevs.get(child.get("paraPrIDRef"), 0)
                    gaps.append({"between": f"{prev_label}→{kind}", "gap_pt": total / 100})
                prev_label = kind
                pending = 0
    return gaps


# ---------------------------------------------------------------------------
# zip 입출력
# ---------------------------------------------------------------------------

def serialize_xml(root):
    body = ET.tostring(root, encoding="unicode")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n' + body).encode("utf-8")


# ---------------------------------------------------------------------------
# 패키지 정합 (R043) — 내부망 자료교환 반입 판별
#
# kordoc generate_document 산출물은 hwpx 최소 패키지(mimetype·container.xml·
# content.hpf·header·section·PrvText + 디렉터리 엔트리 3개, 전량 STORED)라서
# 심층 구조 검사를 하는 반입 시스템이 hwpx로 판별하지 못한다 — mimetype+
# container.xml 만으로는 일반 OCF(EPUB류)와 지문이 같고, hwpx를 확정하는
# 마커인 version.xml이 없기 때문(→ octet-stream 판정 → 미등록 확장자 반려).
# 한컴 정품 실측('26.7.29, 도식 Pool.hwpx)의 멤버 구성·엔트리 순서·압축
# 프로파일로 정합한다. 템플릿 3종은 그 실측본에서 그대로 가져온 정본이다.
# ---------------------------------------------------------------------------

VERSION_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
    '<hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" '
    'tagetApplication="WORDPROCESSOR" major="5" minor="1" micro="1" buildNumber="0" '
    'os="1" xmlVersion="1.5" application="Hancom Office Hangul" '
    'appVersion="12, 0, 0, 3747 WIN32LEWindows_10"/>'
)

SETTINGS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
    '<ha:HWPApplicationSetting xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" '
    'xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0">'
    '<ha:CaretPosition listIDRef="0" paraIDRef="0" pos="0"/>'
    '<config:config-item-set name="PrintInfo">'
    '<config:config-item name="PrintAutoFootNote" type="boolean">false</config:config-item>'
    '<config:config-item name="PrintAutoHeadNote" type="boolean">false</config:config-item>'
    '<config:config-item name="PrintMethod" type="short">0</config:config-item>'
    '<config:config-item name="OverlapSize" type="short">0</config:config-item>'
    '<config:config-item name="PrintCropMark" type="short">0</config:config-item>'
    '<config:config-item name="BinderHoleType" type="short">0</config:config-item>'
    '<config:config-item name="ZoomX" type="short">100</config:config-item>'
    '<config:config-item name="ZoomY" type="short">100</config:config-item>'
    '</config:config-item-set></ha:HWPApplicationSetting>'
)

MANIFEST_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
    '<odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>'
)

_PKG_NUM = re.compile(r"(\d+)")
_PKG_MEDIA_EXT = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".wmf", ".emf")


def _pkg_order_key(name):
    """한컴 저장기 실측 엔트리 순서."""
    fixed = {"mimetype": 0, "version.xml": 1, "Contents/header.xml": 3,
             "Preview/PrvText.txt": 5, "settings.xml": 6, "Preview/PrvImage.png": 7,
             "META-INF/container.rdf": 8, "Contents/content.hpf": 9,
             "META-INF/container.xml": 10, "META-INF/manifest.xml": 11}
    if name in fixed:
        return (fixed[name], ())
    if name.startswith("BinData/"):
        nat = tuple((0, int(t)) if t.isdigit() else (1, t) for t in _PKG_NUM.split(name))
        return (2, nat)
    m = SECTION_RE.match(name)
    if m:
        return (4, ((0, int(_PKG_NUM.search(name).group(1))),))
    return (12, ((1, name),))


def _pkg_compress(name):
    """정품 압축 프로파일: mimetype·version.xml·미디어는 STORED, 나머지 DEFLATED."""
    if name in ("mimetype", "version.xml"):
        return zipfile.ZIP_STORED
    if name.startswith("BinData/") or name.lower().endswith(_PKG_MEDIA_EXT):
        return zipfile.ZIP_STORED
    return zipfile.ZIP_DEFLATED


def _build_container_rdf(section_names):
    ns0 = 'xmlns:ns0="http://www.hancom.co.kr/hwpml/2016/meta/pkg#"'
    pkg = "http://www.hancom.co.kr/hwpml/2016/meta/pkg#"
    parts = ['<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
             '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">',
             f'<rdf:Description rdf:about=""><ns0:hasPart {ns0} rdf:resource="Contents/header.xml"/></rdf:Description>',
             f'<rdf:Description rdf:about="Contents/header.xml"><rdf:type rdf:resource="{pkg}HeaderFile"/></rdf:Description>']
    for s in section_names:
        parts.append(f'<rdf:Description rdf:about=""><ns0:hasPart {ns0} rdf:resource="{s}"/></rdf:Description>')
        parts.append(f'<rdf:Description rdf:about="{s}"><rdf:type rdf:resource="{pkg}SectionFile"/></rdf:Description>')
    parts.append(f'<rdf:Description rdf:about=""><rdf:type rdf:resource="{pkg}Document"/></rdf:Description></rdf:RDF>')
    return "".join(parts)


def _build_container_xml(names):
    roots = ['<ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/>']
    if "Preview/PrvText.txt" in names:
        roots.append('<ocf:rootfile full-path="Preview/PrvText.txt" media-type="text/plain"/>')
    roots.append('<ocf:rootfile full-path="META-INF/container.rdf" media-type="application/rdf+xml"/>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
            '<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container" '
            'xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf">'
            '<ocf:rootfiles>' + "".join(roots) + '</ocf:rootfiles></ocf:container>')


def canonicalize_package(data):
    """data(멤버명→bytes)를 제자리 정합하고 (정본 순서 멤버명 목록, 요약)을 반환한다."""
    summary = {"added": [], "dirs_removed": 0, "scripts_removed": [],
               "container_rewritten": False, "settings_registered": False}
    for name in [n for n in data if n.endswith("/")]:
        del data[name]
        summary["dirs_removed"] += 1
    # Scripts 스텁 제거 — 한글 재저장 시 삽입되는 기본 빈 JScript(headerScripts·
    # sourceScripts)는 확장자 없는 멤버 + 활성콘텐츠라서 압축 내부까지 검사하는
    # 반입 시스템이 '등록되지 않은 확장자'로 반려한다('26.7.29 실측 — 실반려 문구
    # "header script에 등록되지 않은 확장자"가 이 멤버명이다). 기관보고서 인도본에
    # 매크로가 있을 이유가 없고 스텁은 기능 0이므로 전량 제거하고 hpf 등재도 걷는다.
    scripts = sorted(n for n in data if n.startswith("Scripts/"))
    if scripts:
        for n in scripts:
            del data[n]
        summary["scripts_removed"] = scripts
        hpf = data.get("Contents/content.hpf")
        if hpf is not None:
            removed_ids = [m.group(1) for m in
                           re.finditer(rb'<opf:item\s+id="([^"]+)"[^>]*href="Scripts/[^"]*"[^>]*/>', hpf)]
            hpf = re.sub(rb'<opf:item\b[^>]*href="Scripts/[^"]*"[^>]*/>', b"", hpf)
            for rid in removed_ids:
                hpf = re.sub(rb'<opf:itemref\s+idref="' + re.escape(rid) + rb'"[^>]*/>', b"", hpf)
            data["Contents/content.hpf"] = hpf
    section_names = sorted(n for n in data if SECTION_RE.match(n))
    for name, content in (("version.xml", VERSION_XML),
                          ("settings.xml", SETTINGS_XML),
                          ("META-INF/manifest.xml", MANIFEST_XML)):
        if name not in data:
            data[name] = content.encode("utf-8")
            summary["added"].append(name)
    if "META-INF/container.rdf" not in data:
        data["META-INF/container.rdf"] = _build_container_rdf(section_names).encode("utf-8")
        summary["added"].append("META-INF/container.rdf")
    cx = data.get("META-INF/container.xml")
    if cx is not None and b"container.rdf" not in cx:
        data["META-INF/container.xml"] = _build_container_xml(data).encode("utf-8")
        summary["container_rewritten"] = True
    hpf = data.get("Contents/content.hpf")
    if hpf is not None and b'href="settings.xml"' not in hpf and b"</opf:manifest>" in hpf:
        data["Contents/content.hpf"] = hpf.replace(
            b"</opf:manifest>",
            b'<opf:item id="settings" href="settings.xml" media-type="application/xml"/></opf:manifest>')
        summary["settings_registered"] = True
    return sorted(data, key=_pkg_order_key), summary


def process_file(path, star=False, spacing=False, sender_size=None,
                 header_banner=False):
    if not (star or spacing or sender_size is not None
            or header_banner):
        raise PostprocessError(
            "--star-footnote/--spacing/--sender-size/--header-banner/--all 중 최소 하나는 지정해야 합니다"
        )

    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        data = {info.filename: z.read(info.filename) for info in infos}

    header_root = ET.fromstring(data["Contents/header.xml"])
    section_names = sorted(n for n in data if SECTION_RE.match(n))
    section_roots = {n: ET.fromstring(data[n]) for n in section_names}

    summary = {"file": str(path), "sections": section_names}
    any_change = False
    any_target_found = False

    zero = spacing  # 스페이서 방식은 여백 0화와 한 몸 (원본 양식 정합)

    if star:
        r = apply_star_footnote(header_root, list(section_roots.values()))
        summary["star_footnote"] = r
        if r["stars_found"] > 0:
            any_target_found = True
        if r["runs_changed"] > 0:
            any_change = True

    if spacing:
        # 캡션 내장(R034)은 스페이서 계산 전에 수행 — 캡션 문단이 사라지면
        # X→caption·caption→table 전환이 X→table 전환으로 바뀐다
        cer = apply_caption_embed(header_root, list(section_roots.values()))
        summary["caption_embed"] = cer
        if cer["embedded"] > 0:
            any_target_found = True
            any_change = True

        r = apply_spacing(header_root, list(section_roots.values()))
        summary["spacing"] = {"inserted": r["inserted"], "modified": r["modified"],
                               "events": r["events"]}
        if r["events"]:
            any_target_found = True
            any_change = True

    if zero:
        zr = apply_zero_margins(header_root, list(section_roots.values()))
        summary["zero_margins"] = zr
        if zr["count"] > 0:
            any_target_found = True
            any_change = True
        summary["effective_gaps"] = effective_gaps(header_root, list(section_roots.values()))
        cr = apply_table_alignment(header_root, list(section_roots.values()))
        summary["table_alignment"] = cr
        if any(cr["aligned"].values()):
            any_target_found = True
            any_change = True
        sh = apply_space_hierarchy(header_root, list(section_roots.values()))
        summary["space_hierarchy"] = sh
        if sh["prefixed"] or sh["flattened"]:
            any_target_found = True
            any_change = True
        bj = apply_body_justify(header_root, list(section_roots.values()))
        summary["body_justify"] = bj
        if bj["found"] > 0:
            any_target_found = True
        if bj["changed"] > 0:
            any_change = True
        hl = apply_highlight(header_root, list(section_roots.values()))
        summary["highlight"] = hl
        if hl["highlights"] > 0:
            any_target_found = True
            any_change = True
        ps = apply_paren_small(header_root, list(section_roots.values()))
        summary["paren_small"] = ps
        if ps["paren_spans"] > 0:
            any_target_found = True
            any_change = True
        ss = apply_superscript_star(header_root, list(section_roots.values()))
        summary["superscript_star"] = ss
        if ss["stars_superscripted"] > 0:
            any_target_found = True
            any_change = True
        pm = apply_page_margins(list(section_roots.values()))
        summary["page_margins"] = pm
        if pm["attrs_changed"]:
            any_target_found = True
            any_change = True

        ccr = apply_center_cell_text(header_root, list(section_roots.values()))
        summary["center_cells"] = ccr
        if ccr["tables"] > 0:
            any_target_found = True
        if ccr["paragraphs"] > 0:
            any_change = True

        tbr = apply_title_box_borderless(header_root, list(section_roots.values()))
        summary["title_box"] = tbr
        if tbr["found"]:
            any_target_found = True
        if tbr["fills_replaced"] > 0:
            any_change = True

        tgr = apply_title_box_topgap(header_root, list(section_roots.values()))
        summary["title_box_topgap"] = tgr
        if tgr["anchors_fixed"] or tgr["outmargins_fixed"]:
            any_target_found = True
            any_change = True

        cfr = apply_caption_table_font(header_root, list(section_roots.values()))
        summary["caption_table_font"] = cfr
        if cfr["caption_runs_changed"] or cfr["cell_runs_changed"]:
            any_target_found = True
            any_change = True

        dbr = apply_dae_bold(header_root, list(section_roots.values()))
        summary["dae_bold"] = dbr
        if dbr["dae_found"] > 0:
            any_target_found = True
        if dbr["runs_changed"] > 0:
            any_change = True

        abr = apply_annex_banner(header_root, list(section_roots.values()))
        summary["annex_banner"] = abr
        if abr["banners"] > 0:
            any_target_found = True
        if abr["cell_runs_changed"] > 0 or abr["title_justified"] > 0:
            any_change = True

    if sender_size is not None:
        ssr = apply_sender_size(header_root, list(section_roots.values()), sender_size)
        summary["sender_size"] = ssr
        if ssr["sending_found"] > 0:
            any_target_found = True
        if ssr["runs_changed"] > 0:
            any_change = True

    if header_banner:
        hbr = apply_header_banner(header_root, list(section_roots.values()), data)
        summary["header_banner"] = hbr
        if hbr.get("injected"):
            any_target_found = True
            any_change = True
        geo = hbr.get("geometry") or {}
        if geo.get("linespacing_fixed") or geo.get("textwidth_fixed"):
            any_target_found = True
            any_change = True

    tp = apply_table_pagination(list(section_roots.values()))
    summary["table_pagination"] = tp
    if tp["attrs_fixed"] > 0:
        any_change = True

    fb = apply_formula_box(header_root, list(section_roots.values()))
    summary["formula_box"] = fb
    if fb["formula_boxes"] > 0:
        any_change = True

    lf = apply_line_fit(header_root, list(section_roots.values()))
    summary["line_fit"] = lf
    summary["layout"] = estimate_layout(header_root, list(section_roots.values()))
    if lf["fitted"] > 0:
        any_change = True

    fit = apply_fit_page_width(list(section_roots.values()))
    summary["fit_page_width"] = fit
    if fit.get("tables_fitted"):
        any_target_found = True
        any_change = True

    data["Contents/header.xml"] = serialize_xml(header_root)
    for name, root in section_roots.items():
        data[name] = serialize_xml(root)

    # 패키지 정합 (R043) — 플래그와 무관하게 매 실행 적용 (표 폭 정합과 동일 지위).
    # any_target_found에는 세지 않는다: exit 1(스타일 대상 0건 = 잘못된 파일 의심)
    # 가드를 유지하기 위해 — 정합 결과는 summary.package_canonical로 보고된다.
    canon_names, canon = canonicalize_package(data)
    summary["package_canonical"] = canon
    if canon["added"] or canon["dirs_removed"] or canon["container_rewritten"]:
        any_change = True

    by_name = {info.filename: info for info in infos}
    base_dt = infos[0].date_time if infos else (1980, 1, 1, 0, 0, 0)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(pathlib.Path(path).resolve().parent), suffix=".hwpx.tmp")
    os.close(tmp_fd)
    try:
        with zipfile.ZipFile(tmp_path, "w") as zout:
            for name in canon_names:
                src = by_name.get(name)
                zi = zipfile.ZipInfo(name, date_time=src.date_time if src else base_dt)
                zi.compress_type = _pkg_compress(name)
                if src is not None:
                    zi.external_attr = src.external_attr
                zout.writestr(zi, data[name])
        os.replace(tmp_path, path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    summary["changed"] = any_change
    summary["target_found"] = any_target_found
    return summary


USAGE = ("usage: postprocess_hwpx.py <file.hwpx> [--star-footnote] [--spacing] [--header-banner] [--all]\n"
         "                          [--sender-size PT]   (--all은 발신 줄 12pt를 기본 포함, PT 지정 시 재정의)\n"
         "exit 0: 변경 적용 완료 | exit 1: 스타일 대상 없음(패키지 정합만 적용됐을 수 있음) | exit 2: 인자/파일/구조 오류")


def main(argv):
    if len(argv) < 2:
        print(USAGE, file=sys.stderr)
        return 2
    path, rest = argv[0], argv[1:]
    valid_bool = {"--star-footnote", "--spacing", "--header-banner", "--all"}
    star = spacing = all_flag = header_banner = False
    sender_size = None
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg in valid_bool:
            if arg == "--star-footnote":
                star = True
            elif arg == "--spacing":
                spacing = True
            elif arg == "--header-banner":
                header_banner = True
            else:
                all_flag = True
            i += 1
        elif arg == "--sender-size":
            if i + 1 >= len(rest):
                print(USAGE, file=sys.stderr)
                return 2
            try:
                sender_size = float(rest[i + 1])
            except ValueError:
                print(USAGE, file=sys.stderr)
                return 2
            i += 2
        else:
            print(USAGE, file=sys.stderr)
            return 2

    star = star or all_flag
    spacing = spacing or all_flag
    header_banner = header_banner or all_flag
    if all_flag and sender_size is None:
        sender_size = SENDER_SIZE_PT
    if not (star or spacing or sender_size is not None
            or header_banner):
        print(USAGE, file=sys.stderr)
        return 2
    try:
        summary = process_file(path, star=star, spacing=spacing,
                                sender_size=sender_size,
                                header_banner=header_banner)
    except PostprocessError as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 2
    except (OSError, zipfile.BadZipFile, ET.ParseError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False))
    if not summary["target_found"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
