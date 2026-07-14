# 표 열 폭 유동 분배 · 보고 대상 프로파일 · 총괄표 제안 Q&A — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** kordoc이 균등 분할하는 표 열 폭을 셀 내용 비례로 자동 재분배하고, 보고 대상(임원/경영진/부서장·실무) 프로파일과 총괄표·부연자료 2단계 제안 Q&A를 하네스에 도입한다.

**Architecture:** 신규 `adjust_table_widths.py`(결정론적 후처리, builder 파이프라인의 build_from_template 직후)가 폭 재분배를 담당. `prep_report_md.py`가 `[ 캡션 | 폭 2:1:1:3 ]` 지시자를 사이드카 JSON으로 추출. `validate_hwpx.py`에 행 폭 합계 불변식 추가(기존 PostToolUse 훅이 자동 검사). 프로파일·Q&A는 스킬/에이전트 마크다운 편집(layout §9, lint L21, orchestrator Phase 0·1 게이트).

**Tech Stack:** Python 3 표준 라이브러리만(re·zipfile·json·unittest). XML은 기존 코드베이스 관례대로 정규식 처리(ET 파싱 아님).

**Spec:** `docs/superpowers/specs/2026-07-14-table-width-audience-proposal-design.md`

## Global Constraints

- Python 3 stdlib only — 외부 패키지 금지 (기존 scripts 관례).
- 결정론 — 랜덤·시간 의존 없음. 같은 입력 → 같은 출력.
- 표 전체 폭 보존 — 재분배 후 각 행의 cellSz 합 == 원래 표 폭(`<hp:sz width>`), 정확 일치.
- HWPX zip 재작성 시 `mimetype`은 무압축(ZIP_STORED) + 원래 엔트리 순서 유지.
- 자동 분배 파라미터(스펙 값 그대로): 하한 = max(헤더 표시폭 환산, 전체 폭의 8%), 헤더 하한 캡 40%, 가중치 상한 5:1, 표시폭 = 한글·전각 2 / ASCII 1.
- 제외 대상: colCnt=1 표, colSpan/rowSpan>1 있는 표, 첫 행 폭이 균등하지 않은 표(참고양식·라벨박스). **본문 표 순번은 조정 후보(균등폭 표)만 센다** — MD의 GFM 표 순서와 1:1.
- SSOT 규율: 임계값·방법은 `kca-report-layout`에만 쓰고 lint·에이전트는 참조만.
- 에이전트 런타임은 `~/.claude/skills`·`~/.claude/agents` **사본**을 읽는다 — 저장소 수정 후 반드시 동기화(Task 7).
- 커밋 메시지는 기존 저장소 관례(한국어 요약 한 줄) + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- 테스트 실행: `python3 -m unittest discover -s tests -v` (저장소 루트에서).

---

### Task 1: adjust_table_widths.py — 폭 계산 코어 (display_width·compute_widths)

**Files:**
- Create: `skills/kca-report-style/scripts/adjust_table_widths.py`
- Test: `tests/test_adjust_table_widths.py`

**Interfaces:**
- Produces: `display_width(text: str) -> int` (한글·전각 2, 그 외 1), `compute_widths(col_texts: list[list[str]], total: int, ratios: list[float]|None = None) -> list[int]` — col_texts는 열별 셀 텍스트 목록(첫 원소 = 헤더 행), 반환 합계 == total. Task 2가 이 두 함수를 사용.

- [ ] **Step 1: 테스트 작성**

`tests/test_adjust_table_widths.py`:

```python
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/kca-report-style/scripts"))
from adjust_table_widths import display_width, compute_widths


class TestDisplayWidth(unittest.TestCase):
    def test_hangul_is_2_ascii_is_1(self):
        self.assertEqual(display_width("가나다"), 6)
        self.assertEqual(display_width("ABC12"), 5)
        self.assertEqual(display_width("가A"), 3)
        self.assertEqual(display_width(""), 0)


class TestComputeWidths(unittest.TestCase):
    def test_uniform_content_stays_equal(self):
        cols = [["구분", "가나"], ["구분", "다라"], ["구분", "마바"], ["구분", "사아"]]
        w = compute_widths(cols, 44000)
        self.assertEqual(sum(w), 44000)
        self.assertEqual(len(set(w)), 1)

    def test_long_column_gets_wider(self):
        cols = [["사", "A"], ["구분", "나다"], ["특징", "라마"],
                ["시사점", "공공기관 대민서비스 자동화·문서 검증에 적합한 구조"]]
        w = compute_widths(cols, 44000)
        self.assertEqual(sum(w), 44000)
        self.assertEqual(max(w), w[3])
        self.assertGreater(w[3], w[0])

    def test_floor_8_percent(self):
        cols = [["", ""], ["구분", "아주아주아주아주 긴 내용의 셀 텍스트가 계속 이어지는 경우"]]
        w = compute_widths(cols, 44000)
        self.assertEqual(sum(w), 44000)
        self.assertGreaterEqual(w[0], int(44000 * 0.08))

    def test_ratios_override(self):
        cols = [["같음", "같음"], ["같음", "같음"], ["같음", "같음"], ["같음", "같음"]]
        w = compute_widths(cols, 44000, ratios=[2, 1, 1, 3])
        self.assertEqual(sum(w), 44000)
        self.assertGreater(w[0], w[1])
        self.assertGreater(w[3], w[0])

    def test_bad_ratios_fall_back_to_auto(self):
        cols = [["가", "가"], ["나", "나"]]
        self.assertEqual(compute_widths(cols, 20000, ratios=[1, 2, 3]),
                         compute_widths(cols, 20000))          # 개수 불일치
        self.assertEqual(compute_widths(cols, 20000, ratios=[0, 1]),
                         compute_widths(cols, 20000))          # 0 비율


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m unittest tests.test_adjust_table_widths -v`
Expected: FAIL (`ModuleNotFoundError: adjust_table_widths`)

- [ ] **Step 3: 구현**

`skills/kca-report-style/scripts/adjust_table_widths.py`:

```python
#!/usr/bin/env python3
"""표 열 폭을 셀 내용 표시폭에 비례해 재분배한다 — kordoc 균등 분할 보정.

generate_document(kordoc)는 GFM 표를 열 폭 균등 분할로 렌더한다(4열 = 11000×4).
이 스크립트는 build_from_template.py '직후'(inject_image.py 이전)에 실행되어,
본문 표의 열 폭을 내용 길이 비례로 결정론적으로 재분배한다.

규칙(SSOT: docs/superpowers/specs/2026-07-14-…-design.md):
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

_FULLWIDTH = re.compile(r'[ᄀ-ᇿ⺀-꓏가-힣豈-﫿'
                        r'︰-﹏＀-｠　-〿]')


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
```

주의: `header_w * CHAR_UNIT`에서 `display_width`는 전각을 이미 2로 세므로 반각 단위 600을 곱하면 전각 12pt(1200 HWPUNIT)가 맞게 나온다.

- [ ] **Step 4: 통과 확인**

Run: `python3 -m unittest tests.test_adjust_table_widths -v`
Expected: PASS (6 tests)

- [ ] **Step 5: 커밋**

```bash
git add skills/kca-report-style/scripts/adjust_table_widths.py tests/test_adjust_table_widths.py
git commit -m "표 열 폭 계산 코어 — display_width·compute_widths (하한 8%·상한 5:1·합계 보존)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: adjust_table_widths.py — section XML 재분배 (redistribute_section)

**Files:**
- Modify: `skills/kca-report-style/scripts/adjust_table_widths.py`
- Test: `tests/test_adjust_table_widths.py` (추가)

**Interfaces:**
- Consumes: Task 1의 `display_width`, `compute_widths`.
- Produces: `redistribute_section(xml: str, widths_map: dict[int, list[float]], start_index: int = 0) -> tuple[str, int, int]` — (수정된 XML, 조정한 표 수, 다음 본문 표 순번). Task 3의 CLI가 사용.

- [ ] **Step 1: 테스트 추가**

`tests/test_adjust_table_widths.py`에 추가 (import 줄에 `redistribute_section` 추가):

```python
from adjust_table_widths import redistribute_section


def _tc(col, width, text, span=1):
    return (f'<hp:tc name="" header="0" borderFillIDRef="45">'
            f'<hp:subList vertAlign="CENTER"><hp:p paraPrIDRef="91" styleIDRef="0">'
            f'<hp:run charPrIDRef="135"><hp:t>{text}</hp:t></hp:run></hp:p></hp:subList>'
            f'<hp:cellAddr colAddr="{col}" rowAddr="0" />'
            f'<hp:cellSpan colSpan="{span}" rowSpan="1" />'
            f'<hp:cellSz width="{width}" height="1500" />'
            f'<hp:cellMargin left="141" right="141" top="141" bottom="141" /></hp:tc>')


def _tbl(colcnt, cells, total):
    return (f'<hp:tbl id="1025" rowCnt="1" colCnt="{colcnt}" borderFillIDRef="4">'
            f'<hp:sz width="{total}" widthRelTo="ABSOLUTE" height="1500" />'
            f'<hp:tr>{cells}</hp:tr></hp:tbl>')


class TestRedistributeSection(unittest.TestCase):
    def test_uniform_body_table_adjusted(self):
        xml = _tbl(2, _tc(0, 11000, "가") + _tc(1, 11000, "아주 길고 긴 설명 텍스트"), 22000)
        out, n, nxt = redistribute_section(xml, {})
        self.assertEqual(n, 1)
        self.assertEqual(nxt, 1)
        ws = [int(x) for x in __import__("re").findall(r'<hp:cellSz width="(\d+)"', out)]
        self.assertEqual(sum(ws), 22000)
        self.assertGreater(ws[1], ws[0])

    def test_nonuniform_and_spanned_tables_skipped(self):
        label = _tbl(3, _tc(0, 5968, "붙임 1") + _tc(1, 565, "") + _tc(2, 41626, "제목"), 48159)
        spanned = _tbl(2, _tc(0, 11000, "가", span=2) + _tc(1, 11000, "나"), 22000)
        out, n, _ = redistribute_section(label + spanned, {})
        self.assertEqual(n, 0)
        self.assertEqual(out, label + spanned)      # 원문 그대로

    def test_widths_map_applies_by_body_table_order(self):
        t0 = _tbl(2, _tc(0, 11000, "같음") + _tc(1, 11000, "같음"), 22000)
        label = _tbl(3, _tc(0, 5968, "붙임 1") + _tc(1, 565, "") + _tc(2, 41626, "제목"), 48159)
        t1 = _tbl(2, _tc(0, 11000, "같음") + _tc(1, 11000, "같음"), 22000)
        out, n, _ = redistribute_section(t0 + label + t1, {1: [1, 3]})
        self.assertEqual(n, 2)
        ws = [int(x) for x in __import__("re").findall(r'<hp:cellSz width="(\d+)"', out)]
        # t0(자동, 내용 동일) 균등 / label 불변 / t1(지시자 1:3) 뒤 열이 넓음
        self.assertEqual(ws[0], ws[1])
        self.assertEqual(ws[2:5], [5968, 565, 41626])
        self.assertGreater(ws[6], ws[5])

    def test_single_col_skipped(self):
        xml = _tbl(1, _tc(0, 50624, "제목"), 50624)
        out, n, _ = redistribute_section(xml, {})
        self.assertEqual(n, 0)
        self.assertEqual(out, xml)
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m unittest tests.test_adjust_table_widths -v`
Expected: FAIL (`ImportError: redistribute_section`)

- [ ] **Step 3: 구현**

`adjust_table_widths.py`의 `compute_widths` 아래에 추가:

```python
_TBL = re.compile(r'<hp:tbl\b[^>]*>.*?</hp:tbl>', re.S)
_TC = re.compile(r'<hp:tc\b.*?</hp:tc>', re.S)
_T = re.compile(r'<hp:t>(.*?)</hp:t>', re.S)
_CELLSZ = re.compile(r'(<hp:cellSz width=")(\d+)(")')


def _cell_info(tc_xml):
    col = int(re.search(r'colAddr="(\d+)"', tc_xml).group(1))
    row = int(re.search(r'rowAddr="(\d+)"', tc_xml).group(1))
    span = re.search(r'colSpan="(\d+)" rowSpan="(\d+)"', tc_xml)
    spanned = span and (int(span.group(1)) > 1 or int(span.group(2)) > 1)
    width = int(re.search(r'<hp:cellSz width="(\d+)"', tc_xml).group(1))
    paras = re.findall(r'<hp:p\b.*?</hp:p>', tc_xml, re.S)
    lines = [''.join(_T.findall(p)) for p in paras] or ['']
    text = max(lines, key=display_width)        # 다행 셀은 최장 행 기준
    return col, row, bool(spanned), width, text


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
        if colcnt < 2:
            return tbl
        cells = [_cell_info(tc) for tc in _TC.findall(tbl)]
        if not cells or any(c[2] for c in cells):                   # span 있는 표 제외
            return tbl
        row0 = sorted([c for c in cells if c[1] == 0])
        if len(row0) != colcnt or len({c[3] for c in row0}) != 1:   # 첫 행 비균등 → 참고양식
            return tbl
        total = sum(c[3] for c in row0)
        col_texts = [[] for _ in range(colcnt)]
        for col, row, _, _, text in sorted(cells, key=lambda c: (c[1], c[0])):
            if col < colcnt:
                col_texts[col].append(text)
        new_w = compute_widths(col_texts, total, ratios=widths_map.get(idx))
        idx += 1
        adjusted += 1

        def cell_repl(tm):
            col = int(re.search(r'colAddr="(\d+)"', tm.group(0)).group(1))
            return _CELLSZ.sub(lambda s: s.group(1) + str(new_w[col]) + s.group(3),
                               tm.group(0))
        return _TC.sub(cell_repl, tbl)

    return _TBL.sub(repl, xml), adjusted, idx
```

- [ ] **Step 4: 통과 확인**

Run: `python3 -m unittest tests.test_adjust_table_widths -v`
Expected: PASS (10 tests)

- [ ] **Step 5: 커밋**

```bash
git add skills/kca-report-style/scripts/adjust_table_widths.py tests/test_adjust_table_widths.py
git commit -m "표 열 폭 재분배 — section XML 처리(제외 시그니처·지시자 순번 매핑)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: adjust_table_widths.py — CLI·zip 처리 + 실파일 스모크

**Files:**
- Modify: `skills/kca-report-style/scripts/adjust_table_widths.py`
- Test: `tests/test_adjust_table_widths.py` (추가)

**Interfaces:**
- Consumes: Task 2의 `redistribute_section`.
- Produces: CLI `python3 adjust_table_widths.py <in.hwpx> <out.hwpx> [--widths <json>]` — builder가 호출. 내부 함수 `process(src, dst, widths_map) -> int`(조정 표 수).

- [ ] **Step 1: 테스트 추가**

`tests/test_adjust_table_widths.py`에 추가 (파일 상단 import에 `import io, json, re, zipfile, tempfile, os` 및 `from adjust_table_widths import process` 추가):

```python
class TestProcessZip(unittest.TestCase):
    def _make_hwpx(self, path, section_xml):
        with zipfile.ZipFile(path, "w") as z:
            z.writestr(zipfile.ZipInfo("mimetype"), b"application/hwp+zip",
                       compress_type=zipfile.ZIP_STORED)
            z.writestr("Contents/header.xml", "<hh:head></hh:head>")
            z.writestr("Contents/section0.xml", section_xml)

    def test_roundtrip_preserves_mimetype_and_adjusts(self):
        xml = _tbl(2, _tc(0, 11000, "가") + _tc(1, 11000, "아주 길고 긴 설명 텍스트"), 22000)
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "in.hwpx"), os.path.join(d, "out.hwpx")
            self._make_hwpx(src, xml)
            n = process(src, dst, {})
            self.assertEqual(n, 1)
            with zipfile.ZipFile(dst) as z:
                self.assertEqual(z.namelist()[0], "mimetype")
                self.assertEqual(z.getinfo("mimetype").compress_type, zipfile.ZIP_STORED)
                out = z.read("Contents/section0.xml").decode("utf-8")
            ws = [int(x) for x in re.findall(r'<hp:cellSz width="(\d+)"', out)]
            self.assertEqual(sum(ws), 22000)
            self.assertGreater(ws[1], ws[0])

    def test_in_place_same_path(self):
        xml = _tbl(2, _tc(0, 11000, "가") + _tc(1, 11000, "아주 길고 긴 설명 텍스트"), 22000)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "same.hwpx")
            self._make_hwpx(p, xml)
            self.assertEqual(process(p, p, {}), 1)
            with zipfile.ZipFile(p) as z:
                z.testzip()
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m unittest tests.test_adjust_table_widths -v`
Expected: FAIL (`ImportError: process`)

- [ ] **Step 3: 구현**

`adjust_table_widths.py` 끝에 추가:

```python
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
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 2:
        sys.exit("usage: adjust_table_widths.py <in.hwpx> <out.hwpx> [--widths <json>]")
    widths_map = {}
    if "--widths" in sys.argv:
        wpath = sys.argv[sys.argv.index("--widths") + 1]
        try:
            raw = json.load(open(wpath, encoding="utf-8"))
            widths_map = {int(k): v for k, v in raw.items()}
        except (OSError, ValueError) as e:
            print(f"  ⚠️  지시자 파일 무시({wpath}): {e} — 자동 분배로 폴백")
    n = process(args[0], args[1], widths_map)
    print(f"OK: {args[1]}")
    print(f"  열 폭 재분배: {n}개 표 (지시자 {len(widths_map)}건)")


if __name__ == "__main__":
    main()
```

주의: `main()`의 `args` 필터가 `--widths`의 값(json 경로)을 위치 인자로 오인하지 않도록, json 경로 인자는 `--widths` 바로 뒤에 온다는 규약을 사용한다. 구현 시 `args`에서 widths 경로를 제거하는 코드가 필요하다:

```python
    argv = sys.argv[1:]
    if "--widths" in argv:
        i = argv.index("--widths")
        wpath = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    else:
        wpath = None
    if len(argv) != 2:
        sys.exit("usage: adjust_table_widths.py <in.hwpx> <out.hwpx> [--widths <json>]")
```

(위 형태로 `main()`을 작성한다 — `args` 필터 방식 대신 이 방식을 사용.)

- [ ] **Step 4: 통과 확인**

Run: `python3 -m unittest tests.test_adjust_table_widths -v`
Expected: PASS (12 tests)

- [ ] **Step 5: 실파일 스모크 (수동 검증)**

```bash
cp "/Users/bcchung81/workspace/works/대형LLM-동향-공공기관시사점.hwpx" /tmp_smoke.hwpx 2>/dev/null || \
  cp "/Users/bcchung81/workspace/works/대형LLM-동향-공공기관시사점.hwpx" "$TMPDIR/smoke_in.hwpx"
python3 skills/kca-report-style/scripts/adjust_table_widths.py "$TMPDIR/smoke_in.hwpx" "$TMPDIR/smoke_out.hwpx"
python3 skills/kca-report-style/scripts/validate_hwpx.py "$TMPDIR/smoke_out.hwpx"
python3 - "$TMPDIR/smoke_out.hwpx" <<'EOF'
import sys, re, zipfile
xml = zipfile.ZipFile(sys.argv[1]).read("Contents/section0.xml").decode("utf-8")
for m in re.finditer(r'<hp:tbl\b[^>]*colCnt="4"[^>]*>.*?</hp:tbl>', xml, re.S):
    print(re.findall(r'<hp:cellSz width="(\d+)"', m.group(0))[:4])
EOF
```

Expected: validate 통과, 4열 표의 폭이 11000×4가 아닌 내용 비례 값(합계 44000)으로 출력.

- [ ] **Step 6: 커밋**

```bash
git add skills/kca-report-style/scripts/adjust_table_widths.py tests/test_adjust_table_widths.py
git commit -m "표 열 폭 재분배 CLI — zip 왕복(mimetype STORED)·in-place 지원·실파일 검증

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: prep_report_md.py — 폭 지시자 추출

**Files:**
- Modify: `skills/kca-report-style/scripts/prep_report_md.py`
- Test: `tests/test_prep_report_md.py`

**Interfaces:**
- Consumes: 없음(독립).
- Produces: `extract_widths(md: str) -> tuple[str, dict[int, list[float]]]` — 지시자 제거된 MD + {GFM 표 순번(0-based): 비율}. CLI 3번째 위치 인자(선택) `<widths.json>` — 지시자가 1건 이상일 때만 파일 생성. builder가 `prep_report_md.py <draft.md> <prepared.md> _workspace/table_widths.json`으로 호출.

- [ ] **Step 1: 테스트 작성**

`tests/test_prep_report_md.py`:

```python
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/kca-report-style/scripts"))
from prep_report_md import extract_widths, prep

MD = """- 추진 배경
  - (동향) 대형 LLM 확산

[ 모델 비교 | 폭 2:1:1:3 ]
| 개발사 | 모델 | 특징 | 시사점 |
|---|---|---|---|
| A | B | C | D |

[ 일정 총괄 ]
| 단계 | 시점 |
|---|---|
| 착수 | '26.8월 |
"""


class TestExtractWidths(unittest.TestCase):
    def test_directive_extracted_and_caption_cleaned(self):
        out, widths = extract_widths(MD)
        self.assertIn("[ 모델 비교 ]", out)
        self.assertNotIn("| 폭", out)
        self.assertIn("[ 일정 총괄 ]", out)           # 지시자 없는 캡션 불변
        self.assertEqual(widths, {0: [2.0, 1.0, 1.0, 3.0]})

    def test_no_directive_returns_empty(self):
        out, widths = extract_widths("본문\n\n| a | b |\n|---|---|\n")
        self.assertEqual(widths, {})

    def test_bad_ratio_ignored(self):
        md = "[ 캡션 | 폭 2:x:1 ]\n| a | b | c |\n|---|---|---|\n"
        out, widths = extract_widths(md)
        self.assertEqual(widths, {})
        self.assertIn("[ 캡션 ]", out)                # 캡션은 정리

    def test_prep_still_converts_footnote(self):
        self.assertIn("＊ 용어: 정의", prep("* 용어: 정의"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m unittest tests.test_prep_report_md -v`
Expected: FAIL (`ImportError: extract_widths`)

- [ ] **Step 3: 구현**

`prep_report_md.py`의 `prep()` 아래에 추가하고, docstring 처리 목록에 `3) 표 폭 지시자 [ 캡션 | 폭 2:1:1:3 ] → 캡션 정리 + 사이드카 JSON` 한 줄을 추가한다:

```python
_DIRECTIVE = re.compile(r'^\[\s*(.+?)\s*\|\s*폭\s*([\d.:\s]+?)\s*\]\s*$')


def extract_widths(md):
    """[ 캡션 | 폭 2:1:1:3 ] 지시자를 캡션에서 제거하고 {표순번: [비율]}을 수집.
    표 순번은 GFM 표(| 로 시작하는 연속 블록) 등장 순서, 0-based."""
    lines, widths = [], {}
    pending, tbl_idx, in_tbl = None, -1, False
    for ln in md.split("\n"):
        m = _DIRECTIVE.match(ln)
        if m:
            try:
                pending = [float(x) for x in m.group(2).split(":")]
            except ValueError:
                pending = None                      # 비율 형식 오류 → 지시자 무시
            lines.append(f"[ {m.group(1)} ]")
            continue
        is_tbl = ln.lstrip().startswith("|")
        if is_tbl and not in_tbl:
            tbl_idx += 1
            if pending:
                widths[tbl_idx] = pending
                pending = None
        in_tbl = is_tbl
        lines.append(ln)
    return "\n".join(lines), widths
```

`main()`을 다음으로 교체:

```python
def main():
    if len(sys.argv) not in (3, 4):
        sys.exit("usage: prep_report_md.py <in.md> <out.md> [<widths.json>]")
    src, dst = sys.argv[1], sys.argv[2]
    md = open(src, encoding="utf-8").read()
    n_before = len(re.findall(r'(?m)^\* (?=.+?: )', md))
    out, widths = extract_widths(prep(md))
    open(dst, "w", encoding="utf-8").write(out)
    n_marker = len(re.findall(r'\[도해:', out))
    print(f"OK: {dst}")
    print(f"  각주 정의 ＊ 치환: {n_before}건 / 도해 마커 보존: {n_marker}건")
    if len(sys.argv) == 4 and widths:
        import json
        json.dump({str(k): v for k, v in widths.items()},
                  open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False)
        print(f"  표 폭 지시자: {len(widths)}건 → {sys.argv[3]}")
    elif widths:
        print(f"  ⚠️  표 폭 지시자 {len(widths)}건 발견했으나 widths.json 경로 미지정 — 무시됨")
```

(`import json`은 파일 상단 `import sys, re` 줄에 합쳐 `import sys, re, json`으로 두어도 된다.)

- [ ] **Step 4: 통과 확인**

Run: `python3 -m unittest tests.test_prep_report_md -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 커밋**

```bash
git add skills/kca-report-style/scripts/prep_report_md.py tests/test_prep_report_md.py
git commit -m "prep_report_md — 표 폭 지시자 [캡션|폭 n:n] 추출→사이드카 JSON·캡션 정리

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: validate_hwpx.py — 표 행 폭 합계 불변식

**Files:**
- Modify: `skills/kca-report-style/scripts/validate_hwpx.py`
- Test: `tests/test_validate_hwpx_widths.py`

**Interfaces:**
- Consumes: 없음(독립).
- Produces: `check_table_widths(section: str, errs: list) -> None` — span 없는 표의 모든 행에 대해 cellSz 합 == `<hp:sz width>`(±2) 검사. `main()`의 section 루프에서 `check_idrefs` 옆에 호출. 기존 PostToolUse 훅(`hooks/validate_hwpx_hook.py`)은 이 스크립트를 그대로 실행하므로 자동 편입.

- [ ] **Step 1: 테스트 작성**

`tests/test_validate_hwpx_widths.py`:

```python
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/kca-report-style/scripts"))
from validate_hwpx import check_table_widths

GOOD = ('<hp:tbl id="1" rowCnt="1" colCnt="2"><hp:sz width="22000" height="1" />'
        '<hp:tr><hp:tc><hp:cellAddr colAddr="0" rowAddr="0" />'
        '<hp:cellSpan colSpan="1" rowSpan="1" /><hp:cellSz width="8000" height="1" /></hp:tc>'
        '<hp:tc><hp:cellAddr colAddr="1" rowAddr="0" />'
        '<hp:cellSpan colSpan="1" rowSpan="1" /><hp:cellSz width="14000" height="1" /></hp:tc>'
        '</hp:tr></hp:tbl>')
BAD = GOOD.replace('width="14000"', 'width="9999"')
SPANNED = GOOD.replace('colSpan="1" rowSpan="1" /><hp:cellSz width="8000"',
                       'colSpan="2" rowSpan="1" /><hp:cellSz width="8000"')


class TestCheckTableWidths(unittest.TestCase):
    def test_good_table_passes(self):
        errs = []
        check_table_widths(GOOD, errs)
        self.assertEqual(errs, [])

    def test_mismatch_reported(self):
        errs = []
        check_table_widths(BAD, errs)
        self.assertEqual(len(errs), 1)
        self.assertIn("행 폭 합", errs[0])

    def test_spanned_table_skipped(self):
        errs = []
        check_table_widths(SPANNED, errs)      # span 표는 검사 대상 아님
        self.assertEqual(errs, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 실패 확인**

Run: `python3 -m unittest tests.test_validate_hwpx_widths -v`
Expected: FAIL (`ImportError: check_table_widths`)

- [ ] **Step 3: 구현**

`validate_hwpx.py`의 `check_idrefs` 아래에 추가:

```python
def check_table_widths(section, errs):
    """span 없는 표: 각 행의 cellSz 합 == 표 폭(±2). 열 폭 재분배 회귀 방어."""
    for tm in re.finditer(r'<hp:tbl\b[^>]*>.*?</hp:tbl>', section, re.S):
        tbl = tm.group(0)
        if re.search(r'(?:colSpan|rowSpan)="(?:[2-9]|\d{2,})"', tbl):
            continue
        sz = re.search(r'<hp:sz width="(\d+)"', tbl)
        cc = re.search(r'colCnt="(\d+)"', tbl)
        if not sz or not cc:
            continue
        total, colcnt = int(sz.group(1)), int(cc.group(1))
        for rm in re.finditer(r'<hp:tr\b[^>]*>(.*?)</hp:tr>', tbl, re.S):
            ws = [int(x) for x in re.findall(r'<hp:cellSz width="(\d+)"', rm.group(1))]
            if len(ws) != colcnt:
                continue
            if abs(sum(ws) - total) > 2:
                errs.append(f"section: 표 행 폭 합({sum(ws)}) ≠ 표 폭({total}) "
                            f"— 열 폭 재분배 오류 의심")
                return   # 첫 건만 보고(노이즈 방지)
```

`main()`의 section 루프를 다음으로 교체:

```python
    for n in names:
        if re.match(r"Contents/section\d+\.xml$", n):
            sec = data[n].decode("utf-8", "replace")
            check_idrefs(sec, ranges, errs)
            check_table_widths(sec, errs)
```

docstring의 "검사 항목"에 `5) 표 행 폭 합계 == 표 폭 (span 없는 표, 열 폭 재분배 회귀 방어)` 한 줄 추가.

- [ ] **Step 4: 통과 확인 + 실파일 회귀**

Run: `python3 -m unittest tests.test_validate_hwpx_widths -v`
Expected: PASS (3 tests)

Run: `python3 skills/kca-report-style/scripts/validate_hwpx.py "/Users/bcchung81/workspace/works/대형LLM-동향-공공기관시사점.hwpx"`
Expected: `✓ 구조 검증 통과` (기존 정상 파일이 새 검사에 걸리지 않아야 함 — 걸리면 임계값이 아니라 검사 로직을 재검토)

- [ ] **Step 5: 커밋**

```bash
git add skills/kca-report-style/scripts/validate_hwpx.py tests/test_validate_hwpx_widths.py
git commit -m "validate_hwpx — 표 행 폭 합계 불변식 추가(열 폭 재분배 회귀 방어)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: 스킬·에이전트 문서 반영 (프로파일·Q&A·파이프라인)

**Files:**
- Modify: `skills/kca-report-layout/SKILL.md` (§8 폭 지시자, §9 신설)
- Modify: `skills/kca-style-lint/SKILL.md` (L21)
- Modify: `skills/kca-report-orchestrator/SKILL.md` (Phase 0·1 게이트, 재실행 매트릭스, 테스트 시나리오, 변경 이력)
- Modify: `agents/kca-builder.md` (adjust 단계)
- Modify: `agents/kca-planner.md` (보고대상 태그·표 구상 섹션)
- Modify: `agents/kca-writer.md` (규칙 16)
- Modify: `agents/kca-style-auditor.md` (L21 점검·입력 추가)

**Interfaces:**
- Consumes: Task 3의 CLI 규약, Task 4의 사이드카 규약.
- Produces: 에이전트들이 따를 규범 텍스트. 검증은 grep(Step 8).

- [ ] **Step 1: layout §8에 열 폭 규칙 추가**

`skills/kca-report-layout/SKILL.md` §8의 "표는 `[ 캡션 ]` + GFM 표로 작성하고, 본문 분량 예산(2p)에 포함한다(표 남용 금지 — 요지 전달에 표가 더 빠를 때만)." 문단 바로 뒤에 추가:

```markdown
**열 폭 (자동 재분배 + 지시자)**: kordoc은 열 폭을 균등 분할하므로 builder가 `adjust_table_widths.py`로 셀 내용 표시폭(한글 2·영숫자 1)에 비례해 자동 재분배한다 — 하한 열당 전체 폭 8%·헤더 폭 보장, 가중치 상한 5:1, 표 전체 폭 보존. writer가 특정 비율을 원할 때만 캡션 지시자 `[ 캡션 | 폭 2:1:1:3 ]`(비율 개수 = 열 수)를 쓴다. 지시자는 렌더 전에 캡션에서 제거되고 비율만 적용되며, 형식 오류·개수 불일치 시 자동 분배로 폴백한다(빌드 중단 없음).
```

- [ ] **Step 2: layout §9 신설**

`## Why — 왜 이 규율인가` 절 바로 앞에 삽입:

```markdown
## 9. 보고 대상 프로파일 — 보고자 수준 맞춤 (SSOT)

보고서 생성 시작 시 오케스트레이터가 **보고 대상 1개**를 선택받아 `_workspace/00_context.md`에 기록한다(자료 구성 방향과 함께). 아래 4개 축이 §1 분량 예산 등 기본값을 **대상별로 오버라이드**하는 유일 기준이다. planner는 관점 축에 맞춰 재료를 모으고, writer는 해당 열을 준수하며, style-auditor가 lint L21로 검증한다.

| 축 | 임원 | 경영진 | 부서장·실무 |
|---|---|---|---|
| 분량·구성 | 본문 1p 목표(최대 2p), 결론·건의 선행 | 본문 2p, 전략+관리 균형 | 본문 2~3p, 실행 상세 |
| 용어·각주 | 전문용어 → 쉬운 표현 치환 우선, 필수 용어만 각주 | 핵심 용어만 각주 | 전문용어 허용, 각주 최소 |
| 관점·메시지 | 의사결정·예산·리스크 | 전략·성과·조직 | 실행계획·일정·담당 |
| 표 상세도 | 총괄표만 본문, 상세 표는 붙임 | 총괄표+핵심 비교표 본문 | 상세 표 본문 허용 |

- 각주 총량 규칙(ㅇ당 `*`≤1+`※`≤1)은 모든 프로파일 공통 — 임원 프로파일은 "각주 증가"가 아니라 "쉬운 표현 우선"으로 해석한다.
- `00_context.md` 없이 실행되면 대상을 되묻는다(기본값 가정 금지).
```

- [ ] **Step 3: lint L21 추가**

`skills/kca-style-lint/SKILL.md` 린트 표의 L20 행 뒤에 추가:

```markdown
| L21 | **대상 프로파일 위반** | `00_context.md`의 보고 대상 대비 분량(임원: 본문 1p 목표)·용어 각주 밀도·관점·표 배치(임원: 상세 표 본문 금지)가 프로파일과 불일치 | 반려 |
```

그 아래 인용 줄 `> L11~L20 판정 기준…`을 `> L11~L21 판정 기준·…·보고 대상 프로파일(§9)은 \`kca-report-layout\` 스킬(SSOT)을 따른다.`로 갱신(기존 열거 내용 유지 + `보고 대상 프로파일(§9)` 추가).

- [ ] **Step 4: orchestrator Phase 0·1 게이트 + 매트릭스 + 이력**

`skills/kca-report-orchestrator/SKILL.md`:

(a) Phase 0 목록에 4번 항목 추가 (3. 재실행 판별 뒤):

```markdown
4. **생성 전 Q&A 게이트 (1단계)**: 하네스 실행이 확정되면 AskUserQuestion **1회**로 다음을 묻고 `_workspace/00_context.md`에 기록한다:
   - **보고 대상** (택1): 임원 / 경영진 / 부서장·실무 — `kca-report-layout` §9 프로파일이 분량·용어·관점·표 상세도를 결정. "Other"로 직접 지정 가능.
   - **자료 구성 방향** (택1): 표 중심(총괄표·비교표 적극) / 서술 중심(표 최소) / LLM 판단 위임.
   부분 재실행 시 기존 `00_context.md`를 재사용하고 다시 묻지 않는다. `00_context.md`가 없으면 기본값을 가정하지 말고 되묻는다.
```

(b) Phase 1 마지막 문장("planner가 반환한 **미확정·플레이스홀더 목록**을 사용자에게 확인받는다(핵심 수치가 비면 여기서 되묻기).")을 다음으로 교체:

```markdown
planner 산출물에는 **"표·부연자료 구상" 섹션이 반드시 포함**되어야 한다(누락 시 planner 재호출). Phase 1 종료 게이트에서 AskUserQuestion **1회(2단계 Q&A)**로 다음을 묶어 확인받는다:
- planner가 반환한 **미확정·플레이스홀더 목록**(핵심 수치가 비면 여기서 되묻기)
- **표·부연자료 후보 채택**(multiSelect): planner가 전체 조사내역을 분석해 제안한 총괄표·비교표·부연자료 후보(유형·묶는 조사항목·본문/붙임 배치·기대 효과 명시)를 후보별로 채택/제외. 채택 결과를 outline에 반영한 뒤 Phase 2로 진행한다. 1단계에서 "서술 중심"을 선택했어도 표가 명백히 유리한 항목은 후보로 제시할 수 있다(채택은 사용자 몫).
```

(c) 부분 재실행 매트릭스에 행 추가:

```markdown
| "대상 바꿔서 다시" (보고 대상 변경) | writer → style-auditor → builder → hwpx-qa | 01 outline (00_context.md만 갱신) |
```

(d) 테스트 시나리오에 추가:

```markdown
- **표 폭 흐름**: 4열 표(1열 짧은 라벨·4열 긴 설명) → builder의 adjust_table_widths.py 후 4열이 1열보다 넓고 행 폭 합 = 표 폭, validate 통과. `[ 캡션 | 폭 2:1:1:3 ]` 지시자는 캡션에서 제거되고 비율 적용. 제목 그라데이션·붙임 라벨박스 표는 불변.
- **대상 프로파일 흐름**: Phase 0에서 임원 선택 → writer가 본문 1~2p·총괄표만 본문. writer가 상세 표를 본문에 넣으면 auditor L21 반려.
- **2단계 제안 흐름**: planner outline에 표·부연자료 구상 섹션 부재 → planner 재호출. 사용자가 후보 일부만 채택 → writer 산출물에 채택분만 반영.
```

(e) 변경 이력 표에 행 추가:

```markdown
| 2026-07-14 | 표 열 폭 유동 분배(adjust_table_widths.py) + 보고 대상 프로파일(layout §9·L21) + 총괄표·부연자료 2단계 Q&A | scripts·builder·layout·lint·planner·writer·auditor·오케스트레이터 | 균등 4분할 표 개선·보고자 수준 맞춤·조사내역 기반 표 구상 제안(실전 보고서 피드백) |
```

- [ ] **Step 5: builder 파이프라인 반영**

`agents/kca-builder.md`:

(a) MD 전처리 명령을 다음으로 교체:

```
python3 ~/.claude/skills/kca-report-style/scripts/prep_report_md.py <draft.md> <prepared.md> _workspace/table_widths.json
```

그 아래 설명 문단 끝에 추가: `표 폭 지시자 \`[ 캡션 | 폭 2:1:1:3 ]\`는 캡션에서 제거되어 \`_workspace/table_widths.json\`으로 추출된다(3단계 adjust에서 사용).`

(b) 권장 경로의 2번(템플릿 병합) 뒤에 3번 추가:

```markdown
3. **표 열 폭 재분배**: 병합본의 균등폭 표를 셀 내용 비례로 재분배한다(제목·라벨박스 표는 자동 제외, 표 폭 보존):
   ```
   python3 ~/.claude/skills/kca-report-style/scripts/adjust_table_widths.py \
     _workspace/04_final.hwpx _workspace/04_final.hwpx \
     --widths _workspace/table_widths.json
   ```
   (in-place 안전 — 전체를 메모리에 읽은 뒤 쓴다. table_widths.json이 없으면 `--widths` 생략.)
```

(c) 도해 절의 순서 줄을 갱신: `순서 주의: prep_report_md.py → generate_document → build_from_template.py(양식 병합) → adjust_table_widths.py(표 폭) → inject_image.py(도해 주입, 마지막).`

- [ ] **Step 6: planner·writer·auditor 반영**

(a) `agents/kca-planner.md` 작업 원칙 1번 앞에 0번 추가:

```markdown
0. **보고 대상 반영**: `_workspace/00_context.md`의 보고 대상·자료 구성 방향을 읽고, `kca-report-layout` §9 프로파일의 **관점 축**(임원=의사결정·예산·리스크 / 경영진=전략·성과·조직 / 부서장·실무=실행계획·일정·담당)에 맞춰 재료를 수집한다. outline 머리에 `보고대상: {대상}`을 기록한다.
```

출력 구조 코드블록의 `# 골격:` 줄 아래에 `보고대상: {임원|경영진|부서장·실무}` 줄 추가, `## 수집 근거 로그` 앞에 의무 섹션 추가:

```markdown
## 표·부연자료 구상 (의무)
| # | 유형 | 제목(안) | 묶는 조사항목 | 배치 | 기대 효과 |
|---|------|---------|--------------|------|-----------|
| T1 | 총괄표 | {제목} | {근거 항목들} | 본문 | {가시성·충실도 1줄} |
| T2 | 부연설명 붙임 | {제목} | {근거 항목들} | 붙임 | {1줄} |
```

마지막 협업 문단의 "미확정·플레이스홀더 목록을 요약해 넘겨" 문장에 덧붙임: `표·부연자료 구상 후보도 함께 넘겨 오케스트레이터가 2단계 Q&A로 채택을 확정하게 한다.`

(b) `agents/kca-writer.md` 규칙 15 뒤에 16 추가:

```markdown
16. **보고 대상 프로파일(§9)** — `_workspace/00_context.md`의 보고 대상에 맞춰 분량·용어·관점·표 배치를 `kca-report-layout` §9 표의 해당 열로 조정. 임원이면 본문 1p 목표·결론 선행·상세 표는 붙임. outline의 표·부연자료 채택 결과만 표로 작성(미채택 후보는 만들지 않음). 특정 열 폭이 필요한 표만 `[ 캡션 | 폭 2:1:1:3 ]` 지시자 사용(기본은 자동 재분배에 맡김).
```

입력 줄을 `**입력**: \`_workspace/01_planner_outline.md\`, \`_workspace/00_context.md\`(보고 대상). (반려 재작업 시) \`_workspace/03_auditor_report.md\`.`로 갱신.

(c) `agents/kca-style-auditor.md`:
- 로드 목록의 `kca-style-lint` 줄을 `(SSOT, L1~L21)`로, `kca-report-layout` 줄을 `— L11~L21(분량·ㅇ≤3·통합·용어각주·붙임·표·프로파일) 판정 기준`으로 갱신.
- 검증 항목 18번 뒤에 추가:

```markdown
19. **대상 프로파일 준수** — `00_context.md`의 보고 대상 대비 분량(임원: 본문 1p 목표)·용어 각주 밀도·관점·표 배치(임원: 상세 표 본문 금지)가 layout §9와 일치하는가. 불일치면 반려 (L21)
```

- 입력 줄을 `**입력**: \`_workspace/02_writer_draft.md\`, 대조용 \`_workspace/01_planner_outline.md\`·\`_workspace/00_context.md\`.`로 갱신.

- [ ] **Step 7: 검증 (grep)**

```bash
grep -c "L21" skills/kca-style-lint/SKILL.md agents/kca-style-auditor.md            # 각 ≥1
grep -c "9. 보고 대상 프로파일" skills/kca-report-layout/SKILL.md                    # 1
grep -c "adjust_table_widths" agents/kca-builder.md skills/kca-report-layout/SKILL.md skills/kca-report-orchestrator/SKILL.md
grep -c "00_context" skills/kca-report-orchestrator/SKILL.md agents/kca-planner.md agents/kca-writer.md agents/kca-style-auditor.md
grep -c "표·부연자료 구상" agents/kca-planner.md skills/kca-report-orchestrator/SKILL.md
```

Expected: 모두 1 이상.

- [ ] **Step 8: 커밋**

```bash
git add skills/kca-report-layout/SKILL.md skills/kca-style-lint/SKILL.md \
        skills/kca-report-orchestrator/SKILL.md agents/
git commit -m "보고 대상 프로파일(§9·L21) + 총괄표 2단계 Q&A + 표 폭 파이프라인 문서 반영

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: 배포(~/.claude 동기화) + 종단 검증

**Files:**
- 대상: `~/.claude/skills/kca-*` 4개 디렉터리, `~/.claude/agents/kca-*.md` 5개 파일 (저장소 밖 — 커밋 대상 아님)

**Interfaces:**
- Consumes: Task 1~6 산출물 전부. 에이전트·PostToolUse 훅은 `~/.claude` 경로를 읽으므로 동기화 없이는 변경이 반영되지 않는다.

- [ ] **Step 1: 동기화**

```bash
cd /Users/bcchung81/workspace/report-harness
for s in kca-report-style kca-report-layout kca-report-orchestrator kca-style-lint; do
  rsync -a --exclude '__pycache__' "skills/$s/" ~/.claude/skills/"$s"/
done
rsync -a agents/ ~/.claude/agents/
```

- [ ] **Step 2: 동기화 검증**

```bash
diff -rq --exclude '__pycache__' skills/kca-report-style ~/.claude/skills/kca-report-style && echo SYNC-OK
python3 ~/.claude/skills/kca-report-style/scripts/adjust_table_widths.py 2>&1 | head -1
```

Expected: `SYNC-OK` + usage 메시지(스크립트가 배포 경로에서 실행됨).

- [ ] **Step 3: 종단 검증 (실전 보고서 재적용)**

```bash
cp "/Users/bcchung81/workspace/works/대형LLM-동향-공공기관시사점.hwpx" "$TMPDIR/e2e_in.hwpx"
python3 ~/.claude/skills/kca-report-style/scripts/adjust_table_widths.py "$TMPDIR/e2e_in.hwpx" "$TMPDIR/e2e_out.hwpx"
python3 ~/.claude/skills/kca-report-style/scripts/validate_hwpx.py "$TMPDIR/e2e_out.hwpx"
```

Expected: `열 폭 재분배: N개 표`(N ≥ 4 — 본문 균등폭 표들), `✓ 구조 검증 통과`. 추가로 kordoc `parse_document`로 내용 보존 확인(표 텍스트 손실 없음)이 가능하면 수행.

- [ ] **Step 4: 전체 테스트 최종 실행 + 커밋 확인**

```bash
python3 -m unittest discover -s tests -v
git status --short   # 깨끗해야 함(모든 변경 커밋됨)
git log --oneline -7
```

Expected: 전체 PASS, 워킹트리 클린.

---

## Self-Review 결과

- 스펙 커버리지: 자동 분배 알고리즘(Task 1·2), 제외 시그니처·순번 정의(Task 2), 지시자+사이드카(Task 3·4), validate 불변식(Task 5), builder 파이프라인·layout §8·§9·L21·planner·writer·auditor·orchestrator 게이트·매트릭스·테스트 시나리오·이력(Task 6), 배포·종단(Task 7) — 스펙의 변경 파일 목록 10개 전부 대응.
- 에러 핸들링: 지시자 형식 오류 폴백(compute_widths·extract_widths·CLI), adjust 실패 시 builder 재시도·균등폭 진행은 builder 문서의 기존 에러 핸들링 절이 커버(스크립트는 예외 시 비정상 종료 → builder가 1회 재시도).
- 타입 일관성: `compute_widths(col_texts, total, ratios)` — Task 1 정의·Task 2 사용 일치. `redistribute_section(xml, widths_map, start_index)` — Task 2 정의·Task 3 사용 일치. 사이드카 JSON 키는 문자열로 저장(Task 4)·`int(k)` 변환(Task 3) 일치.
