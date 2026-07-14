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
