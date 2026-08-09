#!/usr/bin/env python3
"""md-profile 개조식 마크다운 → base.hwpx (stdlib-only).

노트북 하네스의 kordoc `generate_document` 자리를 웹앱에서 대신한다. 산출물은
`postprocess_hwpx.py --all`이 그대로 받을 수 있는 형태다 —
개조식 리터럴 기호(□ ㅇ - ※ ＊)를 문단 텍스트에 두고, 스타일은 동결 정본
`assets/kca-header.xml`의 고정 id를 참조한다(설계문서 §5 실측 확정 맵).

3층 구조: parse(md) → render(blocks) → package(section_xml).
파서는 hwpx를 모르고, 직렬화기는 md를 모른다.

usage: md2hwpx.py <prepared.md> -o <base.hwpx>
"""
import sys, re, json, zipfile, pathlib, argparse

ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"

# --- 스타일 id 맵 (설계문서 §5 — kordoc 산출물 실측 확정) --------------------
PP_SENDING, PP_DAE, PP_YO, PP_DASH, PP_CHAM = "17", "8", "9", "10", "20"
PP_PLAIN, PP_TBL_WRAP, PP_CELL, PP_TITLE_PAD = "0", "17", "18", "24"
CP_BODY, CP_BODY_B, CP_DAE, CP_REF = "0", "1", "11", "13"
CP_TITLE, CP_TITLE_PAD = "25", "26"
CP_CELL, CP_CELL_B = "22", "23"

BF_TITLE_TBL, BF_CONTENT_TBL = "1", "2"
BF_TITLE_CELLS = ("11", "13", "12")          # 상단밴드 / 제목 / 하단밴드
BF_HEAD = ("15", "16", "17")                 # 헤더행   좌/중/우
BF_FIRST = ("18", "19", "20")                # 첫 본문행 좌/중/우
BF_MID = ("21", "13", "22")                  # 중간행   좌/중/우
BF_LAST = ("23", "24", "25")                 # 마지막행 좌/중/우
BF_BANNER = ("26", "27", "28")               # 붙임 배너 라벨/스페이서/제목
BF_FORMULA = "14"

# --- 기하 (HWPUNIT = 1/7200 inch) -------------------------------------------
TEXT_WIDTH = 48190          # 본문 폭 (pagePr 59528 − 좌우 여백 5669×2)
FIT_SLACK = 283             # R036·R042: 표 총폭 < 본문폭 − 283
W_CONTENT = 46389           # 콘텐츠 표 sz (outMargin 0)
OUTM_TITLE = 283            # 제목 박스 outMargin (양식 실측)
# 제목 박스 sz — 총폭(sz + outMargin 좌우)이 본문폭 − 283 '미만'이어야 한다(R042).
# 같게 두면 slack 0이라 한컴이 표를 다음 줄로 내려 위에 15pt 빈 줄이 생긴다.
W_TITLE = TEXT_WIDTH - FIT_SLACK - OUTM_TITLE * 2 - 1   # 47340
H_ROW_BASE, H_ROW_LINE = 2202, 1920   # 행 높이 = BASE + LINE×(줄수−1) — 실측
H_TITLE_PAD, H_TITLE_MAIN = 382, 2850
CELL_PAD = 282              # cellMargin 좌우 141×2
CHAR_HU = 600               # 12pt 반각 1칸 폭 (전각 = 2칸)
W_BANNER_LABEL, W_BANNER_GAP = 5968, 565

MIN_COL_UNITS = 8           # 열 하한 표시폭
MAX_COL_RATIO = 0.40        # 열 상한 비율

SENDING_RE = re.compile(r"^<\s*'?\d")
CAPTION_RE = re.compile(r"^[\[<]")
BANNER_RE = re.compile(r"^(붙\s*임|붙임\s*\d+|참고\s*\d*)$")
BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
DAE, STAR, CHAM, DASH, ARROW = "□", "＊", "※", "-", "☞"
YO_CHARS = ("ㅇ", "○")


class Md2HwpxError(Exception):
    """변환 불가 입력 — exit 2 대상."""


def wlen(s):
    """표시폭 — 한글·전각 2, 그 외 1."""
    return sum(2 if ord(c) > 0x1100 else 1 for c in s)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# 1층: 파서 — md-profile 서브셋만 인식한다
# ---------------------------------------------------------------------------

def split_bold(text):
    """'a **b** c' → [('a ',False),('b',True),(' c',False)]. R016 리드 라벨 보존.

    B안(hwpx 스킬 create_document.py)이 깨진 지점이 정확히 여기다 — 인라인을
    파싱하지 않으면 `**`가 문서에 리터럴로 박힌다.
    """
    segs, pos = [], 0
    for m in BOLD_RE.finditer(text):
        if m.start() > pos:
            segs.append((text[pos:m.start()], False))
        segs.append((m.group(1), True))
        pos = m.end()
    if pos < len(text):
        segs.append((text[pos:], False))
    return segs or [("", False)]


def _table_rows(buf):
    rows = []
    for line in buf:
        s = line.strip()
        if re.match(r"^\|[\s\-:|]+\|?$", s):      # 구분행
            continue
        cells = [c.strip() for c in s.split("|")]
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        if cells:
            rows.append(cells)
    return rows


def _flush_table(rows):
    if not rows:
        return None
    ncol = max(len(r) for r in rows)
    if len(rows) == 1 and ncol == 1:
        return {"t": "formula", "text": rows[0][0]}
    if len(rows) == 1 and ncol == 3 and BANNER_RE.match(rows[0][0].strip()):
        return {"t": "banner", "cells": [rows[0][0], "", rows[0][2] if len(rows[0]) > 2 else ""]}
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    return {"t": "table", "rows": rows}


def parse(md):
    blocks, buf, title_taken = [], [], False
    for raw in md.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if s.startswith("|"):
            buf.append(s)
            continue
        if buf:
            b = _flush_table(_table_rows(buf))
            if b:
                blocks.append(b)
            buf = []
        if not s:
            continue
        if not title_taken:
            blocks.append({"t": "title", "text": re.sub(r"^#\s+", "", s)})
            title_taken = True
            continue
        if s.startswith(DAE):
            blocks.append({"t": "dae", "segs": split_bold(s)})
        elif s[0] in YO_CHARS:
            blocks.append({"t": "yo", "segs": split_bold(s)})
        elif s.startswith(STAR):
            blocks.append({"t": "star", "segs": split_bold(s)})
        elif s.startswith(CHAM):
            blocks.append({"t": "cham", "segs": split_bold(s)})
        elif s.startswith(ARROW):
            blocks.append({"t": "arrow", "segs": split_bold(s)})
        elif SENDING_RE.match(s):
            blocks.append({"t": "sending", "segs": split_bold(s)})
        elif CAPTION_RE.match(s):
            blocks.append({"t": "caption", "segs": split_bold(s)})
        elif s.startswith(DASH):
            blocks.append({"t": "dash", "segs": split_bold(s)})
        else:
            blocks.append({"t": "plain", "segs": split_bold(s)})
    if buf:
        b = _flush_table(_table_rows(buf))
        if b:
            blocks.append(b)
    if not title_taken:
        raise Md2HwpxError("제목 줄(첫 비어있지 않은 줄)을 찾지 못했습니다")
    return blocks


# ---------------------------------------------------------------------------
# 열 폭 — 필요 폭(1줄에 담기는 폭) 기준 배분 (설계문서 §7)
#
# kordoc은 내용과 역행하는 폭을 낸다(실측: 34폭 열에 8.6폭/줄만 배정 → 5줄).
#
# 고정 비율 상한(옛 MAX_COL_RATIO=0.40)은 폐기했다 — 2열 표에서 ncol×0.40 < 1이라
# 두 열 모두 상한에 걸려 20%가 미배정으로 남고, 그 잔여가 최광열 하나에 몰리면서
# 배분이 뒤집혔다(실측 '26.8.7 Reachy_Mini 건: 요구 8폭 열이 60%, 55폭 열이 40%).
# 대신 "한 열은 자기 내용이 1줄에 담기는 폭 이상을 필요로 하지 않는다"를 기준으로
# 삼는다 — 자기제한적이라 별도 상한이 필요 없고, 과점은 다른 열의 하한이 막는다.
#
#   need_j  = 요구 표시폭이 1줄에 담기는 폭
#   floor_j = max(헤더 표시폭, 8폭)이 담기는 폭   ← 짧은 라벨 열 뭉갬 방지
#   want_j  = max(need_j, floor_j)
#   여유분(sum(want) < total)은 want 비례로 나눠 열 비율을 유지하고,
#   부족분(sum(want) > total)은 want 비례로 줄이되 floor 아래로는 내리지 않는다.
#   합계는 표 sz와 정확히 일치시킨다(R036: 셀 폭 합 == 표 sz).
# ---------------------------------------------------------------------------

def _fit_width(units):
    """표시폭 units가 한 줄에 담기는 셀 폭(hu)."""
    return units * CHAR_HU / 2 + CELL_PAD


def column_widths(rows, total):
    ncol = len(rows[0])
    demand = [max((wlen(r[j]) if j < len(r) else 0) for r in rows) for j in range(ncol)]
    header = [wlen(rows[0][j]) if len(rows[0]) > j else 0 for j in range(ncol)]
    floor = [_fit_width(max(header[j], MIN_COL_UNITS)) for j in range(ncol)]
    want = [max(_fit_width(demand[j]), floor[j]) for j in range(ncol)]

    if sum(floor) >= total:                      # 하한조차 안 들어가는 극단 — 하한 비례 축소
        out = [int(total * f / sum(floor)) for f in floor]
    elif sum(want) <= total:                     # 전부 1줄에 들어감 — 여유분을 want 비례로
        out = [int(total * w / sum(want)) for w in want]
    else:                                        # 부족분 — want 비례 축소, floor에서 클램프
        fixed = {}
        for _ in range(ncol):
            free = [j for j in range(ncol) if j not in fixed]
            rest = total - sum(fixed.values())
            tot = sum(want[j] for j in free) or 1
            hit = [j for j in free if rest * want[j] / tot < floor[j]]
            if not hit:
                break
            for j in hit:
                fixed[j] = floor[j]
        free = [j for j in range(ncol) if j not in fixed]
        rest = total - sum(fixed.values())
        tot = sum(want[j] for j in free) or 1
        out = [0] * ncol
        for j, v in fixed.items():
            out[j] = int(v)
        for j in free:
            out[j] = int(rest * want[j] / tot)

    # 정수 반올림 잔차(수 hu)만 가장 넓은 열에 얹어 합계를 정확히 맞춘다
    out[out.index(max(out))] += total - sum(out)
    return out


def row_height(cells, widths):
    lines = 1
    for txt, w in zip(cells, widths):
        cap = max((w - CELL_PAD) / CHAR_HU * 2, 1)
        lines = max(lines, -(-wlen(txt) // cap) if wlen(txt) else 1)
    return H_ROW_BASE + H_ROW_LINE * (int(lines) - 1)


# ---------------------------------------------------------------------------
# 2층: 직렬화기 — 블록 → section0.xml
# ---------------------------------------------------------------------------

def runs(segs, cp, cp_bold):
    out = []
    for text, bold in segs:
        if not text:
            continue
        out.append(f'<hp:run charPrIDRef="{cp_bold if bold else cp}"><hp:t>{esc(text)}</hp:t></hp:run>')
    return "".join(out) or f'<hp:run charPrIDRef="{cp}"><hp:t></hp:t></hp:run>'


def para(pp, inner):
    return f'<hp:p paraPrIDRef="{pp}" styleIDRef="0">{inner}</hp:p>'


def cell(text, bf, w, h, r, c, bold=False):
    body = para(PP_CELL, runs(split_bold(text), CP_CELL, CP_CELL_B) if not bold
                else f'<hp:run charPrIDRef="{CP_CELL_B}"><hp:t>{esc(text)}</hp:t></hp:run>')
    return (f'<hp:tc name="" header="0" hasMargin="0" protect="0" editable="1" dirty="0" '
            f'borderFillIDRef="{bf}">'
            f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" '
            f'linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" '
            f'hasTextRef="0" hasNumRef="0">{body}</hp:subList>'
            f'<hp:cellAddr colAddr="{c}" rowAddr="{r}"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
            f'<hp:cellSz width="{w}" height="{h}"/>'
            f'<hp:cellMargin left="141" right="141" top="141" bottom="141"/></hp:tc>')


def tbl(tid, rowcnt, colcnt, width, height, body, bf=BF_CONTENT_TBL,
        outm=0, repeat=1, noadjust=None):
    na = f' noAdjust="{noadjust}"' if noadjust else ""
    return (f'<hp:tbl id="{tid}" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" '
            f'textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL" '
            f'repeatHeader="{repeat}" rowCnt="{rowcnt}" colCnt="{colcnt}" cellSpacing="0" '
            f'borderFillIDRef="{bf}"{na}>'
            f'<hp:sz width="{width}" widthRelTo="ABSOLUTE" height="{height}" '
            f'heightRelTo="ABSOLUTE" protect="0"/>'
            f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" '
            f'holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" '
            f'horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
            f'<hp:outMargin left="{outm}" right="{outm}" top="{outm}" bottom="{outm}"/>'
            f'<hp:inMargin left="510" right="510" top="141" bottom="141"/>'
            f'{body}</hp:tbl>')


def wrap(tbl_xml, pp=PP_TBL_WRAP):
    return para(pp, f'<hp:run charPrIDRef="{CP_BODY}">{tbl_xml}</hp:run>')


def render_title(text, tid):
    rows = []
    for i, (bf, h) in enumerate(zip(BF_TITLE_CELLS,
                                    (H_TITLE_PAD, H_TITLE_MAIN, H_TITLE_PAD))):
        if i == 1:
            body = para(PP_CELL, f'<hp:run charPrIDRef="{CP_TITLE}"><hp:t>{esc(text)}</hp:t></hp:run>')
        else:
            body = para(PP_TITLE_PAD, f'<hp:run charPrIDRef="{CP_TITLE_PAD}"><hp:t></hp:t></hp:run>')
        rows.append(
            f'<hp:tr><hp:tc name="" header="0" hasMargin="0" protect="0" editable="1" dirty="0" '
            f'borderFillIDRef="{bf}"><hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" '
            f'vertAlign="CENTER" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" '
            f'textHeight="0" hasTextRef="0" hasNumRef="0">{body}</hp:subList>'
            f'<hp:cellAddr colAddr="0" rowAddr="{i}"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
            f'<hp:cellSz width="{W_TITLE}" height="{h}"/>'
            f'<hp:cellMargin left="141" right="141" top="141" bottom="141"/></hp:tc></hp:tr>')
    h = H_TITLE_PAD * 2 + H_TITLE_MAIN
    return tbl(tid, 3, 1, W_TITLE, h, "".join(rows), bf=BF_TITLE_TBL,
               outm=OUTM_TITLE, repeat=0, noadjust="1")


def render_table(rows, tid):
    ncol = len(rows[0])
    nrow = len(rows)
    widths = column_widths(rows, W_CONTENT)
    trs, total_h = [], 0
    for i, row in enumerate(rows):
        h = row_height(row, widths)
        total_h += h
        if i == 0:
            bfs = BF_HEAD
        elif i == nrow - 1:
            bfs = BF_LAST
        elif i == 1:
            bfs = BF_FIRST
        else:
            bfs = BF_MID
        tcs = []
        for j, txt in enumerate(row):
            bf = bfs[0] if j == 0 else (bfs[2] if j == ncol - 1 else bfs[1])
            tcs.append(cell(txt, bf, widths[j], h, i, j, bold=(i == 0)))
        trs.append("<hp:tr>" + "".join(tcs) + "</hp:tr>")
    return wrap(tbl(tid, nrow, ncol, W_CONTENT, total_h, "".join(trs)))


def render_formula(text, tid):
    h = row_height([text], [W_CONTENT])
    tc = cell(text, BF_FORMULA, W_CONTENT, h, 0, 0, bold=True)
    return wrap(tbl(tid, 1, 1, W_CONTENT, h, f"<hp:tr>{tc}</hp:tr>"))


def render_banner(cells, tid):
    w = [W_BANNER_LABEL, W_BANNER_GAP, W_CONTENT - W_BANNER_LABEL - W_BANNER_GAP]
    h = H_ROW_BASE
    tcs = [cell(cells[j], BF_BANNER[j], w[j], h, 0, j, bold=(j == 0)) for j in range(3)]
    return wrap(tbl(tid, 1, 3, W_CONTENT, h, "<hp:tr>" + "".join(tcs) + "</hp:tr>"))


PARA_STYLE = {
    "sending": (PP_SENDING, CP_BODY, CP_BODY_B),
    "dae":     (PP_DAE, CP_DAE, CP_DAE),
    "yo":      (PP_YO, CP_BODY, CP_BODY_B),
    "dash":    (PP_DASH, CP_BODY, CP_BODY_B),
    "cham":    (PP_CHAM, CP_REF, CP_REF),
    "star":    (PP_CHAM, CP_REF, CP_REF),
    "arrow":   (PP_CHAM, CP_REF, CP_REF),
    "caption": (PP_PLAIN, CP_BODY, CP_BODY_B),
    "plain":   (PP_PLAIN, CP_BODY, CP_BODY_B),
}


def render(blocks):
    # secPr와 제목 박스는 **같은 문단**에 담는다 — 쪼개면 secPr 문단이 본문 15pt·
    # 줄간격 160%짜리 빈 줄로 렌더돼 제목표 위에 약 8.5mm 여백이 생긴다
    # (실측 '26.8.7 Reachy_Mini 건 — 정적 XML 검증은 전부 통과하므로 렌더로만 드러난다).
    secpr = (ASSETS / "secpr.xml").read_text(encoding="utf-8")
    head = [f'<hp:run charPrIDRef="{CP_BODY}">{secpr}</hp:run>']
    tid = 9300001
    title = next((b for b in blocks if b["t"] == "title"), None)
    if title is not None:
        head.append(f'<hp:run charPrIDRef="{CP_BODY}">{render_title(title["text"], tid)}</hp:run>')
        tid += 1
    out = [para(PP_PLAIN, "".join(head))]
    for b in blocks:
        t = b["t"]
        if t == "title":
            continue                      # 위 첫 문단에서 이미 처리했다
        elif t == "table":
            out.append(render_table(b["rows"], tid)); tid += 1
        elif t == "formula":
            out.append(render_formula(b["text"], tid)); tid += 1
        elif t == "banner":
            out.append(render_banner(b["cells"], tid)); tid += 1
        else:
            pp, cp, cpb = PARA_STYLE[t]
            out.append(para(pp, runs(b["segs"], cp, cpb)))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
            'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
            'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" '
            'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core">'
            + "".join(out) + '</hs:sec>')


# ---------------------------------------------------------------------------
# 3층: 패키저 — 정품 순서·압축 프로파일은 postprocess canonicalize_package 재사용
# ---------------------------------------------------------------------------

def package(section_xml, blocks, out_path):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    from postprocess_hwpx import canonicalize_package, _pkg_compress
    preview = "\n".join(
        re.sub(r"\*\*", "", "".join(s for s, _ in b.get("segs", [])) or b.get("text", ""))
        for b in blocks[:20] if b["t"] not in ("table", "banner"))[:800]
    data = {
        "mimetype": b"application/hwp+zip",
        "Contents/header.xml": (ASSETS / "kca-header.xml").read_bytes(),
        "Contents/section0.xml": section_xml.encode("utf-8"),
        "Contents/content.hpf": (ASSETS / "content.hpf.tmpl").read_bytes(),
        "META-INF/container.xml": (ASSETS / "container.xml").read_bytes(),
        "Preview/PrvText.txt": preview.encode("utf-8"),
    }
    names, summary = canonicalize_package(data)
    with zipfile.ZipFile(out_path, "w") as z:
        for n in names:
            z.writestr(zipfile.ZipInfo(n), data[n], compress_type=_pkg_compress(n))
    return summary


def main(argv):
    ap = argparse.ArgumentParser(description="md-profile 개조식 md → base.hwpx")
    ap.add_argument("src")
    ap.add_argument("-o", "--output", required=True)
    a = ap.parse_args(argv)
    try:
        blocks = parse(pathlib.Path(a.src).read_text(encoding="utf-8"))
        summary = package(render(blocks), blocks, a.output)
    except Md2HwpxError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2
    counts = {}
    for b in blocks:
        counts[b["t"]] = counts.get(b["t"], 0) + 1
    print(json.dumps({"output": a.output, "blocks": counts, "package": summary},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
