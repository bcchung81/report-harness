import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/kca-report-style/scripts"))
from lint_report_md import lint

HEADER = "# 시스템 구축 추진계획 보고\n\n< '26. 7. 14.(화), 기금사업성과팀 >\n\n"
BLUF = "◇ 통합관리 일원화 검토 건의 — 관리 사각지대 해소 기반 확보\n\n"

LONG = "주체·방법·근거를 담아 두 줄을 꽉 채우는 설명으로 집행·정산·성과 통합관리 체계와 시스템 기반을 이미 보유하여 체계적 사업관리 수행 여건 확보"


def rules_of(result, kind):
    return [f["rule"] for f in result[kind]]


class TestL1NounEnding(unittest.TestCase):
    def test_verb_ending_flagged(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG} 시스템을 운영합니다\n"
        self.assertIn("L1", rules_of(lint(md), "violations"))

    def test_da_ending_flagged(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG} 체계가 부재한 상태이다.\n"
        self.assertIn("L1", rules_of(lint(md), "violations"))

    def test_noun_ending_clean(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n"
        self.assertNotIn("L1", rules_of(lint(md), "violations"))

    def test_ham_nominalization_allowed(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG} 마련 필요함\n"
        self.assertNotIn("L1", rules_of(lint(md), "violations"))


class TestL4SectionTitle(unittest.TestCase):
    def test_long_title_flagged(self):
        md = HEADER + BLUF + "- 추진 배경 및 목적으로서 당 본부가 보유한 통합관리 체계와 시스템 기반을 설명하는 섹션\n  - (현황) " + LONG + "\n"
        self.assertIn("L4", rules_of(lint(md), "violations"))

    def test_short_title_clean(self):
        md = HEADER + BLUF + f"- 추진 배경 및 목적\n  - (현황) {LONG}\n"
        self.assertNotIn("L4", rules_of(lint(md), "violations"))


class TestL7Skeleton(unittest.TestCase):
    def test_missing_sender_flagged(self):
        md = "# 제목\n\n" + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n"
        self.assertIn("L7", rules_of(lint(md), "violations"))

    def test_missing_title_flagged(self):
        md = "< '26. 7. 14.(화), 팀 >\n\n" + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n"
        self.assertIn("L7", rules_of(lint(md), "violations"))


class TestL11ItemDensity(unittest.TestCase):
    def test_four_items_flagged(self):
        items = "".join(f"  - (리드{i}) {LONG}\n" for i in range(4))
        md = HEADER + BLUF + "- 추진 배경\n" + items
        self.assertIn("L11", rules_of(lint(md), "violations"))

    def test_three_items_clean(self):
        items = "".join(f"  - (리드{i}) {LONG}\n" for i in range(3))
        md = HEADER + BLUF + "- 추진 배경\n" + items
        self.assertNotIn("L11", rules_of(lint(md), "violations"))

    def test_appendix_items_not_counted(self):
        items = "".join(f"  - (리드{i}) {LONG}\n" for i in range(4))
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n- 붙임 1. 상세\n" + items
        self.assertNotIn("L11", rules_of(lint(md), "violations"))


class TestL12BodyBudget(unittest.TestCase):
    def test_over_18_items_flagged(self):
        secs = "".join(
            f"- 섹션{s}\n" + "".join(f"  - (리드{s}{i}) {LONG}\n" for i in range(3))
            for s in range(7)
        )  # 21 ㅇ
        md = HEADER + BLUF + secs
        self.assertIn("L12", rules_of(lint(md), "violations"))

    def test_three_body_tables_flagged(self):
        table = "[ 캡션 ]\n| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n\n" + table * 3
        self.assertIn("L12", rules_of(lint(md), "violations"))

    def test_appendix_tables_not_counted(self):
        table = "[ 캡션 ]\n| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        md = (HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n\n"
              + f"- 붙임 1. 상세\n  - (구성) {LONG}\n\n" + table * 3)
        self.assertNotIn("L12", rules_of(lint(md), "violations"))


class TestL13Footnotes(unittest.TestCase):
    def test_marker_without_definition_flagged(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) PIMS* 기반 {LONG}\n"
        self.assertIn("L13", rules_of(lint(md), "violations"))

    def test_orphan_definition_flagged(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n\n* RAG: 검색 증강 생성 기법\n"
        self.assertIn("L13", rules_of(lint(md), "violations"))

    def test_matched_pair_clean(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) PIMS* 기반 {LONG}\n\n* PIMS: 사업정보관리시스템\n"
        self.assertNotIn("L13", rules_of(lint(md), "violations"))

    def test_definition_for_table_term_clean(self):
        md = (HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n\n"
              "[ 요약 ]\n| 주체 | 건수 |\n|---|---|\n| NABO | 10 |\n\n* NABO: 국회예산정책처\n")
        self.assertNotIn("L13", rules_of(lint(md), "violations"))

    def test_definition_for_absent_term_flagged(self):
        md = (HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n\n"
              "[ 요약 ]\n| 주체 | 건수 |\n|---|---|\n| NABO | 10 |\n\n* RAG: 검색 증강 생성\n")
        self.assertIn("L13", rules_of(lint(md), "violations"))


class TestL13bFootnoteQuota(unittest.TestCase):
    def test_two_star_markers_flagged(self):
        md = (HEADER + BLUF + f"- 추진 배경\n  - (현황) PIMS* 및 RAG* 기반 {LONG}\n\n"
              "* PIMS: 시스템\n* RAG: 기법\n")
        self.assertIn("L13b", rules_of(lint(md), "violations"))

    def test_one_star_one_note_clean(self):
        md = (HEADER + BLUF + f"- 추진 배경\n  - (현황) PIMS* 기반 {LONG}\n\n"
              "※ 세부 기준은 내부 지침 참조\n\n* PIMS: 시스템\n")
        self.assertNotIn("L13b", rules_of(lint(md), "violations"))


class TestL16Schedule(unittest.TestCase):
    def test_no_date_flagged(self):
        md = HEADER + BLUF + f"- 향후 계획\n  - (착수) {LONG}\n"
        self.assertIn("L16", rules_of(lint(md), "violations"))

    def test_date_clean(self):
        md = HEADER + BLUF + f"- 향후 계획\n  - (착수) {LONG} : '26. 9월 중\n"
        self.assertNotIn("L16", rules_of(lint(md), "violations"))

    def test_placeholder_clean(self):
        md = HEADER + BLUF + f"- 향후 계획\n  - (착수) {LONG} ['26.__월] (안)\n"
        self.assertNotIn("L16", rules_of(lint(md), "violations"))


class TestL22Bluf(unittest.TestCase):
    def test_no_bluf_exec_target_flagged(self):
        md = HEADER + f"- 추진 배경\n  - (현황) {LONG}\n"
        self.assertIn("L22", rules_of(lint(md, target="임원"), "violations"))

    def test_gist_block_satisfies_bluf(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n"
        self.assertNotIn("L22", rules_of(lint(md, target="임원"), "violations"))

    def test_gist_section_satisfies_bluf(self):
        md = HEADER + f"- 보고 요지\n  - (핵심) {LONG}\n- 추진 배경\n  - (현황) {LONG}\n"
        self.assertNotIn("L22", rules_of(lint(md, target="임원"), "violations"))

    def test_no_target_downgrades_to_warning(self):
        md = HEADER + f"- 추진 배경\n  - (현황) {LONG}\n"
        result = lint(md)
        self.assertNotIn("L22", rules_of(result, "violations"))
        self.assertIn("L22", rules_of(result, "warnings"))


class TestWarnings(unittest.TestCase):
    def test_skinny_item_warned_L2(self):
        md = HEADER + BLUF + "- 추진 배경\n  - (구축) 자체 LLM 구축\n"
        self.assertIn("L2", rules_of(lint(md), "warnings"))

    def test_overlong_item_warned_L3(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG} {LONG} {LONG}\n"
        self.assertIn("L3", rules_of(lint(md), "warnings"))

    def test_wa_enumeration_warned_L5(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) 집행와 정산와 성과 통합 관리로 {LONG}\n"
        self.assertIn("L5", rules_of(lint(md), "warnings"))

    def test_missing_lead_warned_L6(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - 괄호 리드 없이 시작하는 항목 {LONG}\n"
        self.assertIn("L6", rules_of(lint(md), "warnings"))


class TestL19AppendixStructure(unittest.TestCase):
    def test_table_only_appendix_flagged(self):
        md = (HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n\n"
              "- 붙임 1. 상세\n\n[ 캡션 ]\n| a | b |\n|---|---|\n| 1 | 2 |\n")
        self.assertIn("L19", rules_of(lint(md), "violations"))

    def test_summary_before_table_clean(self):
        md = (HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n\n"
              f"- 붙임 1. 상세\n  - (구성) {LONG}\n\n[ 캡션 ]\n| a | b |\n|---|---|\n| 1 | 2 |\n")
        self.assertNotIn("L19", rules_of(lint(md), "violations"))


def table_md(rows, caption="캡션"):
    body = "".join(f"| 항목{i} | 값{i} |\n" for i in range(rows))
    return f"[ {caption} ]\n| 구분 | 내용 |\n|---|---|\n{body}\n"


class TestL23BodyTableSize(unittest.TestCase):
    def test_nine_row_body_table_flagged(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n\n" + table_md(9)
        self.assertIn("L23", rules_of(lint(md), "violations"))

    def test_eight_row_body_table_clean(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n\n" + table_md(8)
        self.assertNotIn("L23", rules_of(lint(md), "violations"))

    def test_large_appendix_table_clean(self):
        md = (HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n\n"
              f"- 붙임 1. 상세\n  - (구성) {LONG}\n\n" + table_md(17))
        self.assertNotIn("L23", rules_of(lint(md), "violations"))


class TestL24LegalCitation(unittest.TestCase):
    def test_section_sign_flagged(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (근거) 정진 §45③에 따라 위탁 가능하여 {LONG}\n"
        self.assertIn("L24", rules_of(lint(md), "violations"))

    def test_circled_number_after_jo_flagged(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (근거) 「전파법」 제66조①·④5호에 따라 {LONG}\n"
        self.assertIn("L24", rules_of(lint(md), "violations"))

    def test_spaced_jo_hang_flagged(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (근거) 「전파법」 제66조 제1항에 따라 {LONG}\n"
        self.assertIn("L24", rules_of(lint(md), "violations"))

    def test_korean_style_clean(self):
        md = (HEADER + BLUF
              + f"- 추진 배경\n  - (근거) 「전파법」 제66조제1항 및 제66조제4항제5호에 따라 {LONG}\n")
        self.assertNotIn("L24", rules_of(lint(md), "violations"))

    def test_table_cells_also_checked(self):
        md = (HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n\n"
              "[ 근거 법령 ]\n| 구분 | 조문 |\n|---|---|\n| 위탁 | 「정보통신산업 진흥법」 제45조③ |\n")
        self.assertIn("L24", rules_of(lint(md), "violations"))


class TestVerdict(unittest.TestCase):
    def test_violation_gives_rejection(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG} 시스템을 운영합니다\n"
        self.assertEqual(lint(md)["verdict"], "반려")

    def test_warning_only_gives_pass_with_count(self):
        md = HEADER + BLUF + "- 추진 배경\n  - (구축) 자체 LLM 구축\n"
        r = lint(md)
        self.assertTrue(r["verdict"].startswith("통과 (경고"))

    def test_clean_gives_pass(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n"
        r = lint(md)
        self.assertEqual(r["verdict"], "통과", msg=str(r))

    def test_stats_present(self):
        md = HEADER + BLUF + f"- 추진 배경\n  - (현황) {LONG}\n"
        stats = lint(md)["stats"]
        self.assertEqual(stats["body_sections"], 1)
        self.assertEqual(stats["body_items"], 1)
        self.assertIn("numeric_density_per_1000", stats)


if __name__ == "__main__":
    unittest.main()
