#!/usr/bin/env python3
"""초안 리뷰용 HTML — 20_draft.md를 hwpx 변환 전에 양식에 가깝게 보여 준다. stdlib-only.

배경('26.9.24 사용자 요청): 게이트②에서 개조식 마크다운 원문을 읽고 잘 썼는지 판단하기
어렵다는 지적. 변환 후 미리보기(kordoc `render_document`)는 AI 생성본을 근사 조판으로 그려
표와 본문이 겹치는 쪽이 나왔고(요약본 r02 2쪽 실측), 게이트②에서 hwpx 재빌드 루프를 돌지 않는
원칙과도 맞지 않는다. 그래서 초안을 바로 HTML로 그린다.

  · 글자 크기·들여쓰기·단락 간격은 `postprocess_hwpx.py` 상수를 그대로 가져온다 — 이 상수는
    `test_value_drift.py`가 format-profile.kca.md와 대조하므로 미리보기가 따로 어긋나지 않는다.
  · 항목마다 게이트② 절 주소(`□2-ㅇ3`)를 여백에 달아, 코멘트가 어느 항목을 가리키는지
    원문 인용과 주소로 함께 찾는다.
  · 스크립트·외부 글꼴·외부 URL을 넣지 않는다 — 리뷰 도구(plannotator)가 페이지 스크립트의
    외부 요청을 막지 않으므로 페이지 자체를 정적으로 둔다.
  · 쪽 나눔은 붙임 경계만 흉내 낸다. 한글 조판과 줄바꿈·쪽수는 다를 수 있다(폰트 대체).
  · `도해: 슬러그` 자리에는 `figures/{슬러그}.json` 명세로 도식을 직접 그리고(render_diagram 조각),
    research 그림 참조는 data URI로 싣는다 — 리뷰 도구는 HTML 폴더 밖 상대 경로를 읽지 않는다.

산출 위치는 `history/drafts/25_review.html`(R087 — 값싼 파생물은 루트에 두지 않는다). 같은 경로를
덮어써야 리뷰 도구가 회차 간 변경을 비교할 수 있고, 다음 변환의 `archive_revision.py begin`이
그 판본 폴더로 함께 내린다. 리뷰 결과 JSON 경로(`26_review.{시각}.json`)도 함께 알려 준다.
"""
import sys
import re
import json
import html
import base64
import argparse
import datetime
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from harness_config import history_paths, ASSETS_DIR           # noqa: E402  (경로 규약 단독 출처)
from postprocess_hwpx import (                                  # noqa: E402  (양식 실측값 단독 출처)
    TRANSITIONS, BLOCK_BOUNDARY_HEIGHT, HIERARCHY_SPACES, HIERARCHY_HANG,
    FORM_SIZES_PT, TITLE_BOX_SIZE_PT, TITLE_TEXT_WIDTH_HU, fit_title, SENDER_SIZE_PT, HIGHLIGHT_SHADE, PAGE_MARGINS,
    LINE_FIT_KINDS, fit_line, word_lens, _weighted_len, MIN_RATIO, MIN_SPACING, transition_for, column_shares,
    HEADER_SPLIT, DITTO, LABEL_FILL, FIT_PAGE_SLACK, QUOTE_FACE, QUOTE_SIZE_PT, QUOTE_LINE_SPACING,
    QUOTE_FILL, QUOTE_BORDER)
import render_diagram                                           # noqa: E402  (도식 조각 단독 출처)
import diagram_table                                            # noqa: E402  (표 도식 격자 단독 출처 — R089)
from lint_md_profile import FENCE                               # noqa: E402  (인용 블록 경계 단독 출처)

TABLE_PT = 12            # 캡션·표 셀 12pt (R023 — apply_caption_table_font 기본값)
EMBED_LIMIT = 1_500_000  # 그림 data URI 누적 상한(바이트) — 리뷰 도구의 로컬 파일 상한 2MiB 이내
LINE_SPACING = 160       # 편집용지 줄간격 160% (R008 line_spacing)
HU_PER_PT = 100
# 한글 산출물 본문 글자의 장평·자간 시작값 — kordoc 보고서 프리셋이 계층 문단 본문 charPr에 넣는 값.
# '26.9.24 시험 변환 실측: □·-·※는 100/0 그대로 두고(26건 중 22건), ㅇ만 kordoc 자체 조판으로
# 95~100/-11~0 사이로 조인다(r02 인도본·시험본 중앙값 95~97/-8). 후처리 apply_line_fit이 이 값에서
# 출발해 2줄에 맞추므로, 리뷰도 같은 값에서 출발해야 줄 수가 같다.
BODY_FIT = {"yo": (95, -8)}
BODY_FIT_DEFAULT = (100, 0)
A4_WIDTH_HU = 59528
TEXT_WIDTH_PT = (A4_WIDTH_HU - int(PAGE_MARGINS["left"]) - int(PAGE_MARGINS["right"])) / HU_PER_PT

SENDING = re.compile(r"^<\s*'?\d.*>$")
DAE = re.compile(r"^□\s*(.*)$")
YO = re.compile(r"^[ㅇ○]\s+(.*)$")
DASH = re.compile(r"^\s*-\s+(.*)$")
SUB = re.compile(r"^\[\d+\]\s+\S")
CAPTION = re.compile(r"^\*{0,2}\[\s*(.+?)\s*\]\*{0,2}$")
CHAM = re.compile(r"^※\s*(.*)$")
STAR = re.compile(r"^＊\s*(.*)$")
MARKER = re.compile(r"^(도해|도식):\s*(.+)$")
TABLE = re.compile(r"^\s*\|")
SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}")
ANNEX = re.compile(r"^(붙\s*임\s*\d*|참고\s*\d*)$")
BOLD = re.compile(r"\*\*(.+?)\*\*")
HIGHLIGHT = re.compile(r"==(.+?)==")

SHORT_CELL = 8          # 이 글자 수 이하 셀은 가운데 정렬
# 표 칸 — kordoc 산출 실측(표 안여백 좌우 510·상하 141 HWPUNIT, 셀 문단 줄간격 130%). 열 폭은 후처리와 같은
# column_shares로 나눈다 — 브라우저 자동 배치로 두면 열 폭이 최대 6%p 달라 행 높이·쪽수가 달라졌다('26.9.24).
CELL_PAD_PT = (1.41, 5.1)
TABLE_LINE = 1.3
TABLE_WIDTH_HU = A4_WIDTH_HU - int(PAGE_MARGINS["left"]) - int(PAGE_MARGINS["right"])
KIND_MARK = {"yo": "ㅇ", "dash": "-", "cham": "※", "star": "＊"}


APOS_NUM = re.compile(r"'(?=\d)")
PAIR_SINGLE = re.compile(r"'([^'\n]+?)'")
PAIR_DOUBLE = re.compile(r'"([^"\n]+?)"')


def curly(text):
    """곧은따옴표를 둥근따옴표로 — kordoc이 변환 때 같게 바꾼다('25년 → ’25년). 둥근따옴표는 한글 글꼴에서
    전각이라 줄 수 계산도 이 글자로 해야 한글과 맞는다('26.9.24 □3-ㅇ2-1 — 곧은따옴표로 재서 화면 3줄)."""
    text = APOS_NUM.sub("’", text)
    text = PAIR_DOUBLE.sub(r"“\1”", PAIR_SINGLE.sub(r"‘\1’", text))
    return text.replace("'", "’")


def inline(text):
    """이스케이프 후 볼드(`**`)·하이라이트(`==`, R040)만 살린다. 따옴표는 한글 산출물처럼 둥글게."""
    s = html.escape(curly(text), quote=False)
    s = HIGHLIGHT.sub(r'<mark>\1</mark>', s)
    return BOLD.sub(r"<b>\1</b>", s)


def split_row(line):
    cells = line.strip()
    if cells.startswith("|"):
        cells = cells[1:]
    if cells.endswith("|"):
        cells = cells[:-1]
    return [c.strip() for c in cells.split("|")]


def parse(text):
    """초안을 블록 목록으로 — 각 블록은 kind·줄 번호·내용. 표는 연속된 `|` 줄을 한 블록으로 묶는다."""
    lines = text.splitlines()
    blocks, i, title_done = [], 0, False
    while i < len(lines):
        raw = lines[i]
        body = raw.strip()
        no = i + 1
        if not body:
            i += 1
            continue
        if not title_done:
            blocks.append({"kind": "title", "line": no, "text": body})
            title_done = True
        elif FENCE.match(raw):                    # 원문 인용 블록 — 닫는 울타리까지 글자 그대로 한 블록
            j = i + 1
            while j < len(lines) and not FENCE.match(lines[j]):
                j += 1
            blocks.append({"kind": "quote", "line": no, "lines": lines[i + 1:j]})
            i = j + 1
            continue
        elif TABLE.match(raw):
            rows = []
            while i < len(lines) and TABLE.match(lines[i]):
                if not SEPARATOR.match(lines[i].replace("|", "", 1)):
                    rows.append(split_row(lines[i]))
                i += 1
            kind = "table"
            if rows and len(rows[0]) >= 2 and ANNEX.match(rows[0][0]):
                kind = "banner"
            elif len(rows) == 1 and len(rows[0]) == 1:
                kind = "formula"
            blocks.append({"kind": kind, "line": no, "rows": rows})
            continue
        elif SENDING.match(body):
            blocks.append({"kind": "sending", "line": no, "text": body})
        elif m := DAE.match(body):
            blocks.append({"kind": "dae", "line": no, "text": m.group(1)})
        elif m := YO.match(body):
            blocks.append({"kind": "yo", "line": no, "text": m.group(1)})
        elif SUB.match(body):
            blocks.append({"kind": "sub", "line": no, "text": body})
        elif m := CAPTION.match(body):
            blocks.append({"kind": "caption", "line": no, "text": m.group(1)})
        elif m := CHAM.match(body):
            blocks.append({"kind": "cham", "line": no, "text": m.group(1)})
        elif m := STAR.match(body):
            blocks.append({"kind": "star", "line": no, "text": m.group(1)})
        elif m := MARKER.match(body):
            blocks.append({"kind": "marker", "line": no, "text": f"{m.group(1)}: {m.group(2)}"})
        elif m := DASH.match(raw):
            blocks.append({"kind": "dash", "line": no, "text": m.group(1)})
        elif body == "끝.":
            blocks.append({"kind": "end", "line": no, "text": body})
        else:
            blocks.append({"kind": "other", "line": no, "text": body})
        i += 1
    return blocks


def address(blocks):
    """게이트② 절 주소를 단다 — □N · □N-ㅇM · □N-ㅇM-K(대시) · □N-표K · □N-※K · □N-그림K, 붙임은 `붙임N-…`.

    그림 자리에 절 주소(□N)를 그대로 주면 □ 줄과 겹쳐 코멘트가 엉뚱한 곳에 붙는다('26.9.24 실측)."""
    scope, dae = "", 0
    yo = dash = table = cham = annex = fig = quote = 0
    for b in blocks:
        k = b["kind"]
        if k == "dae":
            dae += 1
            scope, yo, dash, table, cham, fig, quote = f"□{dae}", 0, 0, 0, 0, 0, 0
            b["addr"] = scope
        elif k == "banner":
            annex += 1
            scope, yo, dash, table, cham, fig, quote = f"붙임{annex}", 0, 0, 0, 0, 0, 0
            b["addr"] = scope
        elif k == "yo":
            yo, dash = yo + 1, 0
            b["addr"] = f"{scope}-ㅇ{yo}"
        elif k == "dash":
            dash += 1
            b["addr"] = f"{scope}-ㅇ{yo}-{dash}" if yo else f"{scope}-{dash}"
        elif k in ("table", "formula"):
            table += 1
            b["addr"] = f"{scope}-표{table}"
        elif k in ("cham", "star"):
            cham += 1
            b["addr"] = f"{scope}-※{cham}"
        elif k == "title":
            b["addr"] = "제목"
        elif k == "sending":
            b["addr"] = "발신"
        elif k == "marker":
            fig += 1
            b["addr"] = f"{scope}-그림{fig}"
        elif k == "quote":
            quote += 1
            b["addr"] = f"{scope}-인용{quote}"
        elif k == "caption":
            b["addr"] = ""                 # 캡션은 바로 아래 표의 주소를 함께 쓴다
        else:
            b["addr"] = scope
    return blocks


def gap_pt(prev, kind):
    """앞 블록과의 간격(pt) — 후처리 스페이서 규칙(`transition_for`)을 그대로 쓴다(R013·R060·R009·R088)."""
    as_kind = {"sub": "yo", "formula": "table", "marker": "figure", "quote": "quote"}
    t = transition_for(as_kind.get(prev, prev), as_kind.get(kind, kind))
    return t[1] / HU_PER_PT if t else 0


def render_table(rows, formula=False):
    """GFM 표 → HTML. 후처리와 같은 병합 표기를 그린다 — 머리글 `A > B`는 2단 머리행, 본문 `〃`는
    위 칸과 세로 병합, 첫 열 본문이 모두 **굵게**면 라벨 열 음영(postprocess `apply_table_merge`)."""
    if formula:
        return f'<table class="formula"><tr><td>{inline(rows[0][0])}</td></tr></table>'
    head, *body = rows
    parts = [c.split(HEADER_SPLIT, 1) for c in head]
    plain = [[curly(BOLD.sub(r"\1", HIGHLIGHT.sub(r"\1", c))) for c in r] for r in rows]
    shares = column_shares(plain, TABLE_WIDTH_HU) if len(head) > 1 else None
    cols = "".join(f'<col style="width:{sh * 100:.2f}%">' for sh in shares) if shares else ""
    out = [f"<table><colgroup>{cols}</colgroup><thead>" if cols else "<table><thead>"]
    if any(len(x) == 2 for x in parts):
        top, sub, i = [], [], 0
        while i < len(parts):
            if len(parts[i]) == 1:
                top.append(f'<th rowspan="2">{inline(parts[i][0])}</th>')
                i += 1
                continue
            j = i
            while j < len(parts) and len(parts[j]) == 2 and parts[j][0].strip() == parts[i][0].strip():
                sub.append(f"<th>{inline(parts[j][1].strip())}</th>")
                j += 1
            top.append(f'<th colspan="{j - i}">{inline(parts[i][0].strip())}</th>')
            i = j
        out += ["<tr>", *top, "</tr><tr>", *sub, "</tr>"]
    else:
        out += ["<tr>", *[f"<th>{inline(c)}</th>" for c in head], "</tr>"]
    out.append("</thead><tbody>")
    # 라벨 열 — 첫 열이 모두 굵게, 또는 2열 표(kordoc이 2열 표의 첫 열을 스스로 굵게 만들어 후처리가
    # 라벨 열로 칠한다 — '26.9.24 시험 변환 실측, 붙임2 「수집 프롬프트 구성」)
    label = bool(body) and len(head) > 1 and (len(head) == 2 or all(
        re.fullmatch(r"\*\*.+\*\*", r[0].strip()) or r[0].strip() == DITTO for r in body if r))
    # 세로 병합: 셀별 rowspan 계산 — `〃`는 바로 위 칸(같은 열)의 rowspan을 늘리고 자신은 그리지 않는다
    spans = [[1] * len(r) for r in body]
    owner = {}
    for ri, r in enumerate(body):
        for ci, c in enumerate(r):
            if c.strip() == DITTO and (ri - 1, ci) in owner:
                oi = owner[(ri - 1, ci)]
                spans[oi][ci] += 1
                spans[ri][ci] = 0
                owner[(ri, ci)] = oi
            else:
                owner[(ri, ci)] = ri
    for ri, r in enumerate(body):
        cells = []
        for ci, c in enumerate(r):
            if not spans[ri][ci]:
                continue
            rs = f' rowspan="{spans[ri][ci]}"' if spans[ri][ci] > 1 else ""
            cls = "lab" if (label and ci == 0) else ("c" if len(c) <= SHORT_CELL else "l")
            cells.append(f'<td class="{cls}"{rs}>{inline(c)}</td>')
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def fit_style(kind, text):
    """계층 문단의 장평·자간 — 후처리 `apply_line_fit`(R062)과 같은 계산으로 2줄에 맞춘다.

    (인라인 style, 넘침 여부, 장평 배율). 장평은 CSS에 없어 scaleX로 흉내 내고, 폭·내어쓰기는 배율만큼
    늘려 되돌린다. 하한(자간 -10·장평 90)까지 조여도 넘치면 한글에서도 3줄이 되므로 표시한다."""
    if kind not in LINE_FIT_KINDS:
        return "", False, 1.0
    plain = curly(BOLD.sub(r"\1", HIGHLIGHT.sub(r"\1", text)))
    wl = _weighted_len(plain)                 # 앞 공백·부호는 내어쓰기 칸에 들어간다(후처리 _body_len과 같음)
    size = FORM_SIZES_PT.get(kind, FORM_SIZES_PT["yo"])
    hang = HIERARCHY_HANG.get(kind, 0) / HU_PER_PT
    chosen = fit_line(wl, TEXT_WIDTH_PT - hang, size, *BODY_FIT.get(kind, BODY_FIT_DEFAULT), words=word_lens(plain))
    over = chosen is None
    ratio, spacing = chosen or (MIN_RATIO, MIN_SPACING)
    r = ratio / 100
    style = (f"box-sizing:border-box;letter-spacing:{spacing / 100:g}em;transform:scaleX({r:g});transform-origin:0 0;"
             f"width:{100 / r:.3f}%;padding-left:{hang / r:.2f}pt;text-indent:-{hang / r:.2f}pt")
    return style, over, r


def marker_html(kind, mark, r):
    """계층 부호 칸 — 앞 공백과 부호를 내어쓰기 폭의 고정 칸에 넣어 첫 줄 본문이 둘째 줄과 같은 자리에서
    시작하게 한다('26.9.24 게이트② 지적 — 공백·부호를 글자폭대로 그리면 1줄과 2줄의 앞이 어긋난다).
    한글 산출물은 부호 뒤 탭과 내어쓰기(HIERARCHY_HANG)로 같은 정렬을 만든다. 공백 1칸 = 글자 크기의 절반."""
    hang = HIERARCHY_HANG.get(kind, 0) / HU_PER_PT
    lead = HIERARCHY_SPACES.get(kind, 0) * FORM_SIZES_PT.get(kind, FORM_SIZES_PT["yo"]) / 2
    return (f'<span class="mk" style="display:inline-block;box-sizing:border-box;text-indent:0;'
            f'width:{hang / r:.2f}pt;padding-left:{lead / r:.2f}pt">{mark}</span>')


def render_block(b, prev):
    k, addr = b["kind"], b.get("addr", "")
    style = f' style="margin-top:{gap_pt(prev, k):g}pt"' if gap_pt(prev, k) else ""
    label = f'<span class="addr">{html.escape(addr)}</span>' if addr else ""
    head = f'<div class="blk {k}" id="L{b["line"]}" data-line="{b["line"]}" data-addr="{html.escape(addr)}"{style}>{label}'
    if k == "caption":                     # 표·그림 제목은 대괄호째 보인다 — 한글 산출물과 같게
        return f'{head}<p>[ {inline(b["text"])} ]</p></div>'
    if k == "title":                       # 제목표도 지목 대상 — blk·주소를 달아야 클릭·드래그로 골라진다
        ratio, spacing, over = fit_title(curly(BOLD.sub(r"\1", b["text"])), TITLE_TEXT_WIDTH_HU / HU_PER_PT)
        fit = "" if over else f' style="white-space:nowrap;letter-spacing:{spacing / 100:g}em;transform:scaleX({ratio / 100:g})"'
        return f'{head}<div class="titlebox"><div class="band"></div><h1{fit}>{inline(b["text"])}</h1><div class="band low"></div></div></div>'
    if k == "quote":                       # 원문 인용 — 줄 그대로, 해석하지 않는다(한글: 회색 상자·고정폭)
        return f'{head}<pre class="quote">{html.escape(chr(10).join(b["lines"]))}</pre></div>'
    if k in ("table",):
        return f"{head}{render_table(b['rows'])}</div>"
    if k == "formula":
        return f"{head}{render_table(b['rows'], formula=True)}</div>"
    if k == "banner":
        cells = [c for c in b["rows"][0] if c]
        name = cells[1] if len(cells) > 1 else ""
        return (f'{head}<div class="banner"><span class="lab">{inline(cells[0])}</span>'
                f'<span class="name">{inline(name)}</span></div></div>')
    fit, over, r = fit_style(k, b.get("text", ""))
    pstyle = f' style="{fit}"' if fit else ""
    if over:
        head = head.replace('class="blk ', 'class="blk over ', 1).replace(
            '>', ' title="장평 90%·자간 -10까지 조여도 3줄 — 한글에서도 넘치므로 문구를 줄여야 합니다(R062)">', 1)
    if k == "dae":
        return f'{head}<p{pstyle}>{marker_html(k, "□", r)}{inline(b["text"])}</p></div>'
    if k in KIND_MARK:
        return f'{head}<p{pstyle}>{marker_html(k, KIND_MARK[k], r)}{inline(b["text"])}</p></div>'
    if k == "marker":
        return f'{head}{b.get("figure") or placeholder(b["text"])}</div>'
    return f'{head}<p>{inline(b["text"])}</p></div>'


def placeholder(text, why=""):
    note = f" ({html.escape(why)})" if why else ""
    return f'<div class="figure">그림 자리 — {inline(text)}{note}</div>'


def figure_html(slug, work_dir, budget):
    """`도해: 슬러그` 자리에 넣을 조각 — figures/{슬러그}.json 명세가 있으면 도식을 그리고, research
    그림 참조면 표시 크기(R088 계산)로 data URI를 넣는다. budget은 남은 data URI 바이트(리스트 1칸)."""
    spec_path = pathlib.Path(work_dir) / "figures" / f"{slug}.json"
    if not spec_path.is_file():
        return None
    try:
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        if spec.get("type") == "image":
            blob = (pathlib.Path(work_dir) / spec["src"]).read_bytes()
            if len(blob) > budget[0]:
                return placeholder(f"도해: {slug}", "그림이 커서 리뷰 화면에는 싣지 않음")
            budget[0] -= len(blob)
            w, h, dpi = render_diagram.image_pixels(blob)
            d = render_diagram.figure_display(w, h, dpi, render_diagram.DEFAULT_WIDTH_MM)
            mime = {b"\x89P": "image/png", b"\xff\xd8": "image/jpeg", b"GI": "image/gif", b"BM": "image/bmp"}[blob[:2]]
            return (f'<div class="fig"><img alt="{html.escape(spec.get("caption", slug))}" style="width:{d["w_mm"]}mm" '
                    f'src="data:{mime};base64,{base64.b64encode(blob).decode()}"></div>')
        if diagram_table.wants_table(spec):   # 변환에서 표로 들어가는 도식은 리뷰도 같은 격자로 그린다(R089)
            return f'<div class="fig">{diagram_table.html(spec)}</div>'
        return (f'<div class="fig"><div style="width:{render_diagram.width_px(spec)}px;margin:0 auto">'
                f'{render_diagram.fragment(spec)}</div></div>')
    except (OSError, ValueError, KeyError) as e:
        return placeholder(f"도해: {slug}", f"명세 오류: {e}")


HEADER_BANNER_DIR = ASSETS_DIR / "kca-header-banner"


def header_banner_css():
    """문서 머리말 배너(기관 로고 · 슬로건) — 후처리 `apply_header_banner`가 hwpx 머리말에 넣는 것과 같은 그림을
    같은 자리·크기로 그린다('26.9.24 사용자 지시 — 표준안 머리말을 리뷰어에 똑같이).

    크기는 번들 조각(fragment.xml)의 1×2 표·그림 값에 본문 폭 맞춤(fit_page_width) 배율을 곱한 것 — 시험 변환
    실측 표 47625·로고 13437×1788·슬로건 9587×2556 HWPUNIT과 같다. 자리는 위 여백(10mm) 안 머리말 영역,
    왼쪽 칸 로고는 아래 맞춤, 오른쪽 칸 슬로건은 가운데·오른쪽 맞춤(조각의 vertAlign·문단 정렬). 쪽마다
    `::before`로 그려 항목 순서(바뀐 항목만 바꿔 끼우는 번호)를 건드리지 않는다. 자산이 없으면 그리지 않는다."""
    try:
        frag = (HEADER_BANNER_DIR / "fragment.xml").read_text(encoding="utf-8")
        logo = (HEADER_BANNER_DIR / "kcaHdrLogo.png").read_bytes()
        slogan = (HEADER_BANNER_DIR / "kcaHdrSlogan.bmp").read_bytes()
    except OSError:
        return ""
    tw, th = map(int, re.search(r'<hp:tbl [^>]*>\s*<hp:sz width="(\d+)"[^>]*height="(\d+)"', frag).groups())
    om = re.search(r'<hp:tbl .*?<hp:outMargin left="(\d+)" right="(\d+)" top="(\d+)"', frag, re.S)
    ol, orr, ot = (int(x) for x in om.groups())
    pics = [tuple(map(int, m)) for m in re.findall(r'<hp:pic .*?<hp:sz width="(\d+)"[^>]*height="(\d+)"', frag, re.S)]
    cm = re.search(r'<hp:cellMargin left="(\d+)" right="(\d+)" top="(\d+)" bottom="(\d+)"', frag)
    cl, cr, ct, cb = (int(x) for x in cm.groups())
    body = A4_WIDTH_HU - int(PAGE_MARGINS["left"]) - int(PAGE_MARGINS["right"])
    k = min(1.0, (body - FIT_PAGE_SLACK - ol - orr) / tw)       # fit_page_width와 같은 배율
    pt = lambda hu: hu * k / HU_PER_PT
    (lw, lh), (sw, sh) = pics[0], pics[1]
    left = int(PAGE_MARGINS["left"]) / HU_PER_PT + ol / HU_PER_PT
    top = int(PAGE_MARGINS["top"]) / HU_PER_PT + ot / HU_PER_PT
    uri = lambda mime, b: f"data:{mime};base64,{base64.b64encode(b).decode()}"
    return (f".page::before {{ content:''; position:absolute; left:{left:.2f}pt; top:{top:.2f}pt; width:{pt(tw):.2f}pt; height:{pt(th):.2f}pt; "
            f"pointer-events:none; background: url({uri('image/png', logo)}) no-repeat left {cl / HU_PER_PT:.2f}pt bottom {cb / HU_PER_PT:.2f}pt / {pt(lw):.2f}pt {pt(lh):.2f}pt, "
            f"url({uri('image/bmp', slogan)}) no-repeat right {cr / HU_PER_PT:.2f}pt center / {pt(sw):.2f}pt {pt(sh):.2f}pt; }}\n")


def css():
    hang = {k: v / HU_PER_PT for k, v in HIERARCHY_HANG.items()}
    # 쪽 여백 — 한글 본문 영역은 위=위쪽+머리말, 아래=아래쪽+꼬리말(297−25−25 = 247mm). 머리말·꼬리말을 빼면
    # 본문이 272mm로 잡혀 리뷰가 쪽수를 약 10% 적게 보였다('26.9.24 시험 변환 대조).
    mm = {k: int(PAGE_MARGINS[k]) / 7200 * 25.4 for k in ("left", "right")}
    mm["top"] = (int(PAGE_MARGINS["top"]) + int(PAGE_MARGINS["header"])) / 7200 * 25.4
    mm["bottom"] = (int(PAGE_MARGINS["bottom"]) + int(PAGE_MARGINS["footer"])) / 7200 * 25.4
    # 명조 폴백은 굵은 글꼴이 있는 나눔명조를 AppleMyungjo보다 앞에 둔다 — AppleMyungjo는 볼드가
    # 없어 브라우저가 한글을 굵게 합성하지 않으므로 ㅇ 괄호 리드(R016)가 보통 굵기로 보였다('26.9.24 f7).
    return f"""
:root {{ --paper:#ffffff; --desk:#e9e8e6; --ink:#111111; --muted:#8a8a8a; --band:#0080C0; --line:#1B1760; --head:#dce6f1; --mark:{HIGHLIGHT_SHADE}; }}
html, body {{ margin:0; background:var(--desk); color:var(--ink); }}
.page {{ box-sizing:border-box; width:210mm; min-height:297mm; margin:16px auto; background:var(--paper); box-shadow:0 1px 4px rgba(0,0,0,.25);
  padding:{mm['top']:.2f}mm {mm['right']:.2f}mm {mm['bottom']:.2f}mm {mm['left']:.2f}mm; position:relative;
  font-family:"휴먼명조","HCR Batang","Nanum Myeongjo","나눔명조","AppleMyungjo","Noto Serif KR",serif; font-size:{FORM_SIZES_PT['yo']}pt; line-height:{LINE_SPACING}%; }}
.blk {{ position:relative; }}
.blk p {{ margin:0; text-align:justify; }}
.addr {{ position:absolute; left:-19mm; top:.2em; width:17mm; text-align:right; font:10px/1.3 "Apple SD Gothic Neo","Malgun Gothic",sans-serif; color:var(--muted); user-select:none; }}
.titlebox {{ margin:0 0 4pt; text-align:center; }}
.titlebox .band {{ height:3.8pt; background:var(--band); }}
.titlebox .band.low {{ background:radial-gradient(circle, #3CBFFF, var(--band)); }}
.titlebox h1 {{ margin:0; padding:4pt 0; font-family:"HY헤드라인M","HYHeadLine-Medium","Apple SD Gothic Neo","Noto Sans KR",sans-serif; font-size:{TITLE_BOX_SIZE_PT}pt; font-weight:700; line-height:1.4; }}
.sending p {{ text-align:right; font-size:{SENDER_SIZE_PT}pt; }}
.dae p {{ font-family:"HY헤드라인M","HYHeadLine-Medium","Apple SD Gothic Neo","Noto Sans KR",sans-serif; font-size:{FORM_SIZES_PT['dae']}pt; font-weight:700; padding-left:{hang['dae']}pt; text-indent:-{hang['dae']}pt; }}
.sub p {{ font-weight:700; }}
.yo p {{ padding-left:{hang['yo']}pt; text-indent:-{hang['yo']}pt; }}
.dash p {{ padding-left:{hang['dash']}pt; text-indent:-{hang['dash']}pt; }}
.cham p, .star p {{ font-family:"맑은 고딕","Malgun Gothic","Apple SD Gothic Neo",sans-serif; font-size:{FORM_SIZES_PT['cham']}pt; padding-left:{hang['cham']}pt; text-indent:-{hang['cham']}pt; }}
.caption p {{ text-align:center; font-family:"맑은 고딕","Malgun Gothic","Apple SD Gothic Neo",sans-serif; font-size:{TABLE_PT}pt; font-weight:700; }}
.end p {{ text-align:right; }}
mark {{ background:var(--mark); font-weight:700; }}
.blk.over {{ box-shadow:-4px 0 0 #d33; }} .blk.over .addr {{ color:#d33; font-weight:700; }}
table {{ width:100%; table-layout:fixed; border-collapse:collapse; font-family:"맑은 고딕","Malgun Gothic","Apple SD Gothic Neo",sans-serif; font-size:{TABLE_PT}pt; line-height:{TABLE_LINE}; border-top:2px solid #222; border-bottom:2px solid #222; }}
th, td {{ border:1px solid #666; padding:{CELL_PAD_PT[0]}pt {CELL_PAD_PT[1]}pt; vertical-align:middle; overflow-wrap:anywhere; }}
th {{ background:var(--head); text-align:center; font-weight:700; border-bottom:3px double #444; }}
td.c {{ text-align:center; }} td.l {{ text-align:left; }}
td.lab {{ background:{LABEL_FILL}; text-align:center; font-weight:700; }}
pre.quote {{ margin:0; padding:2.83pt 5.67pt; background:{QUOTE_FILL}; border:0.12mm solid {QUOTE_BORDER}; font-family:"{QUOTE_FACE}","GulimChe","D2Coding","Menlo",monospace; font-size:{QUOTE_SIZE_PT}pt; line-height:{QUOTE_LINE_SPACING}%; white-space:pre-wrap; word-break:break-all; }}
table.formula {{ border:0.4mm solid #000; background:#DFE6F7; }} table.formula td {{ text-align:center; padding:6pt; font-weight:700; border:0.4mm solid #000; }}
.banner {{ display:flex; align-items:stretch; border-top:0.5mm solid var(--line); border-bottom:0.5mm solid var(--line);
  font-family:"HY헤드라인M","HYHeadLine-Medium","Apple SD Gothic Neo",sans-serif; font-size:16pt; }}
.banner .lab {{ background:var(--line); color:#fff; padding:2pt 10pt; white-space:nowrap; }}
.banner .name {{ padding:2pt 10pt; }}
.figure {{ border:1.5px dashed #999; color:#666; text-align:center; padding:18pt 6pt; font-size:12pt; }}
.fig {{ text-align:center; line-height:normal; }} .fig .dg {{ text-align:left; }} .fig img {{ display:inline-block; max-width:100%; }}
.page {{ word-break:keep-all; overflow-wrap:break-word; }}
{render_diagram.css()}
{diagram_table.css()}
@media print {{ .page {{ margin:0; box-shadow:none; }} .addr {{ display:none; }} }}
""" + header_banner_css()


def render_parts(text, work_dir=None):
    """화면 조각 — 쪽마다 항목(주소·줄·HTML) 목록. 라이브 리뷰 서버가 바뀐 항목만 골라 보내는 단위다."""
    blocks = address(parse(text))
    budget = [EMBED_LIMIT]
    for b in blocks:                              # 도해 마커 — 명세가 있으면 도식·그림을 싣는다
        m = MARKER.match(b.get("text", "")) if b["kind"] == "marker" else None
        if m and work_dir and m.group(1) == "도해":
            b["figure"] = figure_html(m.group(2).strip(), work_dir, budget)
    pages, cur, prev = [], [], None
    for b in blocks:
        if b["kind"] == "banner" and cur:        # 붙임은 새 쪽에서 시작한다(한글 산출물과 같게)
            pages.append(cur)
            cur, prev = [], None
        cur.append({"addr": b.get("addr", ""), "line": b["line"], "html": render_block(b, prev)})
        prev = b["kind"]
    if cur:
        pages.append(cur)
    counts = {k: sum(1 for b in blocks if b["kind"] == k) for k in ("dae", "yo", "dash", "table", "banner")}
    counts["figure"] = sum(1 for b in blocks if b.get("figure"))
    title = next((b["text"] for b in blocks if b["kind"] == "title"), "초안")
    return {"title": title, "css": css(), "pages": pages, "counts": {"blocks": len(blocks), **counts}}


def page_html(items):
    return '<section class="page">\n' + "\n".join(x["html"] for x in items) + "\n</section>"


def render(text, now=None, work_dir=None):
    parts = render_parts(text, work_dir)
    return document(parts, now), parts["counts"]


def document(parts, now=None):
    """조각을 한 장의 정적 HTML로 묶는다."""
    stamp = (now or datetime.datetime.now()).strftime("%Y-%m-%d %H:%M")
    body = "\n".join(page_html(p) for p in parts["pages"])
    # 상단 안내 띠는 두지 않는다('26.9.24 사용자 지시 — 불필요). 생성 시각은 보이지 않는 meta로만 남긴다.
    # 쪽은 한글 종이처럼 흰 바탕이어야 한다 — 'only light'로 브라우저 강제 다크(Chrome Auto Dark)의 반전을 막는다
    # (운영 교훈 '26.8.7: color-scheme 미선언 페이지가 강제 다크에서 배경만 반전돼 글자가 안 보였다)
    doc = (f'<!doctype html>\n<html lang="ko"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width, initial-scale=1">'
           f'<meta name="color-scheme" content="only light">'
           f'<meta name="generated" content="{stamp}">'
           f'<title>{html.escape(parts["title"])} — 리뷰</title><style>{parts["css"]}</style></head>\n'
           f'<body>\n{body}\n</body></html>\n')
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(description="20_draft.md → 리뷰용 HTML (변환 전 게이트②)")
    ap.add_argument("draft", help="20_draft.md 경로")
    ap.add_argument("-o", "--out", help="출력 HTML(미지정 시 {작업폴더}/history/drafts/25_review.html)")
    args = ap.parse_args(argv)

    draft = pathlib.Path(args.draft)
    now = datetime.datetime.now()
    doc, counts = render(draft.read_text(encoding="utf-8"), now, draft.resolve().parent)
    drafts = history_paths(draft.resolve().parent)["drafts"]
    out = pathlib.Path(args.out) if args.out else drafts / "25_review.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc, encoding="utf-8")
    drafts.mkdir(parents=True, exist_ok=True)
    result = drafts / f"26_review.{now.strftime('%Y%m%d-%H%M%S')}.json"
    print(json.dumps({"html": str(out), "result": str(result), **counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
