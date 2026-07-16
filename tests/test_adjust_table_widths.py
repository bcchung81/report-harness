import os, re, sys, tempfile, unittest, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/kca-report-style/scripts"))
from adjust_table_widths import display_width, compute_widths, redistribute_section, process


def _tc(col, width, text, span=1, row=0, height=1500):
    return (f'<hp:tc name="" header="0" borderFillIDRef="45">'
            f'<hp:subList vertAlign="CENTER"><hp:p paraPrIDRef="91" styleIDRef="0">'
            f'<hp:run charPrIDRef="135"><hp:t>{text}</hp:t></hp:run></hp:p></hp:subList>'
            f'<hp:cellAddr colAddr="{col}" rowAddr="{row}" />'
            f'<hp:cellSpan colSpan="{span}" rowSpan="1" />'
            f'<hp:cellSz width="{width}" height="{height}" />'
            f'<hp:cellMargin left="141" right="141" top="141" bottom="141" /></hp:tc>')


def _tbl(colcnt, cells, total, rowcnt=1):
    return (f'<hp:tbl id="1025" rowCnt="{rowcnt}" colCnt="{colcnt}" borderFillIDRef="4">'
            f'<hp:sz width="{total}" widthRelTo="ABSOLUTE" height="1500" />'
            f'<hp:tr>{cells}</hp:tr></hp:tbl>')


def _data_tbl(texts_row0, texts_row1, widths, total):
    """헤더+데이터 2행 데이터표 (kordoc 스타일 — 비균등폭 허용)"""
    cells = "".join(_tc(c, widths[c], t) for c, t in enumerate(texts_row0))
    cells += "".join(_tc(c, widths[c], t, row=1) for c, t in enumerate(texts_row1))
    return _tbl(len(widths), cells, total, rowcnt=2)


class TestRedistributeSection(unittest.TestCase):
    def test_data_table_adjusted(self):
        xml = _data_tbl(["구분", "내용"], ["가", "아주 길고 긴 설명 텍스트"], [11000, 11000], 22000)
        out, n, nxt = redistribute_section(xml, {})
        self.assertEqual(n, 1)
        self.assertEqual(nxt, 1)
        ws = [int(x) for x in re.findall(r'<hp:cellSz width="(\d+)"', out)]
        self.assertEqual(sum(ws), 44000)            # 2행 × 22000
        self.assertGreater(ws[1], ws[0])

    def test_kordoc_nonuniform_data_table_adjusted(self):
        # kordoc generate_document가 비균등폭으로 렌더한 데이터표도 처리 대상
        # (과거 '첫 행 비균등=참고양식' 신호는 kordoc 내용비례 렌더로 무효 — rowCnt<2로 판별)
        xml = _data_tbl(["연도", "지적 상세내용"], ["'24", "관리시스템 부재로 잔액 파악 불가"],
                        [2785, 19215], 22000)
        out, n, _ = redistribute_section(xml, {})
        self.assertEqual(n, 1)
        ws = [int(x) for x in re.findall(r'<hp:cellSz width="(\d+)"', out)]
        self.assertEqual(ws[0] + ws[1], 22000)

    def test_label_and_spanned_tables_skipped(self):
        # 라벨박스·제목표는 항상 rowCnt=1 → 제외. span 표도 제외.
        label = _tbl(3, _tc(0, 5968, "붙임 1") + _tc(1, 565, "") + _tc(2, 41626, "제목"), 48159)
        spanned = _tbl(2, _tc(0, 11000, "가", span=2) + _tc(1, 11000, "나", row=1),
                       22000, rowcnt=2)
        out, n, _ = redistribute_section(label + spanned, {})
        self.assertEqual(n, 0)
        self.assertEqual(out, label + spanned)      # 원문 그대로

    def test_widths_map_applies_by_body_table_order(self):
        t0 = _data_tbl(["같음", "같음"], ["같음", "같음"], [11000, 11000], 22000)
        label = _tbl(3, _tc(0, 5968, "붙임 1") + _tc(1, 565, "") + _tc(2, 41626, "제목"), 48159)
        t1 = _data_tbl(["같음", "같음"], ["같음", "같음"], [11000, 11000], 22000)
        out, n, _ = redistribute_section(t0 + label + t1, {1: [1, 3]})
        self.assertEqual(n, 2)
        ws = [int(x) for x in re.findall(r'<hp:cellSz width="(\d+)"', out)]
        # t0(자동, 내용 동일·2행=셀4) 균등 / label 불변 / t1(지시자 1:3) 뒤 열이 넓음
        self.assertEqual(ws[0], ws[1])
        self.assertEqual(ws[4:7], [5968, 565, 41626])
        self.assertGreater(ws[8], ws[7])

    def test_single_col_skipped(self):
        xml = _tbl(1, _tc(0, 50624, "제목") + _tc(0, 50624, "부제", row=1), 50624, rowcnt=2)
        out, n, _ = redistribute_section(xml, {})
        self.assertEqual(n, 0)
        self.assertEqual(out, xml)


class TestProcessZip(unittest.TestCase):
    def _make_hwpx(self, path, section_xml):
        with zipfile.ZipFile(path, "w") as z:
            z.writestr(zipfile.ZipInfo("mimetype"), b"application/hwp+zip",
                       compress_type=zipfile.ZIP_STORED)
            z.writestr("Contents/header.xml", "<hh:head></hh:head>")
            z.writestr("Contents/section0.xml", section_xml)

    def test_roundtrip_preserves_mimetype_and_adjusts(self):
        xml = _data_tbl(["구분", "내용"], ["가", "아주 길고 긴 설명 텍스트"], [11000, 11000], 22000)
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
            self.assertEqual(sum(ws), 44000)        # 2행 × 22000
            self.assertGreater(ws[1], ws[0])

    def test_in_place_same_path(self):
        xml = _data_tbl(["구분", "내용"], ["가", "아주 길고 긴 설명 텍스트"], [11000, 11000], 22000)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "same.hwpx")
            self._make_hwpx(p, xml)
            self.assertEqual(process(p, p, {}), 1)
            with zipfile.ZipFile(p) as z:
                self.assertIsNone(z.testzip())


class TestRowHeightRecompute(unittest.TestCase):
    """kordoc이 협폭 열 기준으로 과대 산정한 행 높이를 새 열 폭 기준으로 재계산.

    실측 눈금(정상 렌더): 1줄=2202, 2줄=4122, 3줄=6042 → 줄당 1920 + 패딩 282.
    """

    def _heights(self, out):
        return [int(x) for x in re.findall(r'<hp:cellSz width="\d+" height="(\d+)"', out)]

    def test_pathological_height_shrinks_to_one_line(self):
        # kordoc이 57882(≈20cm)로 과대 산정한 1줄짜리 행 → 재분배 후 1줄 높이로
        cells = (_tc(0, 11000, "구분", height=57882) + _tc(1, 11000, "내용", height=57882)
                 + _tc(0, 11000, "가", row=1, height=57882)
                 + _tc(1, 11000, "나", row=1, height=57882))
        out, n, _ = redistribute_section(_tbl(2, cells, 22000, rowcnt=2), {})
        self.assertEqual(n, 1)
        hs = self._heights(out)
        self.assertEqual(hs, [2202, 2202, 2202, 2202])

    def test_multiline_cell_gets_taller_row_uniform(self):
        long_text = "관리체계와 시스템 기반 부재로 집행·정산·성과 추적이 곤란하여 재정누수 상존" * 2
        cells = (_tc(0, 11000, "구분") + _tc(1, 11000, "내용")
                 + _tc(0, 11000, "가", row=1) + _tc(1, 11000, long_text, row=1))
        out, n, _ = redistribute_section(_tbl(2, cells, 22000, rowcnt=2), {})
        self.assertEqual(n, 1)
        hs = self._heights(out)
        self.assertEqual(hs[0], hs[1])                     # 행별 셀 높이 일치
        self.assertEqual(hs[2], hs[3])
        self.assertGreater(hs[2], 2202)                    # 다줄 행은 1줄보다 큼
        self.assertEqual((hs[2] - 282) % 1920, 0)          # 줄 단위 눈금

    def test_label_table_heights_untouched(self):
        label = _tbl(3, _tc(0, 5968, "붙임 1") + _tc(1, 565, "") + _tc(2, 41626, "제목"), 48159)
        out, n, _ = redistribute_section(label, {})
        self.assertEqual(n, 0)
        self.assertIn('height="1500"', out)                # 원래 높이 보존


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
