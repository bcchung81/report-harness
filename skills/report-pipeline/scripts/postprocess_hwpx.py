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
import sys, json, re, copy, math, zipfile, pathlib, tempfile, os, struct
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
# "< '26. 7. 22.(수), ... >" 형 발신 줄 — kordoc이 곧은따옴표를 ’로 바꿔 넣으므로 둥근따옴표도 받는다
# (종전에는 곧은따옴표만 받아 발신 줄이 캡션으로 분류돼 가운데 정렬·□ 앞 8pt가 됐다 — 인도본마다
# 수동 보정 스크립트를 따로 돌렸다, '26.9.24)
SENDING_RE = re.compile(r"^<\s*['’‘]?\d")
CAPTION_RE = re.compile(r"^[\[<]")     # "[ 표 제목 ]" / "< 표 제목 >" 형 캡션
DAE, STAR, CHAM, DASH, ARROW = "□", "＊", "※", "-", "☞"
YO_CHARS = ("ㅇ", "○")

# 전환 유형 → (이름, 스페이서 charPr 높이 HWPUNIT = pt*100)
TRANSITIONS = {
    ("sending", "dae"): ("sending_to_dae", 1200),   # 제목표 직후 첫 □ 12pt (R060)
    ("dae", "yo"): ("dae_to_yo", 600),
    ("yo", "yo"): ("yo_to_yo", 600),            # 연속 ㅇ 문단 사이 (사용자 확정)
    ("dash", "yo"): ("dash_to_yo", 600),        # 하위 대시에서 다음 ㅇ 복귀
    ("yo", "dash"): ("yo_to_dash", 300),   # ㅇ→대시는 3pt — 상위·하위가 한 덩어리로
                                           # 읽혀야 한다('26.9.10 사용자 확정 정정, 종전 6pt)
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
FIGURE_AFTER_GAP = 600       # 그림 → ㅇ·대시·표 6pt (R088 — X→ㅇ 전환 정합값, 산식 박스와도 띄운다)
ANNEX_BANNER_GAP = 800       # 붙임 배너(제목표) → 첫 요소 8pt 고정 (R009 — '26.9.24 사용자 지시)


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


def _para_is_banner(p):
    """문단 직속 표가 붙임·참고 배너(R027 3열 표)인가."""
    for run in p.findall(qn("hp", "run")):
        tbl = run.find(qn("hp", "tbl"))
        if tbl is not None and _is_banner_table(tbl):
            return True
    return False


def para_has_pic(p):
    for run in p.findall(qn("hp", "run")):
        if run.find(qn("hp", "pic")) is not None:
            return True
    return False


# 도식 표 표지(R089) — diagram_table.py가 그림 대신 넣은 표의 첫 셀 이름. kordoc이 제목 셀에 '__kordoc_h1'을
# 다는 것과 같은 방식이다. 도식 표는 좌표로 짠 격자라 일반 표 규칙(열 폭 재분배·행 높이·셀 가운데 정렬·12pt·
# 병합 음영·셀 단위 쪽 나눔·폭 축소)을 걸면 카드·화살표·연결선이 흐트러진다 — 캡션 내장·쪽 추정만 함께 받는다.
FIGURE_TABLE_NAME = "__harness_figure"


def is_figure_table(tbl):
    tc = tbl.find(f".//{qn('hp', 'tc')}")
    return tc is not None and tc.get("name") == FIGURE_TABLE_NAME


def classify(p):
    """문단 선두 기호로 계층 유형을 판정한다."""
    if para_has_table(p):
        return "table"
    text = para_text(p).strip()
    if text.startswith(QUOTE_MARK) or p.get("paraPrIDRef") in _QUOTE_PARAPRS:
        return "quote"                  # 원문 인용 줄(표식 또는 이미 상자 서식) — `- `·`[ ]`도 글자 그대로
    if not text:
        # 글자 없는 그림 문단은 빈 줄이 아니다 — 'empty'로 두면 캡션 내장이 캡션과 표 사이의
        # 빈 줄로 보고 그림을 지우고, 간격 단계가 그림 run의 글자 크기를 스페이서로 바꾼다
        # ('26.9.24 실측: 캡션 → 그림 → 산식 박스 순서에서 그림 문단 삭제, R088)
        return "figure" if para_has_pic(p) else "empty"
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
    # 붙임 배너(제목표) 다음 첫 요소는 무엇이든 8pt (R009)
    if prev_kind == "banner":
        return ("banner_to_" + next_kind, ANNEX_BANNER_GAP)
    next_kind = "table" if next_kind == "banner" else next_kind
    # 그림 뒤 ㅇ·대시 복귀와 아래 산식 박스·표는 6pt — 표→ㅇ 실측 전환이 없어 R013 체계의 X→ㅇ
    # 정합값을 쓴다(산식 박스가 도식에 붙어 보였다 — '26.9.24 게이트② 지적)
    if prev_kind == "figure" and next_kind in ("yo", "dash", "table"):
        return ("figure_to_" + next_kind, FIGURE_AFTER_GAP)
    # 그림·원문 인용 블록은 본문 흐름에서 표와 같은 자리를 차지한다 — 그 밖의 간격은 표 전환값을 쓴다
    if prev_kind == "quote" and next_kind == "quote":
        return None                                  # 인용 블록 안 — 줄 사이를 벌리지 않는다
    prev_kind = "table" if prev_kind in ("figure", "quote") else prev_kind
    next_kind = "table" if next_kind in ("figure", "quote") else next_kind
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
    """＊로 시작하는 각주 문단을 참고 스타일(13pt 맑은고딕)로 돌린다(R011).

    대상을 먼저 세고 참고 charPr은 **필요할 때만** 찾는다 — 종전에는 순서가 반대여서
    ＊ 문단이 하나도 없는 문서에서도 전제 실패로 예외를 던졌고, 그러면 `--all`의
    **뒤 단계가 통째로 건너뛰어진다**(머리말 배너·표 폭 정합·제목 박스 복원은 물론
    R043 패키지 정합까지). 실제 재현: 기관 서식 채움본 TASK-11 v6은 ＊ 0건인데
    13pt 글꼴이 맑은고딕이 아니라는 이유로 후처리 전 구간이 무적용됐다
    ('26.9.8 lessons 기록 → '26.9.10 조치).
    """
    targets = [p for sec_root in section_roots
               for p in sec_root.iter(qn("hp", "p"))
               if para_text(p).strip().startswith(STAR)]
    if not targets:
        return {"ref_charpr_id": None, "stars_found": 0, "runs_changed": 0,
                "skipped": "no_star_targets"}
    ref_id = find_ref_charpr_id(header_root)
    if ref_id is None:
        raise PostprocessError(
            "참고 charPr(header.xml height=1300·fontRef=맑은고딕 계열)을 찾지 못했습니다"
        )
    runs_changed = 0
    for p in targets:
        for run in p.findall(qn("hp", "run")):
            if run.get("charPrIDRef") != ref_id:
                run.set("charPrIDRef", ref_id)
                runs_changed += 1
    return {"ref_charpr_id": ref_id, "stars_found": len(targets),
            "runs_changed": runs_changed, "skipped": None}


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
    # 붙임 배너 표는 간격 판정에서만 따로 센다 — 다음 요소와 8pt(R009). 다른 단계의 'table' 판정은 그대로
    kinds = ["banner" if k == "table" and _para_is_banner(c) else k for k, c in zip(kinds, children)]
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
                if tbl is not None and not is_figure_table(tbl):   # 도식 표(R089)는 일반 표 규칙 밖
                    yield tbl, not seen_dae


def _title_box(header_root, section_roots):
    """문서의 제목 박스 표를 반환한다(없으면 None) — 제목 박스는 문서에 하나뿐이다.

    판정: 첫 □ 문단 이전의 표 가운데 배너가 아니고 **모든 행이 1열**이며 텍스트가 있는
    **첫 번째** 표. 종전에는 `_iter_content_tables`의 is_title(= 첫 □ 이전 표 전부)을
    그대로 제목 박스로 썼는데, kordoc 보고서 산출물은 그 구간에 요약 박스(1행 1열
    #DFE6F7)·문서정보표(2열)·장 배너(3열)를 함께 싣는다 — '26.9.10 실측에서 첫 □ 앞
    표 5개가 전부 제목 박스로 판정됐고, 그 결과 요약 박스가 제목 박스로 개조돼 음영을
    잃고 20pt로 부풀었다. 요약 박스는 제목 박스 **뒤**에 오므로 '첫 번째'만 취하면
    걸러지고, 문서정보표·장 배너는 1열 조건에서 걸러진다.
    """
    for tbl, is_title in _iter_content_tables(section_roots):
        if not is_title or _is_banner_table(tbl):
            continue
        rows = tbl.findall(qn("hp", "tr"))
        if not rows or any(len(tr.findall(qn("hp", "tc"))) != 1 for tr in rows):
            continue
        idx = _title_row_index(rows)
        if idx is None:
            continue
        # 제목 행 셀에는 채움이 없다(양식·실산출물 실측 — 채움은 밴드 행만 진다).
        # 위치만으로 판정하면 body_title_box=False 산출물에서 첫 1열 표가 요약 박스가
        # 되어 그 음영이 지워진다 — 판정에 양성 신호를 하나 둔다.
        cell_bf = rows[idx].find(qn("hp", "tc")).get("borderFillIDRef")
        for bf in header_root.iter(qn("hh", "borderFill")):
            if bf.get("id") == cell_bf:
                if bf.find(qn("hc", "fillBrush")) is not None:
                    cell_bf = None
                break
        if cell_bf is None:
            continue
        return tbl
    return None


def _title_row_index(rows):
    """제목 행(텍스트가 있는 첫 행)의 인덱스 — 밴드 행은 비어 있어 건너뛴다."""
    for idx, tr in enumerate(rows):
        if "".join(t.text or "" for t in tr.iter(qn("hp", "t"))).strip():
            return idx
    return None


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
# 제목 박스에서 지우는 테두리는 좌·우뿐이다 — kordoc이 제목표를 3행(밴드+제목+그라데이션
# 밴드)에서 1행(상·하 SOLID 0.4mm)으로 바꾼 뒤로는 4변을 전부 지우면 제목부의 유일한 시각
# 요소가 통째로 사라진다('26.9.8 실측 회귀). 원형 복원(apply_title_box_form)이 성립하면 밴드가
# 시각을 담당하고 3행 모두 4변 NONE이 되므로 이 처리는 무동작이다 — 복원이 불가능한 문서
# 형태(밴드 없는 1행 산출물)를 위한 안전망이다. format-profile §7이 적은 '밑줄 행 = 4변 실선'은
# 양식 OLE 원본의 서술이고, 인도본 계보는 밴드 4변 NONE이다(R022 미고침 사항·R084).
TITLE_BOX_STRIP_BORDERS = ("leftBorder", "rightBorder")


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
           for t in TITLE_BOX_STRIP_BORDERS):
        cache[base_id] = base_id
        return base_id
    new_bf = copy.deepcopy(base)
    max_id = max(int(bf.get("id")) for bf in borderfills.findall(qn("hh", "borderFill")))
    new_id = str(max_id + 1)
    new_bf.set("id", new_id)
    for t in TITLE_BOX_STRIP_BORDERS:
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
    tbl = _title_box(header_root, section_roots)
    if tbl is None:
        return {"found": False, "fills_replaced": 0}
    cache = {}
    replaced = 0
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


def ensure_keepnext_parapr(header_root, base_id, cache):
    """base_id paraPr에 '다음 문단과 함께'(breakSetting keepWithNext=1)를 건 복제본 id를 반환한다."""
    key = (base_id, "keepWithNext")
    if key in cache:
        return cache[key]
    paraprops = header_root.find(f".//{qn('hh', 'paraProperties')}")
    base = next((pp for pp in paraprops.findall(qn("hh", "paraPr")) if pp.get("id") == base_id), None)
    bs = base.find(qn("hh", "breakSetting")) if base is not None else None
    if bs is None or bs.get("keepWithNext") == "1":
        cache[key] = base_id
        return base_id
    new_pp = copy.deepcopy(base)
    new_id = str(max(int(pp.get("id")) for pp in paraprops.findall(qn("hh", "paraPr"))) + 1)
    new_pp.set("id", new_id)
    new_pp.find(qn("hh", "breakSetting")).set("keepWithNext", "1")
    paraprops.append(new_pp)
    paraprops.set("itemCnt", str(len(paraprops.findall(qn("hh", "paraPr")))))
    cache[key] = new_id
    return new_id


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


# 제목 박스 원형 (양식 실측 — 같은 파이프라인 산출물 3건이 동일: 이음5G '26.7.30 ·
# cert-poc '26.8.3 · xmos '26.8.7). 3행 1열이고 위·아래 3.8pt 밴드가 파란 띠를 만든다 —
# 0행 단색 #0080C0, 2행 방사형 그라데이션 #0080C0 → #3CBFFF, 1행이 제목(28.5pt).
# kordoc이 '26.9월 이 구조를 1행(상·하 실선·채움 없음)으로 바꾸면서 파란 띠가 원천에서
# 사라졌다. 파이프라인에는 제목표를 만드는 단계가 애초에 없었고(후처리는 있는 fillBrush를
# 보존만 한다) 생성기 산출물에 의존해 왔다 — 그 의존을 여기서 끊는다.
TITLE_BOX_BAND_HEIGHT = 382      # 3.8pt 밴드 행
TITLE_BOX_TITLE_HEIGHT = 2850    # 28.5pt 제목 행
TITLE_BOX_SIDE_MARGIN = 283      # outMargin 좌·우 (1.0mm)
TITLE_BOX_BAND_PT = 1            # 밴드 행 빈 run 크기
TITLE_BOX_TOP_FILL = '<hc:winBrush faceColor="#0080C0" hatchColor="#000000" alpha="0"/>'
TITLE_BOX_BOTTOM_FILL = (
    '<hc:gradation type="RADIAL" angle="0" centerX="0" centerY="0" step="50"'
    ' colorNum="2" stepCenter="50" alpha="0">'
    '<hc:color value="#0080C0"/><hc:color value="#3CBFFF"/></hc:gradation>')


def ensure_title_band_fill(header_root, base_id, fill_xml, cache):
    """base_id borderFill을 4변 NONE + 지정 fillBrush로 바꾼 복제본 id를 반환한다."""
    key = (base_id, fill_xml)
    if key in cache:
        return cache[key]
    borderfills = header_root.find(f".//{qn('hh', 'borderFills')}")
    base = None
    for bf in borderfills.findall(qn("hh", "borderFill")):
        if bf.get("id") == base_id:
            base = bf
            break
    if base is None:
        cache[key] = base_id
        return base_id
    new_bf = copy.deepcopy(base)
    new_id = str(max(int(bf.get("id")) for bf in borderfills.findall(qn("hh", "borderFill"))) + 1)
    new_bf.set("id", new_id)
    for t in BORDER_TAGS:
        el = new_bf.find(qn("hh", t))
        if el is not None:
            el.set("type", "NONE")
    old_fill = new_bf.find(qn("hc", "fillBrush"))
    if old_fill is not None:
        new_bf.remove(old_fill)
    if fill_xml:
        wrapped = (f'<hc:fillBrush xmlns:hc="{NS["hc"]}">{fill_xml}</hc:fillBrush>')
        new_bf.append(ET.fromstring(wrapped))
    borderfills.append(new_bf)
    borderfills.set("itemCnt", str(int(borderfills.get("itemCnt", "0")) + 1))
    cache[key] = new_id
    return new_id


def apply_title_box_form(header_root, section_roots):
    """제목 박스를 양식 원형(제목 행을 파란 밴드 + 그라데이션 밴드로 감싼 꼴)으로 되돌린다.

    원형 실측 3건은 3행 1열 — 0행 단색 밴드·1행 제목·2행 그라데이션 밴드다. kordoc
    `report_info`를 쓰면 제목 행 아래에 담당자 행이 하나 더 붙는데(2행 산출), 이때도
    **제목 행만** 감싸고 부가 행은 그대로 둔다(원형에 없는 행이라 손대지 않는다).
    이미 감싸여 있으면 무동작이다(멱등). 대상을 못 찾거나 건너뛴 사유는 summary의
    `skipped`로 남긴다 — '대상 없음'과 '조용한 실패'가 구분되지 않던 결함의 대책.
    """
    result = {"restored": 0, "band_height": TITLE_BOX_BAND_HEIGHT, "skipped": None}
    tbl = _title_box(header_root, section_roots)
    if tbl is None:
        result["skipped"] = "no_title_box"
        return result
    rows = tbl.findall(qn("hp", "tr"))
    idx = _title_row_index(rows)
    if idx is None:
        result["skipped"] = "no_title_row"
        return result
    if idx > 0:
        # 1열 제목 박스에서 제목 행 위에 올 수 있는 행은 밴드(빈 행)뿐이다 — 이미 원형이다.
        # 채움 유무로 판정하지 않는다: 밴드가 채움을 잃은 상태를 행 삽입으로 고치면
        # 행이 불어난다(R022 '행 삭제 금지'의 대칭 — 있는 밴드는 그대로 둔다).
        result["skipped"] = "already_restored"
        return result
    title_tc = rows[idx].find(qn("hp", "tc"))
    base_bf = title_tc.get("borderFillIDRef")
    sz = tbl.find(qn("hp", "sz"))
    cell_sz = title_tc.find(qn("hp", "cellSz"))
    if base_bf is None or sz is None or cell_sz is None:
        result["skipped"] = "incomplete_geometry"
        return result

    cache, char_cache = {}, {}
    # 총 폭(표 폭 + outMargin 좌우)을 보존한 채 원형 여백으로 되돌린다
    out = tbl.find(qn("hp", "outMargin"))
    if out is None:
        # 없으면 만든다 — 폭만 줄이고 여백을 안 만들면 총 폭이 1mm 조용히 줄어든다
        out = ET.SubElement(tbl, qn("hp", "outMargin"))
        tbl.remove(out)
        tbl.insert(min(1, len(tbl)), out)
    prev_side = int(out.get("left") or 0) + int(out.get("right") or 0)
    out.set("left", str(TITLE_BOX_SIDE_MARGIN))
    out.set("right", str(TITLE_BOX_SIDE_MARGIN))
    out.set("top", "0")
    out.set("bottom", str(TITLE_BOX_SIDE_MARGIN))
    width = int(sz.get("width")) + prev_side - 2 * TITLE_BOX_SIDE_MARGIN
    cell_sz.set("height", str(TITLE_BOX_TITLE_HEIGHT))
    title_tc.set("borderFillIDRef",
                 ensure_title_band_fill(header_root, base_bf, "", cache))
    tbl_bf = tbl.get("borderFillIDRef")
    if tbl_bf is not None:   # 원형의 표 자체 테두리도 4변 NONE (밴드가 시각을 담당)
        tbl.set("borderFillIDRef",
                ensure_title_band_fill(header_root, tbl_bf, "", cache))

    bands = []
    for fill in (TITLE_BOX_TOP_FILL, TITLE_BOX_BOTTOM_FILL):
        band_tr = copy.deepcopy(rows[idx])
        band_tc = band_tr.find(qn("hp", "tc"))
        band_tc.set("name", "")
        band_tc.set("borderFillIDRef",
                    ensure_title_band_fill(header_root, base_bf, fill, cache))
        for run in band_tc.iter(qn("hp", "run")):
            t = run.find(qn("hp", "t"))
            if t is not None:
                t.text = None
            base_cid = run.get("charPrIDRef")
            if base_cid is not None:
                run.set("charPrIDRef", ensure_charpr_sized(
                    header_root, base_cid, TITLE_BOX_BAND_PT * 100, char_cache))
        bsz = band_tc.find(qn("hp", "cellSz"))
        if bsz is not None:
            bsz.set("height", str(TITLE_BOX_BAND_HEIGHT))
        bands.append(band_tr)
    pos = list(tbl).index(rows[idx])
    tbl.insert(pos, bands[0])
    tbl.insert(pos + 2, bands[1])
    tbl.set("rowCnt", str(len(rows) + 2))

    # 삽입으로 행 번호가 밀렸다 — 폭·행 주소를 전 행에 다시 매기고 총 높이를 재계산한다
    heights = []
    for row_addr, tr in enumerate(tbl.findall(qn("hp", "tr"))):
        tc = tr.find(qn("hp", "tc"))
        addr = tc.find(qn("hp", "cellAddr"))
        if addr is not None:
            addr.set("rowAddr", str(row_addr))
        csz = tc.find(qn("hp", "cellSz"))
        if csz is not None:
            csz.set("width", str(width))
            heights.append(int(csz.get("height")))
    sz.set("width", str(width))
    if len(heights) == len(tbl.findall(qn("hp", "tr"))):
        sz.set("height", str(sum(heights)))
    result["restored"] = 1
    return result


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
    # 도식 표(R089)는 셀 글자 크기를 도식이 정하므로 두고, 내장된 캡션만 표 캡션과 같게 맞춘다
    for sec_root in section_roots:
        for tbl in sec_root.iter(qn("hp", "tbl")):
            cap = tbl.find(qn("hp", "caption"))
            if cap is None or not is_figure_table(tbl):
                continue
            for run in cap.iter(qn("hp", "run")):
                base_id = run.get("charPrIDRef")
                new_id = ensure_charpr_sized(header_root, base_id, height, cache) if base_id else base_id
                if new_id != base_id:
                    run.set("charPrIDRef", new_id)
                    caption_runs += 1
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
# 맞춤 여유 — 추정 폭(한글 1·영숫자 0.5)은 가운뎃점·공백·양쪽 정렬을 다 담지 못해 경계(2.00줄)까지 채우면
# 실제 글꼴에서 3줄이 된다('26.9.24 게이트② 지적 □2-ㅇ1-1 — 추정 1.96~2.00줄 대시 3건이 화면에서 3줄).
# 맞출 때만 폭을 이만큼 좁혀 계산한다(쪽수 추정은 그대로).
FIT_SLACK = 0.97


def _para_text(p):
    out = []
    for run in p.findall(qn("hp", "run")):
        for t in run.findall(qn("hp", "t")):
            out.append("".join(t.itertext()))
    return "".join(out)


# 라틴-1 영역이지만 한글 글꼴(KS X 1001 기호)에서 전각으로 그려지는 글자 — 보고서에 잦은 가운뎃점이
# 대표다. 반각으로 세면 '검수·수정·추정'처럼 점이 많은 문단이 2줄로 계산되고 실제로는 3줄이 된다
# ('26.9.24 실측: 명조 글꼴에서 · 0.97em, 한글 0.97em, 숫자 0.61em, 공백 0.37em).
FULLWIDTH_LATIN1 = frozenset("·×÷°±§")


def _weighted_len(text):
    """한글·전각 1.0, 영숫자·기호 0.5로 가중한 글자 폭 환산 길이(가운뎃점 등 KS X 1001 기호는 전각)."""
    w = 0.0
    for ch in text:
        if ch.isspace():
            w += 0.5
        elif ord(ch) > 0x2000 or ch in FULLWIDTH_LATIN1:
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
    """본문 글자 폭에서 빠지는 왼쪽 몫(pt) — 왼쪽 여백 + 내어쓰기 폭(intent 음수).

    계층 문단은 내어쓰기로 부호를 첫 줄 앞 칸에 두고, 본문은 모든 줄에서 그 뒤에 선다. 종전에는
    왼쪽 여백만 읽어 □·ㅇ·- 문단이 전부 0으로 잡혔고, 2줄로 계산해 둔 문단이 한글에서 3줄이
    됐다('26.9.24 시험 변환 실측, R062)."""
    for pr in header_root.iter(qn("hh", "paraPr")):
        if pr.get("id") != para_pr_id:
            continue
        mg = pr.find(qn("hh", "margin"))
        if mg is None:
            return 0.0
        left, intent = mg.find(qn("hc", "left")), mg.find(qn("hc", "intent"))
        lv = int(left.get("value", "0")) if left is not None else 0
        iv = int(intent.get("value", "0")) if intent is not None else 0
        return (lv + max(0, -iv)) / 100.0
    return 0.0


MARK_LEAD = re.compile(r"^\s*[□ㅇ○＊※☞-]\s*")


def _body_len(text, indent_pt):
    """줄 수 계산에 쓰는 본문 길이 — 내어쓰기 문단은 앞 공백·부호가 내어쓰기 칸에 들어가므로 뺀다."""
    return _weighted_len(MARK_LEAD.sub("", text, count=1) if indent_pt else text)


def _text_runs(p):
    """글자가 있는 run 목록 — 공백·부호만 든 run(내어쓰기 칸의 부호)은 뺀다."""
    out = []
    for run in p.findall(qn("hp", "run")):
        text = "".join("".join(t.itertext()) for t in run.findall(qn("hp", "t")))
        if MARK_LEAD.sub("", text).strip():
            out.append((run, text))
    return out


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


def lines_at(wl, avail, h, ratio, spacing, words=None):
    """가중 길이 wl인 문단이 폭 avail(pt)·글자 h(pt)·장평 ratio·자간 spacing에서 차지하는 줄 수(추정).

    words(어절별 가중 길이)를 주면 어절 단위로 채운다 — 줄 끝 어절이 다음 줄로 넘어가 남는 빈자리까지
    센다. 글자 단위 채움(wl만)으로 2줄이던 문단이 어절 단위 화면·렌더에서 3줄이 됐다('26.9.24)."""
    adv = h * (ratio / 100.0 + spacing / 100.0)
    if adv <= 0:
        return 99
    cap = max(1.0, avail / adv)
    if not words:
        return math.ceil(wl / cap)
    lines, cur = 1, 0.0
    for w in words:
        need = w if cur == 0 else cur + 0.5 + w
        if need <= cap:
            cur = need
            continue
        if cur:                                  # 어절째 다음 줄로
            lines += 1
        lines += int(w // cap) if w > cap else 0  # 한 줄보다 긴 어절은 글자로 쪼개진다
        cur = w % cap if w > cap else w
    return lines


def word_lens(text):
    """어절별 가중 길이 — lines_at(words=)용."""
    return [_weighted_len(w) for w in text.split()]


def fit_line(wl, avail, h, ratio0, sp0, max_lines=2, words=None):
    """max_lines 안에 들게 하는 (장평, 자간) — 자간을 먼저 하한까지, 그다음 장평을 조인다(R062).

    이미 들어가면 (ratio0, sp0), 하한까지 조여도 넘치면 None. 리뷰 HTML(render_review_html)도
    같은 계산을 써 한글 산출물과 같은 줄 수로 보여 준다. 폭은 FIT_SLACK만큼 좁혀 여유를 둔다."""
    avail = avail * FIT_SLACK
    if lines_at(wl, avail, h, ratio0, sp0, words) <= max_lines:
        return (ratio0, sp0)
    for spacing in range(sp0, MIN_SPACING - 1, -1):
        if lines_at(wl, avail, h, ratio0, spacing, words) <= max_lines:
            return (ratio0, spacing)
    for ratio in range(ratio0, MIN_RATIO - 1, -1):
        if lines_at(wl, avail, h, ratio, MIN_SPACING, words) <= max_lines:
            return (ratio, MIN_SPACING)
    return None


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
            runs = _text_runs(child)
            if not runs:
                continue
            # 기준은 글자가 가장 많은 run(본문) — 첫 run은 부호 칸이라 kordoc 값과 다르다. 종전에는 첫
            # run 값으로 계산하고 첫 run과 같은 charPr만 조여, ㅇ 문단의 볼드 리드·본문이 그대로 남았다
            # ('26.9.24 시험 변환 실측 — 2줄로 보고한 ㅇ 16건 중 다수가 한글에서 3줄)
            body_cid = max(runs, key=lambda r: len(r[1]))[0].get("charPrIDRef")
            if body_cid is None:
                continue
            h, ratio0, sp0 = _charpr_metrics(header_root, body_cid)
            indent = _para_indent_pt(header_root, child.get("paraPrIDRef") or "")
            avail = width - indent
            wl = _body_len(text, indent)
            words = word_lens(MARK_LEAD.sub("", text, count=1) if indent else text)
            chosen = fit_line(wl, avail, h, ratio0, sp0, max_lines, words)
            if chosen == (ratio0, sp0):
                continue
            if chosen is None:
                overflow.append({"text": text[:40], "chars": len(text),
                                 "lines": lines_at(wl, avail, h, MIN_RATIO, MIN_SPACING, words)})
                continue
            for run, _ in runs:                   # 모든 글자 run을 조이되, 이미 더 조인 run은 그대로 둔다
                cid = run.get("charPrIDRef")
                _, r0, s0 = _charpr_metrics(header_root, cid)
                target = (min(r0, chosen[0]), min(s0, chosen[1]))
                if target != (r0, s0):
                    run.set("charPrIDRef", ensure_charpr_fitted(header_root, cid, target[0], target[1], cache))
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
    parts = []                                   # 붙임 배너마다 새 쪽 — (줄 수, 표·그림 높이) 구간
    for sec_root in section_roots:
        width = _text_width_pt(sec_root)
        for child in sec_root:
            if child.tag != p_tag:
                continue
            if any(_is_banner_table(t) for t in child.iter(qn("hp", "tbl"))):
                parts.append((lines, tbl_h))             # 붙임은 새 쪽에서 시작한다
            for tbl in child.iter(qn("hp", "tbl")):
                rows = int(tbl.get("rowCnt", "1"))
                cols = max(1, int(tbl.get("colCnt", "1")))
                tbl_rows += rows
                tsz = tbl.find(qn("hp", "sz"))
                if tsz is not None and int(tsz.get("height", "0")) > 0:
                    tbl_h += int(tsz.get("height")) / 100.0      # row_fit이 최종 열 폭으로 다시 적은 높이
                    continue
                # 높이가 없는 표 — 셀 텍스트가 균등 열 폭 안에서 몇 줄로 접히는지로 가늠한다
                col_chars = max(4.0, (_text_width_pt(sec_root) / cols) / 6.5)  # 표 12pt 기준
                for tr in tbl.iter(qn("hp", "tr")):
                    tallest = 1
                    for tc in tr.iter(qn("hp", "tc")):
                        ln = _weighted_len("".join(t for t in tc.itertext()))
                        tallest = max(tallest, math.ceil(ln / col_chars))
                    tbl_h += tallest * 12.0 * 1.6 + 4.0
            kind = classify(child)
            if kind == "figure":                  # 그림 높이(sz, HWPUNIT/100 = pt)를 표 몫에 더한다
                tbl_h += sum(int(sz.get("height", "0")) / 100.0 for run in child.findall(qn("hp", "run"))
                             for pic in run.findall(qn("hp", "pic")) for sz in pic.findall(qn("hp", "sz")))
                continue
            text = _para_text(child)
            if kind == "quote":                   # 원문 인용 줄 — 제 글자 크기·줄간격 130%로 표 몫에 더한다(본문 줄 높이로 세면 과대)
                run = child.find(qn("hp", "run"))
                qh = _charpr_metrics(header_root, run.get("charPrIDRef") if run is not None else "")[0]
                n = max(1, math.ceil(_weighted_len(text) * qh / max(1.0, width - 11.3)))
                tbl_h += n * qh * QUOTE_LINE_SPACING / 100.0
                continue
            if not text.strip():
                continue
            runs = _text_runs(child)
            if not runs:
                continue
            h, ratio, sp = _charpr_metrics(header_root, max(runs, key=lambda r: len(r[1]))[0].get("charPrIDRef") or "")
            line_h = max(line_h, h)
            indent = _para_indent_pt(header_root, child.get("paraPrIDRef") or "")
            avail = width - indent
            adv = h * (ratio / 100.0 + sp / 100.0)
            n = math.ceil(_body_len(text, indent) / max(1.0, avail / max(adv, 0.1)))
            lines += n
            if kind in LINE_FIT_KINDS and n > 2:
                over2 += 1
    body_pt = lines * line_h * 1.6            # 줄간격 160%
    marks = [(0, 0.0)] + parts + [(lines, tbl_h)]
    by_part = [max(1, math.ceil(((l1 - l0) * line_h * 1.6 + (t1 - t0)) / 700.0))   # A4 본문 247mm ≈ 700pt
               for (l0, t0), (l1, t1) in zip(marks, marks[1:])]
    return {"paragraph_lines": lines, "table_rows": tbl_rows, "over_two_lines": over2,
            "est_pt": round(body_pt + tbl_h), "est_pages": sum(by_part), "pages_by_part": by_part}


# 본문 자리를 차지하는 표의 배치 속성 (한컴 저장본·기관 양식 원본 전수 실측 — R063 확장).
# kordoc 산출 표에는 이 셋이 아예 없다('26.9.10 실측: 인도본 17건에서 표 246개 중 218개
# 누락, 붙어 있는 28개는 전부 이식 자산인 머리말 배너·제목 박스였다). 배치가 정해지지
# 않으면 한글이 표를 본문 흐름 밖 개체로 다뤄 **페이지 경계에서 나뉘지 않고 통째로 다음
# 장으로 밀린다** — pageBreak=CELL을 걸어도 소용이 없다.
TABLE_PLACEMENT = {"textWrap": "TOP_AND_BOTTOM", "textFlow": "BOTH_SIDES", "lock": "0"}


def apply_table_pagination(section_roots, rows_per_page=22):
    """표가 페이지를 벗어날 때의 처리를 강제한다 (R063).

    ① 본문 자리 차지 배치(textWrap=TOP_AND_BOTTOM·textFlow=BOTH_SIDES) ② 셀 단위
    페이지 분할 허용(pageBreak=CELL) ③ 첫 행 제목 반복(repeatHeader=1)을 모든 표에
    보장하고, 한 페이지를 넘길 것으로 보이는 표는 oversized로 보고한다."""
    fixed, oversized = 0, []
    for sec_root in section_roots:
        for tbl in sec_root.iter(qn("hp", "tbl")):
            if is_figure_table(tbl):        # 도식은 쪽 경계에서 쪼개지면 안 된다 — diagram_table이 둔 NONE 유지(R089)
                continue
            rows = int(tbl.get("rowCnt", "1"))
            cols = int(tbl.get("colCnt", "1"))
            for attr, value in TABLE_PLACEMENT.items():
                if tbl.get(attr) is None:      # 기존 값은 존중한다 — 없을 때만 채운다
                    tbl.set(attr, value)
                    fixed += 1
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
            "rule": "textWrap=TOP_AND_BOTTOM + textFlow=BOTH_SIDES + pageBreak=CELL + repeatHeader=1"}


def apply_formula_box(header_root, section_roots):
    """1행 1열 표를 산식 박스로 규격화한다 (R064) — 본문 폭 전체·가운데 정렬."""
    boxed = 0
    p_tag = qn("hp", "p")
    # 문서 전체에서 공유한다 — 문단마다 새 dict를 넘기면 dedup이 무효가 되어 동일한 CENTER
    # paraPr 복제본이 산식 박스 문단 수만큼 header에 쌓인다
    align_cache = {}
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
                              ensure_aligned_clone(header_root, pid, "CENTER", align_cache))
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


def _explode_inline_runs(p):
    """hp:t 안에 인라인 요소(`<hp:nbSpace/>`·`<hp:tab/>` 등)가 섞인 run을 글자 조각 run과 요소 run으로 나눈다.

    같은 charPr·같은 순서라 조판은 그대로이고, 글자 조각은 단순 run이 되어 괄호 축소(R033·R039)·강조(R040) 같은
    분할 처리를 받는다 — kordoc이 '180만 원'의 숫자·단위 사이에 nbSpace를 넣어, 같은 run 안 괄호 '(1인당 월평균
    15건)'이 분할 불가로 건너뛰어져 15pt로 남았다('26.9.25 하네스 실전 점검). 나눈 run 수를 돌려준다."""
    n = 0
    for run in list(p.findall(qn("hp", "run"))):
        kids = list(run)
        if run.get("charPrIDRef") is None or len(kids) != 1 or kids[0].tag != qn("hp", "t") or not len(kids[0]):
            continue
        t = kids[0]
        if len(t) == 1 and not t.text and not t[0].tail:
            continue                     # 요소 하나뿐인 run — 이미 나뉜 조각(재실행 멱등)
        pieces = [t.text] if t.text else []
        for c in list(t):
            tail, c.tail = c.tail, None
            pieces.append(c)
            if tail:
                pieces.append(tail)
        pos = list(p).index(run)
        p.remove(run)
        for i, piece in enumerate(pieces):
            new_run = ET.Element(qn("hp", "run"), dict(run.attrib))
            nt = ET.SubElement(new_run, qn("hp", "t"), dict(t.attrib))
            if isinstance(piece, str):
                nt.text = piece
            else:
                nt.append(piece)
            p.insert(pos + i, new_run)
        n += 1
    return n


def _para_run_infos(p):
    """문단 직속 run들의 (run, text, start, end, simple) 목록과 전체 텍스트를 반환한다.
    simple = 자식이 순수 텍스트 hp:t 하나뿐이고 charPrIDRef가 있어 _split_run 분할 가능.
    text는 인라인 요소 뒤 글자(tail)까지 담는다 — 빠뜨리면 뒤 run들의 위치가 어긋난다."""
    infos = []
    full = ""
    for run in p.findall(qn("hp", "run")):
        t = run.find(qn("hp", "t"))
        text = "".join(t.itertext()) if t is not None else ""
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
    exploded = 0
    for sec_root in section_roots:
        for child in sec_root:
            if child.tag != p_tag or classify(child) not in PAREN_KINDS:
                continue
            infos, full = _para_run_infos(child)
            if "(" not in full or ")" not in full:
                continue
            if any(not i["simple"] for i in infos):
                exploded += _explode_inline_runs(child)
                infos, full = _para_run_infos(child)
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
            "inline_runs_split": exploded, "height": height}


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
            if any(not i["simple"] for i in infos):
                _explode_inline_runs(child)
                infos, full = _para_run_infos(child)
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


HIERARCHY_SPACES = {"dae": 0, "yo": 1, "dash": 3, "star": 3, "cham": 3, "arrow": 3}
# 줄바꿈 시 둘째 줄 들여쓰기(=본문 시작 위치, HWPUNIT). 첫 줄은 intent=-left로 0에서 시작
# ※ 값은 폰트 크기가 아니라 "그 폰트 글자폭의 배수"(□1.5글자·ㅇ2글자·대시2.5글자·＊3글자) — 사용자 보고 시 글자 단위 병기
# (리터럴 공백이 마커 위치를 잡고, 랩된 줄은 left 위치에 정렬 — 사용자 확정 '26.7.22)
# 산출: 공백폭=글자크기/2 — dae 0+□15+공백7.5 / yo 공백7.5+ㅇ15+7.5 / dash 22.5+대시7.5+7.5
#       star·cham(13pt) 공백 3×6.5+기호13+6.5 / arrow(15pt 본문) 공백 3×7.5+기호15+7.5 (R025)
#       ＊·※·☞ 선두 3칸('26.9.24 사용자 정정 — 종전 5칸, 표 아래 ※가 표와 어울리게, R019)
HIERARCHY_HANG = {"dae": 2250, "yo": 3000, "dash": 3750, "star": 3900, "cham": 3900,
                  "arrow": 4500}


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
    □ 0칸 / ㅇ 1칸 / 대시 3칸 / ＊·※ 3칸. 해당 문단 paraPr의 left·intent는 0화(복제 배정)."""
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



# 열 폭 재배분 (R036 계열 — 표 총 폭은 건드리지 않는다).
# kordoc generate_document의 열 폭 산정이 내용량과 무관해, 가장 긴 열이 가장 좁아지면
# 행 높이가 불어나 표가 페이지를 넘긴다 — '26.9.8 실측: 3열 표에서 내용 열 30.8% ·
# 주제 열 49.8%로 역전돼 표 높이가 141mm(A4 본문의 60%)까지 늘었다.
# 열 폭 하한은 **비중이 아니라 머리글 실폭**이다 — 종전의 정률 하한 10%·상한 60%는
# 기관 보고서의 전형인 `구 분 | 담당 | 내 용` 표에서 거꾸로 작동했다: kordoc이 이미
# 내용 열에 74%를 준 표를 상한 60%로 끌어내리고 그만큼을 라벨 열에 얹어 내용 열이
# **좁아졌다**('26.9.10 실측 35315→28515). 내용 비례 배분이 목적인 단계가 정률 상한과
# 싸운 셈이다. 하한은 '머리글이 한 줄에 들어갈 만큼'으로 족하고, 상한은 다른 열의
# 하한 합에서 자연히 나온다.
# 표 셀 12pt(R023) 기준 글자 폭(HWPUNIT). _weighted_len은 줄 길이 판정용이라 ASCII를
# 0.5로 세는데, 그 값으로 열 하한을 잡으면 `No`가 `N`/`o`로 쪼개진다('26.9.10 렌더 실측).
COL_FIT_HANGUL_HU = 1200   # 한글·전각 = 12pt 전각
COL_FIT_ASCII_HU = 800     # 영숫자·기호
COL_FIT_SPACE_HU = 600     # 공백
COL_FIT_CELL_PAD = 1020    # 셀 좌우 안여백 — kordoc 산출 표 inMargin 510×2 실측(종전 283×2는 좁은 열에서 글자가 여백에 물렸다)
COL_FIT_FLOOR_MAX = 0.25   # 열 하나의 하한 상한(표 폭 대비) — 긴 서술 열이 하한을 독식하지 않게
COL_FIT_FLOOR_CAP = 0.80   # 하한 합이 표 폭을 잠식하지 않도록 두는 천장(합 기준)
COL_FIT_TINY = 0.08        # 이 이하 하한(번호·No 같은 짧은 열)은 천장 비례 축소에서 뺀다
COL_FIT_SHORT_HU = 4800    # 가장 긴 셀이 이 폭(12pt 한글 4자) 이하인 라벨 열도 축소에서 뺀다 — '구 분'·'유지'처럼 짧은 말은
                           # 줄을 바꿀 자리가 없어 한 글자씩 쪼개진다('26.9.24 6열 표 실측: 하한 0.085가 5.9%로 눌려 '구/분')
COL_FIT_TOLERANCE = 0.001  # 사실상 항상 맞춘다 — 같은 글자면 같은 폭이 나와 멱등은 식이 보장한다. 종전 0.05는 kordoc 폭을
                           # 남겨 리뷰 화면(column_shares)과 최대 5%p 어긋났다('26.9.24 시험 변환 대조)


def _cell_width_hu(text):
    """12pt 표 셀에서 이 텍스트가 한 줄에 들어가는 데 필요한 폭(HWPUNIT)."""
    w = 0
    for ch in text:
        if ch == " ":
            w += COL_FIT_SPACE_HU
        elif ord(ch) < 128:
            w += COL_FIT_ASCII_HU
        else:
            w += COL_FIT_HANGUL_HU
    return w


def column_shares(rows_text, total):
    """열 폭 비중 — 열별 가장 긴 셀의 내용량에 비례하되, 열마다 가장 긴 셀이 한 줄에 들어갈 몫은 보장.

    rows_text는 행별 셀 글자 목록, total은 표 폭(HWPUNIT). 후처리 column_fit과 리뷰 HTML(render_review_html)이
    함께 쓴다 — 같은 식으로 나눠야 셀 줄바꿈·행 높이·쪽수가 두 화면에서 같다('26.9.24 시험 변환 대조).
    하한은 긴 서술 열이 독식하지 않게 열당 COL_FIT_FLOOR_MAX로 자른다(그 열은 비례에서 큰 몫을 받는다).
    """
    cols = max((len(r) for r in rows_text), default=0)
    if cols < 1 or not total:
        return None
    weights, floors = [0.0] * cols, []
    for r in rows_text:
        for i, t in enumerate(r):
            weights[i] = max(weights[i], _weighted_len(t))
    widths = []
    for i in range(cols):
        widest = max((_cell_width_hu(r[i].strip()) for r in rows_text if i < len(r)), default=0)
        widths.append(widest)
        floors.append(min((widest + COL_FIT_CELL_PAD) / total, COL_FIT_FLOOR_MAX))
    if sum(floors) > COL_FIT_FLOOR_CAP:
        # 하한 합이 넘치면 비례로 줄이되 짧은 열(`No`·번호처럼 하한 COL_FIT_TINY 이하, 또는 '구 분'처럼 가장 긴 셀이
        # COL_FIT_SHORT_HU 이하인 라벨 열)은 그대로 둔다 — 함께 줄이면 제 글자 폭보다 좁아져 `N`/`o`·`구`/`분`으로
        # 쪼개진다('26.9.24 붙임 대장 No 열 3%, 6열 표 라벨 열 5.9% 실측)
        tiny = [i for i, f in enumerate(floors) if f <= COL_FIT_TINY or widths[i] <= COL_FIT_SHORT_HU]
        rest = sum(f for i, f in enumerate(floors) if i not in tiny)
        room = COL_FIT_FLOOR_CAP - sum(floors[i] for i in tiny)
        if rest > 0 and room > 0:
            floors = [f if i in tiny else f * room / rest for i, f in enumerate(floors)]
    if sum(weights) <= 0:
        return None
    return _fit_shares(weights, floors)


def _fit_shares(weights, floors):
    """가중치에 비례해 열 폭 비중을 나누되 각 열에 최소 몫(floors)은 보장한다.

    floors는 머리글이 한 줄에 들어갈 실폭에서 나온 비중이다 — 정률 하한·상한을 쓰면
    내용 비례 배분과 정면으로 부딪힌다(상수 주석 참조). 하한에 걸린 열을 고정하고
    남은 몫만 나머지 열에 다시 비례 배분한다. 클램프 뒤 합으로 정규화하면 하한이
    그대로 되밀려 무력화되므로 그 방식은 쓰지 않는다('26.9.10 실측).
    """
    n = len(weights)
    total_floor = sum(floors)
    if total_floor > COL_FIT_FLOOR_CAP:          # 하한이 표를 다 먹으면 비례로 눌러 준다
        floors = [f * COL_FIT_FLOOR_CAP / total_floor for f in floors]
    shares = [w / sum(weights) for w in weights] if sum(weights) else [1.0 / n] * n
    pinned = [False] * n
    for _ in range(n + 1):
        free = [i for i in range(n) if not pinned[i]]
        budget = 1.0 - sum(shares[i] for i in range(n) if pinned[i])
        base = sum(weights[i] for i in free)
        for i in free:
            shares[i] = budget * (weights[i] / base if base else 1.0 / len(free))
        below = [i for i in free if shares[i] < floors[i]]
        if not below:
            break
        for i in below:
            shares[i] = floors[i]
            pinned[i] = True
    return shares


def apply_table_column_fit(section_roots):
    """본문 콘텐츠 표의 열 폭을 열별 내용량에 비례해 재배분한다(표 총 폭 불변).

    셀 병합이 없는 표만 대상이다(md-profile은 병합을 금지하므로 파이프라인 산출물은
    전부 해당한다). 제목 박스·붙임 배너는 제외한다 — 폭이 양식 실측값으로 고정돼 있다."""
    fitted = 0
    detail = []
    for tbl, is_title in _iter_content_tables(section_roots):
        if is_title or _is_banner_table(tbl):
            continue
        rows = tbl.findall(qn("hp", "tr"))
        if not rows:
            continue
        cols = int(tbl.get("colCnt") or 0)
        if cols < 2:
            continue
        spanned = any(
            (sp := tc.find(qn("hp", "cellSpan"))) is not None
            and (sp.get("colSpan") != "1" or sp.get("rowSpan") != "1")
            for tr in rows for tc in tr.findall(qn("hp", "tc"))
        )
        if spanned:
            continue
        widths = [None] * cols
        cells_by_col = [[] for _ in range(cols)]
        texts = []
        ok = True
        for tr in rows:
            tcs = tr.findall(qn("hp", "tc"))
            if len(tcs) != cols:
                ok = False
                break
            texts.append(["".join(t.text or "" for t in tc.iter(qn("hp", "t"))) for tc in tcs])
            for idx, tc in enumerate(tcs):
                sz = tc.find(qn("hp", "cellSz"))
                if sz is None:
                    ok = False
                    break
                cells_by_col[idx].append(sz)
                widths[idx] = int(sz.get("width"))
        if not ok or any(w is None for w in widths):
            continue
        total = sum(widths)
        shares = column_shares(texts, total)
        if shares is None:
            continue
        current = [w / total for w in widths]
        if max(abs(a - b) for a, b in zip(shares, current)) <= COL_FIT_TOLERANCE:
            continue
        new_widths = [int(total * sh) for sh in shares]
        new_widths[-1] = total - sum(new_widths[:-1])   # 합계 == 표 폭 정확 일치
        for idx, width in enumerate(new_widths):
            for sz in cells_by_col[idx]:
                sz.set("width", str(width))
        fitted += 1
        detail.append({"cols": cols, "before": widths, "after": new_widths})
    return {"tables_fitted": fitted, "detail": detail}


# 행 높이 — kordoc은 생성 때의 열 폭으로 행마다 필요한 줄 수를 계산해 칸 높이(cellSz height)를 적는다.
# 후처리가 열 폭을 바꾼 뒤(column_fit·fit_page_width)에도 그 높이가 남아, 넓어진 열의 행은 빈 줄만큼
# 높게 그려진다('26.9.24 시험 변환 실측: 표 3개에서 약 240pt — A4 본문 0.34쪽). 최종 폭으로 다시 계산한다.
# 한글은 칸 높이가 모자라면 내용만큼 늘려 그리므로(인도본 r02·시험본의 모자란 행이 잘리지 않음) 과대만 없애면 된다.
ROW_LINE_HU = 1600          # 표 12pt·줄간격 130% 한 줄(kordoc 산출 실측 — 1줄 행 1882, 줄마다 +1600)
ROW_PAD_HU = 282            # 1줄 행 = 줄 높이 + 상하 안여백(141×2)


def _cell_need_lines(header_root, tc, margin_lr):
    width = int(tc.find(qn("hp", "cellSz")).get("width")) - margin_lr
    lines = 0
    for par in tc.iter(qn("hp", "p")):
        text = "".join(t.text or "" for t in par.iter(qn("hp", "t"))).strip()
        run = par.find(qn("hp", "run"))
        size = _charpr_metrics(header_root, run.get("charPrIDRef"))[0] if run is not None else 12.0
        need = _cell_width_hu(text) * size / 12.0
        lines += max(1, math.ceil(need / max(width, 1)))
    return max(lines, 1)


def apply_row_fit(header_root, section_roots):
    """본문 표의 행 높이를 최종 열 폭 기준 필요 줄 수로 다시 적는다(표 전체 높이도 합으로 갱신).

    세로 병합 칸(rowSpan>1)은 행 높이를 정하지 않고 걸친 행 높이의 합을 받는다. 제목 박스·붙임 배너·
    산식 박스(1×1)는 양식 값이라 건드리지 않는다."""
    rows_changed = tables = 0
    for tbl, is_title in _iter_content_tables(section_roots):
        if is_title or _is_banner_table(tbl) or (tbl.get("rowCnt") == "1" and tbl.get("colCnt") == "1"):
            continue
        im = tbl.find(qn("hp", "inMargin"))
        tbl_lr = int(im.get("left", "510")) + int(im.get("right", "510")) if im is not None else 1020
        trs = tbl.findall(qn("hp", "tr"))
        heights, spans = [], []
        for ri, tr in enumerate(trs):
            need = 0
            for tc in tr.findall(qn("hp", "tc")):
                span = tc.find(qn("hp", "cellSpan"))
                rs = int(span.get("rowSpan", "1")) if span is not None else 1
                if rs > 1:
                    spans.append((ri, rs, tc))
                    continue
                cm = tc.find(qn("hp", "cellMargin"))
                lr = (int(cm.get("left", "0")) + int(cm.get("right", "0"))) if tc.get("hasMargin") == "1" and cm is not None else tbl_lr
                need = max(need, _cell_need_lines(header_root, tc, lr))
            old = max((int(tc.find(qn("hp", "cellSz")).get("height")) for tc in tr.findall(qn("hp", "tc"))), default=0)
            heights.append(ROW_PAD_HU + ROW_LINE_HU * need if need else old)
        changed = 0
        for ri, tr in enumerate(trs):
            for tc in tr.findall(qn("hp", "tc")):
                sz = tc.find(qn("hp", "cellSz"))
                if any(tc is s_tc for _, _, s_tc in spans):
                    continue
                if sz.get("height") != str(heights[ri]):
                    sz.set("height", str(heights[ri]))
                    changed = 1
            rows_changed += changed
            changed = 0
        for ri, rs, tc in spans:
            tc.find(qn("hp", "cellSz")).set("height", str(sum(heights[ri:ri + rs])))
        tsz = tbl.find(qn("hp", "sz"))
        if tsz is not None and tsz.get("height") != str(sum(heights)):
            tsz.set("height", str(sum(heights)))
            tables += 1
    return {"tables": tables, "rows_changed": rows_changed}


# ---------------------------------------------------------------------------
# 원문 인용 블록 — ```text 안의 프롬프트·지시문 원문을 회색 상자·고정폭으로('26.9.24 사용자 지시)
# ---------------------------------------------------------------------------
# kordoc은 인용 블록 줄을 평범한 문단(함초롬돋움 13pt)으로 낸다 — 그대로 두면 `- ` 줄이 대시로, `[ ]` 줄이
# 캡션으로 분류돼 서식이 입혀진다. to_kordoc_input이 붙인 표식(U+2060)으로 알아보고, 마지막에 표식을 지우며
# 문단 테두리·배경(연결)으로 한 상자처럼 묶는다 — 표로 감싸지 않아 줄마다 쪽을 넘길 수 있다.
QUOTE_MARK = "\u2060"
QUOTE_FACE = "굴림체"          # 고정폭 — 한글·윈도 기본 탑재
QUOTE_SIZE_PT = 10
QUOTE_LINE_SPACING = 130
QUOTE_FILL = "#F2F2F2"
QUOTE_BORDER = "#BFBFBF"
_QUOTE_PARAPRS = set()        # 이미 상자 서식을 입은 인용 줄의 paraPr — 재실행 때 표식 없이도 알아본다(멱등)


def refresh_quote_paraprs(header_root):
    """인용 상자 paraPr(회색 바탕 테두리를 연결로 쓰는 것)을 찾아 둔다 — process_file 시작 때."""
    fills = {bf.get("id") for bf in header_root.iter(qn("hh", "borderFill"))
             if (wb := bf.find(f".//{qn('hc', 'winBrush')}")) is not None and wb.get("faceColor", "").upper() == QUOTE_FILL
             and (lb := bf.find(qn("hh", "leftBorder"))) is not None and lb.get("color", "").upper() == QUOTE_BORDER}
    _QUOTE_PARAPRS.clear()
    for pp in header_root.iter(qn("hh", "paraPr")):
        b = pp.find(qn("hh", "border"))
        if b is not None and b.get("connect") == "1" and b.get("borderFillIDRef") in fills:
            _QUOTE_PARAPRS.add(pp.get("id"))


def _ensure_font_face(header_root, face):
    """모든 lang 글꼴 목록에 face를 같은 번호로 더한다(이미 있으면 그 번호)."""
    fonts = _hangul_fontfaces(header_root)
    fid = next((k for k, v in fonts.items() if v == face), None)
    if fid is not None:
        return fid
    new_id = None
    for ff in header_root.iter(qn("hh", "fontface")):
        n = len(ff.findall(qn("hh", "font")))
        new_id = new_id if new_id is not None else str(n)
        ET.SubElement(ff, qn("hh", "font"), {"id": str(n), "face": face, "type": "TTF", "isEmbedded": "0"})
        ff.set("fontCnt", str(n + 1))
    return new_id


def _quote_border_fill(header_root, cache):
    key = ("quote-bf",)
    if key in cache:
        return cache[key]
    bfs = header_root.find(f".//{qn('hh', 'borderFills')}")
    new_id = str(max(int(bf.get("id")) for bf in bfs.findall(qn("hh", "borderFill"))) + 1)
    side = f'type="SOLID" width="0.12 mm" color="{QUOTE_BORDER}"'
    bfs.append(ET.fromstring(
        f'<hh:borderFill xmlns:hh="{NS["hh"]}" xmlns:hc="{NS["hc"]}" id="{new_id}" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
        f'<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
        f'<hh:leftBorder {side}/><hh:rightBorder {side}/><hh:topBorder {side}/><hh:bottomBorder {side}/>'
        f'<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>'
        f'<hc:fillBrush><hc:winBrush faceColor="{QUOTE_FILL}" hatchColor="#000000" alpha="0"/></hc:fillBrush></hh:borderFill>'))
    bfs.set("itemCnt", str(len(bfs.findall(qn("hh", "borderFill")))))
    cache[key] = new_id
    return new_id


def _quote_parapr(header_root, base_id, fill_id, cache):
    key = ("quote-pp", base_id)
    if key in cache:
        return cache[key]
    paraprops = header_root.find(f".//{qn('hh', 'paraProperties')}")
    base = next((pp for pp in paraprops.findall(qn("hh", "paraPr")) if pp.get("id") == base_id), None)
    if base is None:
        cache[key] = base_id
        return base_id
    new_pp = copy.deepcopy(base)
    new_pp.set("id", str(max(int(pp.get("id")) for pp in paraprops.findall(qn("hh", "paraPr"))) + 1))
    for al in new_pp.iter(qn("hh", "align")):
        al.set("horizontal", "LEFT")
    for mg in new_pp.iter(qn("hh", "margin")):
        for tag in ("intent", "left", "right", "prev", "next"):
            el = mg.find(qn("hc", tag))
            if el is not None:
                el.set("value", "0")
    for ls in new_pp.iter(qn("hh", "lineSpacing")):
        ls.set("type", "PERCENT")
        ls.set("value", str(QUOTE_LINE_SPACING))
    for bs in new_pp.iter(qn("hh", "breakSetting")):
        bs.set("breakNonLatinWord", "BREAK_WORD")
        bs.set("breakLatinWord", "BREAK_WORD")
    border = new_pp.find(qn("hh", "border"))
    if border is None:
        border = ET.SubElement(new_pp, qn("hh", "border"))
    border.attrib.update({"borderFillIDRef": fill_id, "offsetLeft": "567", "offsetRight": "567",
                          "offsetTop": "283", "offsetBottom": "283", "connect": "1", "ignoreMargin": "0"})
    paraprops.append(new_pp)
    paraprops.set("itemCnt", str(len(paraprops.findall(qn("hh", "paraPr")))))
    cache[key] = new_pp.get("id")
    _QUOTE_PARAPRS.add(cache[key])
    return cache[key]


def apply_quote_block(header_root, section_roots):
    """원문 인용 줄 — 표식을 지우고 고정폭 10pt·줄간격 130%·왼쪽 정렬, 회색 바탕 테두리 상자(문단 연결)로.

    다른 모든 단계가 표식으로 인용 줄을 건너뛴 뒤 마지막에 돈다 — 먼저 지우면 빈 인용 줄이 '빈 문단'으로
    보여 간격 단계가 스페이서로 바꿔 버린다."""
    cache, lines, changed = {}, 0, 0
    fid = None
    for sec_root in section_roots:
        for p in sec_root.iter(qn("hp", "p")):
            if classify(p) != "quote":
                continue
            if fid is None:
                fid = _ensure_font_face(header_root, QUOTE_FACE)
            lines += 1
            if QUOTE_MARK in para_text(p):
                changed += 1
            for t in p.iter(qn("hp", "t")):
                if t.text and QUOTE_MARK in t.text:
                    t.text = t.text.replace(QUOTE_MARK, "")
            if p.get("paraPrIDRef") not in _QUOTE_PARAPRS:
                p.set("paraPrIDRef", _quote_parapr(header_root, p.get("paraPrIDRef", "0"),
                                                   _quote_border_fill(header_root, cache), cache))
            for run in p.findall(qn("hp", "run")):
                cid = run.get("charPrIDRef")
                if cid is not None:
                    run.set("charPrIDRef", ensure_charpr_font_size(header_root, cid, QUOTE_FACE, QUOTE_SIZE_PT * 100, cache))
    return {"lines": lines, "changed": changed, "face": QUOTE_FACE if lines else None}


# ---------------------------------------------------------------------------
# 표 병합 — 2단 머리행(`A > B`)·세로 병합(`〃`)·라벨 열 음영 (경영관리 프레임워크 틀, '26.9.24)
# ---------------------------------------------------------------------------

# GFM은 병합·2단 머리행을 못 그려 기관 양식의 성과지표 실적표(성과지표 · '23년 목표/실적 · 추진실적)·
# 연도별 목표표를 재현하지 못했다. 마크다운에는 표기만 남기고 여기서 hwpx 표 구조를 고친다 — 결과는
# 한글에서 편집 가능한 진짜 병합 표다(이미지 아님).
HEADER_SPLIT = " > "       # 머리글 `'23년 > 목표` — 위 칸 '23년(가로 병합) · 아래 칸 목표
DITTO = "〃"               # 본문 칸 `〃` — 바로 위 칸과 세로 병합(위와 같음)
LABEL_FILL = "#D8D8D8"     # 라벨 칸 음영 — 경영관리 프레임워크 hwpx 5종 실측 최빈값(구분·추진방향·환경분석·시사점)


def _cell_text(tc):
    return "".join(t.text or "" for t in tc.iter(qn("hp", "t")))


def _set_cell_text(tc, text):
    ts = list(tc.iter(qn("hp", "t")))
    if not ts:
        return
    ts[0].text = text
    for t in ts[1:]:
        t.text = ""
    for par in tc.iter(qn("hp", "p")):          # 글자가 바뀌면 줄 배치 캐시는 무효 — 한글이 다시 계산한다
        lsa = par.find(qn("hp", "linesegarray"))
        if lsa is not None:
            par.remove(lsa)


def _span(tc):
    sp = tc.find(qn("hp", "cellSpan"))
    return int(sp.get("colSpan", "1")), int(sp.get("rowSpan", "1"))


def ensure_fill_variant(header_root, base_id, color, cache):
    """base_id borderFill의 테두리는 그대로 두고 채움만 color로 바꾼 복제본 id."""
    key = ("fill", base_id, color)
    if key in cache:
        return cache[key]
    bfs = header_root.find(f".//{qn('hh', 'borderFills')}")
    base = next((bf for bf in bfs.findall(qn("hh", "borderFill")) if bf.get("id") == base_id), None)
    if base is None:
        cache[key] = base_id
        return base_id
    new_bf = copy.deepcopy(base)
    new_bf.set("id", str(max(int(bf.get("id")) for bf in bfs.findall(qn("hh", "borderFill"))) + 1))
    old = new_bf.find(qn("hc", "fillBrush"))
    if old is not None:
        new_bf.remove(old)
    new_bf.append(ET.fromstring(f'<hc:fillBrush xmlns:hc="{NS["hc"]}"><hc:winBrush faceColor="{color}" '
                                f'hatchColor="#000000" alpha="0"/></hc:fillBrush>'))
    bfs.append(new_bf)
    bfs.set("itemCnt", str(len(bfs.findall(qn("hh", "borderFill")))))
    cache[key] = new_bf.get("id")
    return cache[key]


def _two_level_header(tbl):
    """첫 행 머리글에 `A > B`가 있으면 위에 한 행을 더해 A를 가로 병합하고, `>`가 없는 머리글은
    두 행을 세로로 차지하게 한다. 반환: 바꿨으면 True."""
    rows = tbl.findall(qn("hp", "tr"))
    if len(rows) < 2:
        return False
    head = rows[0].findall(qn("hp", "tc"))
    parts = [_cell_text(tc).split(HEADER_SPLIT, 1) for tc in head]
    if not any(len(x) == 2 for x in parts) or any(_span(tc) != (1, 1) for tc in head):
        return False
    top_tr = ET.Element(qn("hp", "tr"))
    subs, i = [], 0
    h = int(head[0].find(qn("hp", "cellSz")).get("height", "0"))
    while i < len(head):
        if len(parts[i]) == 1:                  # 단일 머리글 — 두 행을 세로로 차지
            tc = head[i]
            tc.find(qn("hp", "cellSpan")).set("rowSpan", "2")
            sz = tc.find(qn("hp", "cellSz"))
            sz.set("height", str(int(sz.get("height", "0")) * 2))
            top_tr.append(tc)
            i += 1
            continue
        top, j = parts[i][0].strip(), i
        while j < len(head) and len(parts[j]) == 2 and parts[j][0].strip() == top:
            j += 1
        group = head[i:j]
        g = copy.deepcopy(group[0])
        _set_cell_text(g, top)
        g.find(qn("hp", "cellSpan")).set("colSpan", str(len(group)))
        g.find(qn("hp", "cellSz")).set("width", str(sum(int(x.find(qn("hp", "cellSz")).get("width")) for x in group)))
        top_tr.append(g)
        for tc, pr in zip(group, parts[i:j]):
            _set_cell_text(tc, pr[1].strip())
            subs.append(tc)
        i = j
    old = rows[0]
    for tc in list(old.findall(qn("hp", "tc"))):
        old.remove(tc)
    for tc in subs:
        old.append(tc)
    tbl.insert(list(tbl).index(old), top_tr)
    for r, tr in enumerate(tbl.findall(qn("hp", "tr"))):
        for tc in tr.findall(qn("hp", "tc")):
            tc.find(qn("hp", "cellAddr")).set("rowAddr", str(r))
    tbl.set("rowCnt", str(len(tbl.findall(qn("hp", "tr")))))
    sz = tbl.find(qn("hp", "sz"))
    if sz is not None:
        sz.set("height", str(int(sz.get("height", "0")) + h))
    return True


def _ditto_merge(tbl):
    """본문 칸이 `〃`면 바로 위 칸(같은 열·같은 폭)을 한 행 늘려 덮는다. 반환: 병합한 칸 수."""
    rows = tbl.findall(qn("hp", "tr"))
    last = len(rows) - 1
    grid, merged = {}, 0
    for tr in rows:
        for tc in list(tr.findall(qn("hp", "tc"))):
            addr = tc.find(qn("hp", "cellAddr"))
            c, r = int(addr.get("colAddr")), int(addr.get("rowAddr"))
            cs, rs = _span(tc)
            above = grid.get((r - 1, c))
            if (_cell_text(tc).strip() == DITTO and tc.get("header") != "1" and above is not None
                    and int(above.find(qn("hp", "cellAddr")).get("colAddr")) == c and _span(above)[0] == cs):
                asp = above.find(qn("hp", "cellSpan"))
                asp.set("rowSpan", str(_span(above)[1] + rs))
                asz = above.find(qn("hp", "cellSz"))
                asz.set("height", str(int(asz.get("height")) + int(tc.find(qn("hp", "cellSz")).get("height"))))
                if r + rs - 1 >= last:          # 표 맨 아래 칸을 덮으면 아래 선 서식을 물려받는다
                    above.set("borderFillIDRef", tc.get("borderFillIDRef"))
                tr.remove(tc)
                merged += 1
                owner = above
            else:
                owner = tc
            for k in range(cs):
                for m in range(rs):
                    grid[(r + m, c + k)] = owner
    return merged


def _label_column(header_root, tbl, cache):
    """첫 열 본문 칸이 모두 굵은 글씨면 라벨 열로 보고 연회색 음영·가운데 정렬을 준다."""
    bold = {cp.get("id") for cp in header_root.iter(qn("hh", "charPr")) if cp.find(qn("hh", "bold")) is not None}
    firsts = [tc for tr in tbl.findall(qn("hp", "tr")) for tc in tr.findall(qn("hp", "tc"))
              if tc.get("header") != "1" and tc.find(qn("hp", "cellAddr")).get("colAddr") == "0"]
    if not firsts or int(tbl.get("colCnt") or 0) < 2:
        return False

    def all_bold(tc):
        runs = [run for run in tc.iter(qn("hp", "run")) if "".join(t.text or "" for t in run.iter(qn("hp", "t"))).strip()]
        return bool(runs) and all(run.get("charPrIDRef") in bold for run in runs)
    if not all(all_bold(tc) for tc in firsts):
        return False
    for tc in firsts:
        tc.set("borderFillIDRef", ensure_fill_variant(header_root, tc.get("borderFillIDRef"), LABEL_FILL, cache))
        for par in tc.iter(qn("hp", "p")):
            par.set("paraPrIDRef", ensure_aligned_clone(header_root, par.get("paraPrIDRef", "0"), "CENTER", cache))
    return True


def apply_table_merge(header_root, section_roots):
    """본문 표에 2단 머리행·세로 병합·라벨 열 음영을 적용한다 — 열 폭 맞춤(병합 표는 건너뜀) 다음에 돈다."""
    cache = {}
    two = ditto = label = 0
    for tbl, is_title in _iter_content_tables(section_roots):
        if is_title or _is_banner_table(tbl) or (tbl.get("rowCnt") == "1" and tbl.get("colCnt") == "1"):
            continue
        two += _two_level_header(tbl)
        ditto += _ditto_merge(tbl)
        label += _label_column(header_root, tbl, cache)
    return {"two_level_headers": two, "ditto_merged": ditto, "label_columns": label}


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
            if sz is None or is_figure_table(tbl):   # 도식 표는 diagram_table이 본문 폭 상한으로 만든다(R089)
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
                _refresh_pic_cache(pic)
                pics += 1
            adjusted.append({"before_mm": round(total / 7200 * 25.4, 1),
                             "after_mm": round((target + om_l + om_r) / 7200 * 25.4, 1),
                             "ratio": round(ratio, 4), "pics_scaled": pics})
    return {"tables_fitted": len(adjusted), "detail": adjusted}


def _refresh_pic_cache(pic):
    """그림 크기를 바꾼 뒤 파생 캐시를 다시 계산한다 (R042 위생).

    scaMatrix e1/e5 = curSz/orgSz, rotationInfo center = curSz/2 — sz·curSz만 바꾸면 원값이
    스테일로 남는다. transMatrix·scaMatrix의 e3/e6은 offset 파생이라(offset 불변) 건드리지 않는다.
    """
    org = pic.find(qn("hp", "orgSz"))
    cur = pic.find(qn("hp", "curSz"))
    if org is None or cur is None:
        return
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


# ---------------------------------------------------------------------------
# 본문 그림 — 픽셀은 원본대로, 표시 크기·배치만 정한다 (R088)
# ---------------------------------------------------------------------------

# kordoc은 그림 크기를 1px = 75 HU(96dpi)로 잡고 170mm를 넘는 폭만 줄인다. 그래서 1/3쪽 규격에
# 맞추려고 픽셀을 줄여 넣으면 인쇄 해상도가 96dpi로 떨어져 글자가 뭉개진다('26.8.24 1814건 인도본 —
# 1257px 원본을 556px로 줄여 147×90mm, 실효 96dpi, 그림 문단은 양쪽 정렬·줄간격 160%).
FIGURE_DEFAULT_DPI = 96    # 해상도 정보가 없는 그림의 가정값 — kordoc 환산(1px = 75 HU)과 같다
FIGURE_MAX_H_MM = 90       # 1/3쪽 높이 상한 (R006)
FIGURE_MIN_DPI = 150       # 표시 크기 기준 실효 해상도 하한 — 미만이면 인쇄 시 뭉개진다
FIGURE_CAPTION_FACE = "맑은 고딕"   # 그림 캡션 = 표 캡션 서식(R023·R034 — 표 서체 12pt 볼드, 가운데)
HU_PER_MM = 7200 / 25.4


def image_pixels(blob):
    """(폭 px, 높이 px, dpi 또는 None) — PNG·JPEG·GIF·BMP 머리만 읽는다(kordoc 삽입 허용 형식).

    dpi는 PNG pHYs·JPEG JFIF·BMP 해상도 칸에서 읽고, 없으면 None(호출자가 96dpi로 가정)."""
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        if len(blob) < 24:
            raise ValueError("truncated png")
        w, h = struct.unpack(">II", blob[16:24])
        dpi, i = None, 8
        while i + 8 <= len(blob):
            n, tag = struct.unpack(">I4s", blob[i:i + 8])
            if tag == b"pHYs" and n >= 9 and i + 17 <= len(blob):
                ppx, _ppy, unit = struct.unpack(">IIB", blob[i + 8:i + 17])
                if unit == 1 and ppx:
                    dpi = ppx * 0.0254
                break
            if tag in (b"IDAT", b"IEND"):
                break
            i += 12 + n
        return w, h, dpi
    if blob[:2] == b"\xff\xd8":
        i, dpi = 2, None
        while i + 4 <= len(blob):
            if blob[i] != 0xFF:
                i += 1
                continue
            marker = blob[i + 1]
            if marker == 0xFF:                     # 채움 바이트
                i += 1
                continue
            if marker == 0x01 or 0xD0 <= marker <= 0xD8:
                i += 2
                continue
            n = struct.unpack(">H", blob[i + 2:i + 4])[0]
            seg = blob[i + 4:i + 2 + n]
            if marker == 0xE0 and seg[:5] == b"JFIF\x00" and len(seg) >= 12:
                unit, xd = seg[7], struct.unpack(">H", seg[8:10])[0]
                if xd and unit in (1, 2):
                    dpi = xd if unit == 1 else xd * 2.54
            elif 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC) and len(seg) >= 5:
                h, w = struct.unpack(">HH", seg[1:5])
                return w, h, dpi
            elif marker == 0xDA:
                break
            i += 2 + n
        raise ValueError("no SOF")
    if blob[:4] == b"GIF8" and len(blob) >= 10:
        w, h = struct.unpack("<HH", blob[6:10])
        return w, h, None
    if blob[:2] == b"BM" and len(blob) >= 42:
        w, h = struct.unpack("<ii", blob[18:26])
        ppm = struct.unpack("<i", blob[38:42])[0]
        return w, abs(h), (ppm * 0.0254 if ppm > 0 else None)
    raise ValueError("unsupported format")


def figure_display(w_px, h_px, dpi, max_w_mm, max_h_mm=FIGURE_MAX_H_MM):
    """그림 표시 크기 — 원본 해상도로 잰 물리 크기를 상자(max_w×max_h)에 비율 유지로 넣는다.

    줄이기만 하고 키우지 않는다(작은 그림을 늘리면 뭉개짐이 커진다). 픽셀은 건드리지 않는다.
    실효 해상도 = 픽셀 폭 ÷ 표시 폭(인치) — FIGURE_MIN_DPI 미만이면 sharp=False."""
    dpi = dpi or FIGURE_DEFAULT_DPI
    w_mm, h_mm = w_px / dpi * 25.4, h_px / dpi * 25.4
    scale = min(1.0, max_w_mm / w_mm, max_h_mm / h_mm)
    w_mm, h_mm = w_mm * scale, h_mm * scale
    eff = w_px / (w_mm / 25.4)
    return {"w_mm": round(w_mm, 1), "h_mm": round(h_mm, 1),
            "w_hu": int(round(w_mm * HU_PER_MM)), "h_hu": int(round(h_mm * HU_PER_MM)),
            "effective_dpi": int(round(eff)), "sharp": eff >= FIGURE_MIN_DPI}


def _bin_hrefs(data):
    """content.hpf manifest의 {item id: 패키지 경로} — hc:img binaryItemIDRef를 BinData 파일로 푼다."""
    hpf = data.get("Contents/content.hpf", b"").decode("utf-8", "ignore")
    out = {}
    for tag in re.findall(r"<opf:item\b[^>]*>", hpf):
        attrs = dict(re.findall(r'([\w:-]+)="([^"]*)"', tag))
        if "id" in attrs and "href" in attrs:
            out[attrs["id"]] = attrs["href"]
    return out


def apply_figure_fit(header_root, section_roots, data):
    """본문 그림 문단: 표시 크기를 원본 해상도 기준으로 다시 쓰고 가운데 정렬·줄간격 100%로 둔다.

    대상은 섹션 최상위 문단 가운데 글자 없이 그림만 든 것(kordoc `![캡션](파일)` 산출형) — 표 셀·
    머리말 안 그림은 R042 `apply_fit_page_width` 소관이다. 한 문단에 그림이 여럿이면 폭을 나눈다.
    줄간격 100%는 R041 실측 근거 — 글자처럼 취급한 개체의 줄 높이는 줄간격 %만큼 부풀어
    그림 아래에 높이의 60%(160% 기준)가 빈 줄로 남는다.
    """
    hrefs = _bin_hrefs(data)
    cache, char_cache, bold_cache = {}, {}, {}
    detail, missing, captions = [], [], 0
    for sec_root in section_roots:
        limit_mm = (_text_width_pt(sec_root) * 100 - FIT_PAGE_SLACK) / HU_PER_MM
        paras = sec_root.findall(qn("hp", "p"))
        for idx, p in enumerate(paras):
            if classify(p) != "figure":
                continue
            # 바로 위 캡션(`[ 제목 ]`, 빈 줄 건너뜀)은 표 캡션과 같은 서식으로 — 표에 내장되지
            # 않은 캡션은 본문 명조로 남아 표 캡션과 어긋났다('26.9.24 렌더 확인)
            for q in reversed(paras[:idx]):
                kind = classify(q)
                if kind == "empty":
                    continue
                if kind == "caption":
                    # 가운데 정렬 + 다음 문단과 함께 — 캡션만 쪽 끝에 남고 그림이 다음 쪽으로 넘어갔다
                    # ('26.9.24 렌더 확인, 표 캡션은 표 안에 내장돼 이 문제가 없다)
                    centered = ensure_aligned_clone(header_root, q.get("paraPrIDRef", "0"), "CENTER", cache)
                    q.set("paraPrIDRef", ensure_keepnext_parapr(header_root, centered, cache))
                    for run in q.findall(qn("hp", "run")):
                        cid = run.get("charPrIDRef")
                        if cid is not None:
                            cid = ensure_charpr_font_size(header_root, cid, FIGURE_CAPTION_FACE, 1200, char_cache)
                            run.set("charPrIDRef", ensure_charpr_bold(header_root, cid, bold_cache))
                    captions += 1
                break
            pics = [pic for run in p.findall(qn("hp", "run")) for pic in run.findall(qn("hp", "pic"))]
            for pic in pics:
                img = pic.find(qn("hc", "img"))
                ref = img.get("binaryItemIDRef") if img is not None else None
                blob = data.get(hrefs.get(ref, ""))
                if blob is None:
                    missing.append(ref)
                    continue
                try:
                    w_px, h_px, dpi = image_pixels(blob)
                except (ValueError, struct.error):
                    missing.append(ref)
                    continue
                d = figure_display(w_px, h_px, dpi, limit_mm / len(pics))
                for tag in ("curSz", "sz"):
                    el = pic.find(qn("hp", tag))
                    if el is not None:
                        el.set("width", str(d["w_hu"]))
                        el.set("height", str(d["h_hu"]))
                _refresh_pic_cache(pic)
                detail.append({"id": ref, "px": [w_px, h_px],
                               "src_dpi": round(dpi) if dpi else None, "mm": [d["w_mm"], d["h_mm"]],
                               "effective_dpi": d["effective_dpi"], "sharp": d["sharp"]})
            centered = ensure_aligned_clone(header_root, p.get("paraPrIDRef", "0"), "CENTER", cache)
            p.set("paraPrIDRef", ensure_linespacing_parapr(header_root, centered, 100, cache))
    return {"figures": len(detail), "low_res": sum(1 for x in detail if not x["sharp"]),
            "captions_styled": captions, "unreadable": missing, "detail": detail}


# 발신 줄 크기 실측값(R018, format-profile.kca.md §서체) — --all이 이 값을 기본 적용한다.
# 종전에는 호출자가 --sender-size 12를 매번 손으로 넘겨야 해 9곳 문서에 값이 복제됐고,
# 빠뜨리면 규칙 위반본이 그대로 나갔다.
# 계층별 확정 글자 크기 (format-profile.kca.md §2 — R008 값의 후처리 방어선).
# kordoc generate_document가 sizes 인자(dae·bodyTitle)를 무시하고 preset 기본값으로
# □ 17pt·대시 14pt·제목 23~25pt를 산출하는 것을 '26.9.8 실측 확인했다 — 생성기 기본값에
# 양식 정합을 맡기지 않고 여기서 결정론으로 되돌린다. 표 셀은 대상이 아니다(R023 12pt는
# apply_caption_table_font 소관).
FORM_SIZES_PT = {"dae": 15, "yo": 15, "dash": 15, "arrow": 15, "star": 13, "cham": 13}
TITLE_BOX_SIZE_PT = 24   # '26.9.24 사용자 확정 — 양식 명시값 20pt에서 올림(모든 보고서). 한 줄 맞춤은 fit_title
TITLE_TEXT_WIDTH_HU = 47061   # 제목 행 글자 폭 — kordoc 제목 박스 47341 − 셀 여백 140×2(시험 변환 실측)
# 본문 계층 안에서 의도적으로 작게 남겨 둔 높이 — 괄호 13pt(R033·R039)가 유일하다.
# 이 패스를 재실행해도 앞선 apply_paren_small의 결과를 되돌리지 않도록 건너뛴다(멱등).
FORM_SIZES_KEEP = (1300,)


def _charpr_heights(header_root):
    """{charPr id: height} — 문단마다 전역 탐색하면 charPr이 늘수록 제곱으로 느려진다
    (apply_paren_small이 이미 쓰는 방식)."""
    out = {}
    for cp in header_root.iter(qn("hh", "charPr")):
        try:
            out[cp.get("id")] = int(cp.get("height"))
        except (TypeError, ValueError):
            out[cp.get("id")] = None
    return out


def apply_form_sizes(header_root, section_roots):
    """계층 문단·제목 박스 run의 글자 크기를 양식 확정값으로 되돌린다(폰트·볼드 유지)."""
    p_tag = qn("hp", "p")
    cache = {}
    counts = {}
    changed = 0
    heights = _charpr_heights(header_root)
    for sec_root in section_roots:
        for child in sec_root:
            if child.tag != p_tag:
                continue
            kind = classify(child)
            pt = FORM_SIZES_PT.get(kind)
            if pt is None:
                continue
            counts[kind] = counts.get(kind, 0) + 1
            for run in child.findall(qn("hp", "run")):
                base_id = run.get("charPrIDRef")
                if base_id is None:
                    continue
                if heights.get(base_id) in FORM_SIZES_KEEP:
                    continue
                new_id = ensure_charpr_sized(header_root, base_id, pt * 100, cache)
                if new_id != base_id:
                    run.set("charPrIDRef", new_id)
                    changed += 1
    title_changed = 0
    title_tbl = _title_box(header_root, section_roots)
    title_rows = title_tbl.findall(qn("hp", "tr")) if title_tbl is not None else []
    title_idx = _title_row_index(title_rows)
    if title_idx is not None:
        # 제목 행만 대상 — 밴드 행의 빈 1pt run(행 높이 3.8pt)과 부가 행(담당자 행)은
        # 제목 크기로 부풀리면 안 된다
        for run in title_rows[title_idx].iter(qn("hp", "run")):
            t = run.find(qn("hp", "t"))
            if t is None or not (t.text or "").strip():
                continue
            base_id = run.get("charPrIDRef")
            if base_id is None:
                continue
            new_id = ensure_charpr_sized(header_root, base_id,
                                         TITLE_BOX_SIZE_PT * 100, cache)
            if new_id != base_id:
                run.set("charPrIDRef", new_id)
                title_changed += 1
    return {"paragraphs": counts, "runs_changed": changed,
            "title_runs_changed": title_changed, "title_pt": TITLE_BOX_SIZE_PT}


def apply_title_fit(header_root, section_roots):
    """제목 한 줄 맞춤 — 제목 박스 폭이 다 정해진 **뒤**(본문 폭 맞춤 fit_page_width 다음) 돈다. 그 앞에서는
    kordoc 원래 폭 48757로 재서 덜 조였고 재실행마다 값이 달랐다('26.9.24 시험 변환). kordoc이 생성 크기(25pt)로 조여 둔 장평·자간(87·-5)은 버리고
    새 크기에서 100·0부터 다시 맞춘다. 하한까지 조여도 넘치면 두 줄로 둔다(overflow)."""
    title_tbl = _title_box(header_root, section_roots)
    rows = title_tbl.findall(qn("hp", "tr")) if title_tbl is not None else []
    idx = _title_row_index(rows)
    if idx is None:
        return {"found": False, "ratio": None, "spacing": None, "overflow": False, "runs_changed": 0}
    runs = [r for r in rows[idx].iter(qn("hp", "run"))
            if r.find(qn("hp", "t")) is not None and (r.find(qn("hp", "t")).text or "").strip()]
    text = "".join(r.find(qn("hp", "t")).text or "" for r in runs)
    cell = rows[idx].find(qn("hp", "tc"))
    sz = cell.find(qn("hp", "cellSz")) if cell is not None else None
    width = int(sz.get("width")) - 280 if sz is not None and sz.get("width") else TITLE_TEXT_WIDTH_HU
    ratio, spacing, overflow = fit_title(text, width / 100.0)
    cache, changed = {}, 0
    for run in runs:
        cid = run.get("charPrIDRef")
        if _charpr_metrics(header_root, cid)[1:] != (ratio, spacing):
            run.set("charPrIDRef", ensure_charpr_fitted(header_root, cid, ratio, spacing, cache))
            changed += 1
    return {"found": True, "ratio": ratio, "spacing": spacing, "overflow": overflow, "runs_changed": changed}


def fit_title(text, avail_pt, size_pt=None):
    """제목 한 줄 맞춤 — (장평, 자간, 넘침). 리뷰 HTML도 같은 값으로 그린다."""
    size = size_pt or TITLE_BOX_SIZE_PT
    chosen = fit_line(_weighted_len(text), avail_pt, size, 100, 0, max_lines=1, words=word_lens(text))
    if chosen is None:
        return MIN_RATIO, MIN_SPACING, True
    return chosen[0], chosen[1], False


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
                 "figure", "other"}


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


# ---- process_file 스테이지 테이블 ------------------------------------------
# 항목: (요약 키, 게이트, 실행, 대상 발견 판정, 변경 판정). 나열 순서가 곧 실행 순서다.
# 순서 제약(어기면 결과가 달라진다):
#   · caption_embed → spacing (R034: 캡션 문단이 hp:caption으로 사라지면
#     X→caption·caption→table 전환이 X→table 전환으로 바뀐다)
#   · zero 게이트 그룹은 spacing 뒤 (R014: 콘텐츠 paraPr 여백 0화로 스페이서 단독 체계 유지)
#   · title_box_form → title_box → title_box_topgap (R084: 원형 복원이 4변 NONE을 만든 뒤
#     borderless가 무동작이 되고, topgap은 복원된 표의 앵커를 본다)
#   · column_fit → layout (열 폭이 행 높이를 결정하므로 재배분 전 수치로 쪽수를 재면 안 된다)
#   · always 게이트 5종은 플래그 무관 상시 적용 — **양식이 요구하는 불변식만** 둔다
#     (R036·R042 표 폭 정합·R043 패키지 정합). 내용 기반 재조판인 column_fit은 zero
#     게이트다: --star-footnote 하나로 본문 표 열 폭이 통째로 바뀌면 안 된다
# 판정이 None이면 그 축(found/changed)에 세지 않는다 — effective_gaps·layout은 보고 전용.
_never = None


def _banner_effect(r):
    geo = r.get("geometry") or {}
    return bool(r.get("injected") or geo.get("linespacing_fixed") or geo.get("textwidth_fixed"))


STAGES = (
    ("star_footnote", "star",
     lambda c: apply_star_footnote(c["header"], c["secs"]),
     lambda r: r["stars_found"] > 0, lambda r: r["runs_changed"] > 0),
    ("caption_embed", "spacing",
     lambda c: apply_caption_embed(c["header"], c["secs"]),
     lambda r: r["embedded"] > 0, lambda r: r["embedded"] > 0),
    ("form_sizes", "spacing",
     lambda c: apply_form_sizes(c["header"], c["secs"]),
     lambda r: bool(r["paragraphs"]),
     lambda r: bool(r["runs_changed"] or r["title_runs_changed"])),
    ("spacing", "spacing",
     lambda c: {k: v for k, v in apply_spacing(c["header"], c["secs"]).items()
                if k in ("inserted", "modified", "events")},
     lambda r: bool(r["events"]), lambda r: bool(r["events"])),
    ("zero_margins", "zero",
     lambda c: apply_zero_margins(c["header"], c["secs"]),
     lambda r: r["count"] > 0, lambda r: r["count"] > 0),
    ("effective_gaps", "zero",
     lambda c: effective_gaps(c["header"], c["secs"]), _never, _never),
    ("table_alignment", "zero",
     lambda c: apply_table_alignment(c["header"], c["secs"]),
     lambda r: any(r["aligned"].values()), lambda r: any(r["aligned"].values())),
    ("space_hierarchy", "zero",
     lambda c: apply_space_hierarchy(c["header"], c["secs"]),
     lambda r: bool(r["prefixed"] or r["flattened"]),
     lambda r: bool(r["prefixed"] or r["flattened"])),
    ("body_justify", "zero",
     lambda c: apply_body_justify(c["header"], c["secs"]),
     lambda r: r["found"] > 0, lambda r: r["changed"] > 0),
    ("highlight", "zero",
     lambda c: apply_highlight(c["header"], c["secs"]),
     lambda r: r["highlights"] > 0, lambda r: r["highlights"] > 0),
    ("paren_small", "zero",
     lambda c: apply_paren_small(c["header"], c["secs"]),
     lambda r: r["paren_spans"] > 0, lambda r: r["paren_spans"] > 0),
    ("superscript_star", "zero",
     lambda c: apply_superscript_star(c["header"], c["secs"]),
     lambda r: r["stars_superscripted"] > 0, lambda r: r["stars_superscripted"] > 0),
    ("page_margins", "zero",
     lambda c: apply_page_margins(c["secs"]),
     lambda r: bool(r["attrs_changed"]), lambda r: bool(r["attrs_changed"])),
    ("figure_fit", "zero",
     lambda c: apply_figure_fit(c["header"], c["secs"], c["data"]),
     lambda r: r["figures"] > 0, lambda r: r["figures"] > 0),
    ("center_cells", "zero",
     lambda c: apply_center_cell_text(c["header"], c["secs"]),
     lambda r: r["tables"] > 0, lambda r: r["paragraphs"] > 0),
    ("title_box_form", "zero",
     lambda c: apply_title_box_form(c["header"], c["secs"]),
     lambda r: bool(r["restored"]), lambda r: bool(r["restored"])),
    ("title_box", "zero",
     lambda c: apply_title_box_borderless(c["header"], c["secs"]),
     lambda r: bool(r["found"]), lambda r: r["fills_replaced"] > 0),
    ("title_box_topgap", "zero",
     lambda c: apply_title_box_topgap(c["header"], c["secs"]),
     lambda r: bool(r["anchors_fixed"] or r["outmargins_fixed"]),
     lambda r: bool(r["anchors_fixed"] or r["outmargins_fixed"])),
    ("caption_table_font", "zero",
     lambda c: apply_caption_table_font(c["header"], c["secs"]),
     lambda r: bool(r["caption_runs_changed"] or r["cell_runs_changed"]),
     lambda r: bool(r["caption_runs_changed"] or r["cell_runs_changed"])),
    ("dae_bold", "zero",
     lambda c: apply_dae_bold(c["header"], c["secs"]),
     lambda r: r["dae_found"] > 0, lambda r: r["runs_changed"] > 0),
    ("annex_banner", "zero",
     lambda c: apply_annex_banner(c["header"], c["secs"]),
     lambda r: r["banners"] > 0,
     lambda r: r["cell_runs_changed"] > 0 or r["title_justified"] > 0),
    ("sender_size", "sender",
     lambda c: apply_sender_size(c["header"], c["secs"], c["sender_size"]),
     lambda r: r["sending_found"] > 0, lambda r: r["runs_changed"] > 0),
    ("header_banner", "banner",
     lambda c: apply_header_banner(c["header"], c["secs"], c["data"]),
     _banner_effect, _banner_effect),
    ("table_pagination", "always",
     lambda c: apply_table_pagination(c["secs"]),
     _never, lambda r: r["attrs_fixed"] > 0),
    ("formula_box", "always",
     lambda c: apply_formula_box(c["header"], c["secs"]),
     _never, lambda r: r["formula_boxes"] > 0),
    ("line_fit", "always",
     lambda c: apply_line_fit(c["header"], c["secs"]),
     _never, lambda r: r["fitted"] > 0),
    ("column_fit", "zero",
     lambda c: apply_table_column_fit(c["secs"]),
     lambda r: bool(r["tables_fitted"]), lambda r: bool(r["tables_fitted"])),
    ("table_merge", "zero",
     lambda c: apply_table_merge(c["header"], c["secs"]),
     lambda r: bool(r["two_level_headers"] or r["ditto_merged"] or r["label_columns"]),
     lambda r: bool(r["two_level_headers"] or r["ditto_merged"] or r["label_columns"])),
    ("fit_page_width", "always",
     lambda c: apply_fit_page_width(c["secs"]),
     lambda r: bool(r.get("tables_fitted")), lambda r: bool(r.get("tables_fitted"))),
    ("title_fit", "zero",                      # 제목 박스 폭이 다 정해진 뒤(fit_page_width가 마지막으로 줄인다) — 24pt 한 줄 맞춤
     lambda c: apply_title_fit(c["header"], c["secs"]),
     lambda r: r["found"], lambda r: r["runs_changed"] > 0),
    ("row_fit", "always",                       # 열 폭이 다 정해진 뒤 — 행 높이를 최종 폭으로
     lambda c: apply_row_fit(c["header"], c["secs"]),
     _never, lambda r: r["rows_changed"] > 0),
    ("quote_block", "always",                   # 원문 인용 줄 — 다른 단계가 다 건너뛴 뒤 표식 제거·상자 서식
     lambda c: apply_quote_block(c["header"], c["secs"]),
     _never, lambda r: r["changed"] > 0),
    ("layout", "always",
     lambda c: estimate_layout(c["header"], c["secs"]), _never, _never),
)


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
    refresh_quote_paraprs(header_root)
    section_names = sorted(n for n in data if SECTION_RE.match(n))
    section_roots = {n: ET.fromstring(data[n]) for n in section_names}

    summary = {"file": str(path), "sections": section_names}
    any_change = False
    any_target_found = False

    gates = {
        "star": star,
        "spacing": spacing,
        "zero": spacing,   # 스페이서 방식은 여백 0화와 한 몸 (원본 양식 정합)
        "sender": sender_size is not None,
        "banner": header_banner,
        "always": True,
    }
    ctx = {"header": header_root, "secs": list(section_roots.values()),
           "data": data, "sender_size": sender_size}

    for key, gate, run, found, changed in STAGES:
        if not gates[gate]:
            continue
        r = run(ctx)
        summary[key] = r
        if found is not None and found(r):
            any_target_found = True
        if changed is not None and changed(r):
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
