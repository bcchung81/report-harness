#!/usr/bin/env python3
"""표 열 폭을 셀 내용 표시폭에 비례해 재분배한다 — kordoc 균등 분할 보정.

generate_document(kordoc)는 GFM 표를 열 폭 균등 분할로 렌더한다(4열 = 11000×4).
이 스크립트는 build_from_template.py '직후'(inject_image.py 이전)에 실행되어,
본문 표의 열 폭을 내용 길이 비례로 결정론적으로 재분배한다.

규칙(SSOT: docs/superpowers/specs/2026-07-14-table-width-audience-proposal-design.md):
  - 표시폭: 한글·전각 2, ASCII 1. 열 가중치 = 열 내 셀 최대 표시폭(상한 5:1).
  - 하한: max(헤더 표시폭 환산, 전체 폭 8%) — 헤더 하한은 전체 40%로 캡.
  - 표 전체 폭 보존(행 합계 == <hp:sz width>, 정확 일치).
  - 제외: colCnt=1 / colSpan·rowSpan>1 / rowCnt=1(참고양식 제목표·붙임 라벨박스는 항상 단일행).
    ⚠️ 과거에는 "첫 행 폭 비균등"을 참고양식 판별 신호로 썼으나, kordoc generate_document가
    GFM 표를 내용비례 비균등폭으로 렌더하게 되면서(실측: 2026-07) 그 신호가 무효화됨 —
    데이터표까지 오판·제외. 라벨박스·제목표=항상 1행, 데이터표=헤더+데이터 ≥2행(실측 대조 확정).
  - 열 폭 재분배 시 행 높이도 새 열 폭 기준으로 재계산(kordoc이 협폭 열 기준으로 과대
    산정한 셀 높이 교정 — 미교정 시 빈 공간으로 표가 페이지를 벗어남).
  - 지시자: prep_report_md.py가 추출한 사이드카 JSON({본문표순번: [비율…]})을
    --widths로 받아 해당 표에 적용(하한은 보장). 형식 오류 시 자동 분배 폴백.

사용: python3 adjust_table_widths.py <in.hwpx> <out.hwpx> [--widths <table_widths.json>]
      (in == out 허용 — 전체를 메모리에 읽은 뒤 쓴다)
"""
import sys, re, json, zipfile

MIN_SHARE = 0.08     # 열 하한: 전체 폭의 8%
HEADER_CAP = 0.4     # 헤더 하한 캡: 전체 폭의 40%
MAX_RATIO = 5.0      # 열 가중치 최대:최소
CHAR_UNIT = 600      # 반각 1자 ≈ 6pt ≈ 600 HWPUNIT (표 내부 12pt 기준)
CELL_PAD = 800       # 셀 좌우 여백·여유 보정 (cellMargin 141×2 + 슬랙)
LINE_H = 1920        # 12pt 셀 텍스트 한 줄 높이 (실측: 1줄=2202, 2줄=4122, 3줄=6042)
ROW_PAD = 282        # 행 상하 여백 (실측 눈금의 절편)

# 한글 자모·CJK·한글 음절·호환 한자·전각 기호·CJK 기호 구간
_FULLWIDTH = re.compile(r'[ᄀ-ᇿ⺀-꓏가-힣'
                        r'豈-﫿︰-﹏＀-｠　-〿]')


def display_width(text):
    return sum(2 if _FULLWIDTH.match(ch) else 1 for ch in text)


def compute_widths(col_texts, total, ratios=None):
    """열별 폭 계산. col_texts[i] = i열 셀 텍스트 목록(첫 원소=헤더). 합계 == total."""
    n = len(col_texts)
    if ratios is not None and (len(ratios) != n or any(r <= 0 for r in ratios)):
        ratios = None                                   # 형식 오류 → 자동 폴백
    if ratios is not None:
        weights = [float(r) for r in ratios]
    else:
        weights = [float(max(max((display_width(t) for t in texts), default=1), 1))
                   for texts in col_texts]
        wmin = min(weights)
        weights = [min(w, wmin * MAX_RATIO) for w in weights]   # 상한 5:1
    floors = []
    for texts in col_texts:
        header_w = display_width(texts[0]) if texts else 0
        floor = max(int(total * MIN_SHARE), header_w * CHAR_UNIT + CELL_PAD)
        floors.append(min(floor, int(total * HEADER_CAP)))
    if sum(floors) >= total:                            # 극단(열 과다·헤더 과장) → 균등 폴백
        base = total // n
        widths = [base] * n
        widths[-1] += total - base * n
        return widths
    rem = total - sum(floors)
    wsum = sum(weights)
    widths = [floors[i] + int(rem * weights[i] / wsum) for i in range(n)]
    widths[-1] += total - sum(widths)                   # 반올림 보정(합계 정확 일치)
    return widths


_TBL = re.compile(r'<hp:tbl\b[^>]*>.*?</hp:tbl>', re.S)
_TC = re.compile(r'<hp:tc\b.*?</hp:tc>', re.S)
_T = re.compile(r'<hp:t>(.*?)</hp:t>', re.S)
_CELLSZ = re.compile(r'(<hp:cellSz width=")(\d+)(")')
_CELLSZ_H = re.compile(r'(<hp:cellSz width="\d+" height=")(\d+)(")')


def _cell_info(tc_xml):
    col = int(re.search(r'colAddr="(\d+)"', tc_xml).group(1))
    row = int(re.search(r'rowAddr="(\d+)"', tc_xml).group(1))
    span = re.search(r'colSpan="(\d+)" rowSpan="(\d+)"', tc_xml)
    spanned = span and (int(span.group(1)) > 1 or int(span.group(2)) > 1)
    width = int(re.search(r'<hp:cellSz width="(\d+)"', tc_xml).group(1))
    paras = re.findall(r'<hp:p\b.*?</hp:p>', tc_xml, re.S)
    lines = [''.join(_T.findall(p)) for p in paras] or ['']
    text = max(lines, key=display_width)        # 폭 가중치는 최장 행 기준
    para_widths = [display_width(l) for l in lines]   # 높이 추정은 문단별 줄바꿈 합산
    return col, row, bool(spanned), width, text, para_widths


def _row_heights(cells, new_w):
    """새 열 폭 기준으로 행별 높이 재계산(kordoc의 협폭 기준 과대 산정 교정).

    HWPX 셀 높이는 최소 높이로 동작 — 추정이 짧으면 한글이 자동 확장하므로 안전.
    """
    rows = {}
    for col, row, _, _, _, para_widths in cells:
        rows.setdefault(row, []).append((col, para_widths))
    heights = {}
    for row, items in rows.items():
        max_lines = 1
        for col, pws in items:
            avail = max(new_w[col] - CELL_PAD, CHAR_UNIT)
            cell_lines = sum(max(1, -(-pw * CHAR_UNIT // avail)) for pw in pws) or 1
            max_lines = max(max_lines, cell_lines)
        heights[row] = ROW_PAD + LINE_H * max_lines
    return heights


def redistribute_section(xml, widths_map, start_index=0):
    """section XML의 조정 후보 표(colCnt≥2·span 없음·첫 행 균등폭)를 재분배.
    widths_map: {본문 표 순번(0-based, 후보만 계수): [비율…]}.
    반환: (수정 XML, 조정 표 수, 다음 순번)."""
    idx = start_index
    adjusted = 0

    def repl(m):
        nonlocal idx, adjusted
        tbl = m.group(0)
        head = re.match(r'<hp:tbl\b[^>]*>', tbl).group(0)
        colcnt = int(re.search(r'colCnt="(\d+)"', head).group(1))
        rowcnt = int(re.search(r'rowCnt="(\d+)"', head).group(1))
        if colcnt < 2 or rowcnt < 2:        # 라벨박스·제목표(항상 1행)·단일열 제외
            return tbl
        cells = [_cell_info(tc) for tc in _TC.findall(tbl)]
        if not cells or any(c[2] for c in cells):                   # span 있는 표 제외
            return tbl
        row0 = sorted(c for c in cells if c[1] == 0)
        if len(row0) != colcnt:                                     # 구조 이상 → 안전 제외
            return tbl
        total = sum(c[3] for c in row0)
        col_texts = [[] for _ in range(colcnt)]
        for col, row, _, _, text, _ in sorted(cells, key=lambda c: (c[1], c[0])):
            if col < colcnt:
                col_texts[col].append(text)
        new_w = compute_widths(col_texts, total, ratios=widths_map.get(idx))
        new_h = _row_heights(cells, new_w)
        idx += 1
        adjusted += 1

        def cell_repl(tm):
            tc = tm.group(0)
            col = int(re.search(r'colAddr="(\d+)"', tc).group(1))
            row = int(re.search(r'rowAddr="(\d+)"', tc).group(1))
            tc = _CELLSZ_H.sub(lambda s: s.group(1) + str(new_h[row]) + s.group(3), tc)
            return _CELLSZ.sub(lambda s: s.group(1) + str(new_w[col]) + s.group(3), tc)
        out = _TC.sub(cell_repl, tbl)
        # 표 자체 높이도 행 합계로 동기화(스테일 방지)
        return re.sub(r'(<hp:sz width="\d+"[^>]*height=")(\d+)(")',
                      lambda s: s.group(1) + str(sum(new_h.values())) + s.group(3),
                      out, count=1)

    return _TBL.sub(repl, xml), adjusted, idx


def process(src, dst, widths_map):
    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        data = {n: zin.read(n) for n in names}
    adjusted, idx = 0, 0
    for n in sorted(n for n in names if re.match(r'Contents/section\d+\.xml$', n)):
        xml, a, idx = redistribute_section(data[n].decode("utf-8"), widths_map, idx)
        data[n] = xml.encode("utf-8")
        adjusted += a
    with zipfile.ZipFile(dst, "w") as zout:
        for n in names:
            comp = zipfile.ZIP_STORED if n == "mimetype" else zipfile.ZIP_DEFLATED
            zout.writestr(zipfile.ZipInfo(n), data[n], compress_type=comp)
    return adjusted


def main():
    argv = sys.argv[1:]
    wpath = None
    if "--widths" in argv:
        i = argv.index("--widths")
        if i + 1 >= len(argv):
            sys.exit("usage: adjust_table_widths.py <in.hwpx> <out.hwpx> [--widths <json>]")
        wpath = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if len(argv) != 2:
        sys.exit("usage: adjust_table_widths.py <in.hwpx> <out.hwpx> [--widths <json>]")
    widths_map = {}
    if wpath:
        try:
            raw = json.load(open(wpath, encoding="utf-8"))
            widths_map = {int(k): v for k, v in raw.items()}
        except (OSError, ValueError) as e:
            print(f"  ⚠️  지시자 파일 무시({wpath}): {e} — 자동 분배로 폴백")
    n = process(argv[0], argv[1], widths_map)
    print(f"OK: {argv[1]}")
    print(f"  열 폭 재분배: {n}개 표 (지시자 {len(widths_map)}건)")


if __name__ == "__main__":
    main()
