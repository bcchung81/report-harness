import os, re, sys, tempfile, unittest, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/kca-report-style/scripts"))
from adjust_table_widths import display_width, compute_widths, redistribute_section, process


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
        ws = [int(x) for x in re.findall(r'<hp:cellSz width="(\d+)"', out)]
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
        ws = [int(x) for x in re.findall(r'<hp:cellSz width="(\d+)"', out)]
        # t0(자동, 내용 동일) 균등 / label 불변 / t1(지시자 1:3) 뒤 열이 넓음
        self.assertEqual(ws[0], ws[1])
        self.assertEqual(ws[2:5], [5968, 565, 41626])
        self.assertGreater(ws[6], ws[5])

    def test_single_col_skipped(self):
        xml = _tbl(1, _tc(0, 50624, "제목"), 50624)
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
                self.assertIsNone(z.testzip())


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
