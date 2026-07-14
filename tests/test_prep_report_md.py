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
