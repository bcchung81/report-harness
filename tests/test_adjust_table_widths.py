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
