#!/usr/bin/env python3
"""표 열 폭을 셀 내용 표시폭에 비례해 재분배한다 — kordoc 균등 분할 보정.

generate_document(kordoc)는 GFM 표를 열 폭 균등 분할로 렌더한다(4열 = 11000×4).
이 스크립트는 build_from_template.py '직후'(inject_image.py 이전)에 실행되어,
본문 표의 열 폭을 내용 길이 비례로 결정론적으로 재분배한다.

규칙(SSOT: docs/superpowers/specs/2026-07-14-table-width-audience-proposal-design.md):
  - 표시폭: 한글·전각 2, ASCII 1. 열 가중치 = 열 내 셀 최대 표시폭(상한 5:1).
  - 하한: max(헤더 표시폭 환산, 전체 폭 8%) — 헤더 하한은 전체 40%로 캡.
  - 표 전체 폭 보존(행 합계 == <hp:sz width>, 정확 일치).
  - 제외: colCnt=1 / colSpan·rowSpan>1 / 첫 행 폭 비균등(참고양식·라벨박스).
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
