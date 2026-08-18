"""audit_style.py 회귀 테스트 (R074).

린트가 스코프 아웃한 style-guide 철칙을 결정론으로 잡는지 확인한다. 실제 사고 재현:
'26.8.15 3기관 협의자료가 전 문장 `~함/~됨` 종결이었는데 lint_md_profile을 통과했다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
from audit_style import audit_text  # noqa: E402

OK_HEAD = "3개 기관 데이터 발굴·연계 방안(안)\n\n< '26. 8. 15.(금), 전파기반본부 데이터팀 >\n\n"


def rules(items):
    return [x["rule"] for x in items]


def test_forbidden_ending_detected():
    v, _ = audit_text(OK_HEAD + "□ 추진 배경\n\n ㅇ **(공통 과제)** 자료가 흩어져 있어 과제 수행이 불가함\n")
    assert "ending-forbidden" in rules(v)


def test_noun_ending_passes():
    v, _ = audit_text(OK_HEAD + "□ 추진 배경\n\n ㅇ **(공통 과제)** 자료가 흩어져 있어 과제 수행 불가\n")
    assert "ending-forbidden" not in rules(v)


def test_multiline_item_is_joined_before_ending_check():
    """계층 문구가 두 줄로 접혀 있어도 마지막 줄의 종결을 봐야 한다."""
    body = "□ 추진 배경\n\n ㅇ **(공통 과제)** 상위 계획 과제가 모두 흩어진 자료를\n   입력값으로 요구하고 있음\n"
    v, _ = audit_text(OK_HEAD + body)
    assert "ending-forbidden" in rules(v)


def test_rfp_and_minutes_endings_exempt():
    """style-guide §4 예외 — RFP '~하여야 함'과 회의록 '~답변함'은 합법이다."""
    v, _ = audit_text(OK_HEAD + "□ 주요 내용\n\n ㅇ **(제출 서류)** 입찰자는 사업수행계획서를 제출하여야 함\n")
    assert "ending-forbidden" not in rules(v)
    v, _ = audit_text(OK_HEAD + "□ 주요 내용\n\n ㅇ **(질의 응답)** 유지보수 범위를 묻자 담당자가 별도 계약이라 답변함\n")
    assert "ending-forbidden" not in rules(v)


def test_quoted_original_text_exempt():
    """법령 원문 인용이 인용부호로 끝나면 종결어미 대상이 아니다."""
    v, _ = audit_text(OK_HEAD + '□ 추진 배경\n\n ㅇ **(법정 의무)** 제11조는 "이를 제공하여야 한다"\n')
    assert "ending-forbidden" not in rules(v)


def test_title_without_type_suffix_detected():
    v, _ = audit_text("3개 기관 데이터 발굴·연계 협의 자료\n\n□ 추진 배경\n")
    assert "title-no-suffix" in rules(v)


def test_title_with_type_suffix_passes():
    v, _ = audit_text(OK_HEAD + "□ 추진 배경\n")
    assert "title-no-suffix" not in rules(v)


def test_numbered_section_detected():
    v, _ = audit_text(OK_HEAD + "□ 1. 왜 지금 데이터 연계인가\n")
    assert "section-numbered" in rules(v)


def test_section_symbol_notation_detected():
    """R075 — 조문은 한국식 전체 표기. § 축약은 위반."""
    v, _ = audit_text(OK_HEAD + "□ 현황 및 문제점\n\n ㅇ **(분장 구조)** 영 §123②2에 따라 권한 배정\n")
    assert "article-symbol" in rules(v)
    v, _ = audit_text(OK_HEAD + "□ 현황 및 문제점\n\n ㅇ **(분장 구조)** 영 제123조제2항제2호에 따라 권한 배정\n")
    assert "article-symbol" not in rules(v)


def test_offpool_section_title_is_warning_not_violation():
    v, w = audit_text(OK_HEAD + "□ 세 기관이 가진 것\n")
    assert "section-title-offpool" in rules(w)
    assert "section-title-offpool" not in rules(v)


def test_annex_sections_exempt_from_pool_check():
    """붙임 배너 이후의 □는 붙임 내부 구조라 본문 절 어휘 풀 대상이 아니다."""
    doc = OK_HEAD + "□ 추진 배경\n\n| 붙임 1 | | 공공데이터포털 개방 현황 |\n|---|---|---|\n\n□ 유형별 개방 건수\n"
    _, w = audit_text(doc)
    assert "section-title-offpool" not in rules(w)


def test_table_rows_are_skipped():
    """표 셀의 '~함'은 서술이 아니므로 대상이 아니다."""
    doc = OK_HEAD + "□ 추진 배경\n\n| 구 분 | 내 용 |\n|---|---|\n| 조치 | 재검토함 |\n"
    v, _ = audit_text(doc)
    assert "ending-forbidden" not in rules(v)
