import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
from lint_md_profile import lint_text

def rules(violations):
    return {v["rule"] for v in violations}

def test_clean_gaejosik_passes():
    # 괄호 리드는 3음절 이상 구체 명사구(R051) — 표 헤더의 2음절 벌려쓰기(`구 분`)는 계속 합법.
    text = ("□ 추진 배경\n"
            " ㅇ (추진 목적) AI 활용 **격차 해소**를 위한 환경 조성\n"
            "   - ChatGPT Team 6개 계정 구독(약 3.2백만원/연) 지원\n"
            "※ 세부내용은 붙임 참조\n"
            "| 구 분 | 내용 |\n| --- | --- |\n| A | B |\n")
    assert lint_text(text) == []

def test_inline_dash_and_star_detected():  # R001: 서술 중 - * 잔재
    text = "ㅇ 조사 결과 - 세 가지로 요약되며 *중요* 항목은 다음과 같음\n"
    assert {"inline-markdown", "non-bold-markup"} <= rules(lint_text(text))

def test_inline_backtick_and_heading():
    assert "inline-markdown" in rules(lint_text("ㅇ 명령은 `run` 사용\n"))
    assert "inline-markdown" in rules(lint_text("# 제목처럼 쓴 마크다운\n"))

def test_bold_is_allowed():
    assert lint_text("ㅇ **핵심 명사구** 강조는 허용\n") == []

def test_table_over_6_cols():
    text = "| a | b | c | d | e | f | g |\n| - | - | - | - | - | - | - |\n"
    assert "table-too-wide" in rules(lint_text(text))

def test_bullet_overflow_under_one_yo():   # R045: 3개째부터 위반
    text = "ㅇ 요지\n" + "".join(f"   - 상세{i}\n" for i in range(3))
    assert "bullet-overflow" in rules(lint_text(text))

def test_two_bullets_allowed_under_one_yo():   # R045: 2개까지는 합법
    text = "ㅇ 요지\n   - 상세1\n   - 상세2\n"
    assert "bullet-overflow" not in rules(lint_text(text))

def test_html_tag():
    assert "html-tag" in rules(lint_text("ㅇ 내용 <br> 줄바꿈\n"))

def test_depth_exceeded_on_deep_nesting():
    text = ("□ 절\n"
            " ㅇ 요지\n"
            "   - 상세\n"
            "      - 5단 중첩 세부\n")
    assert "depth-exceeded" in rules(lint_text(text))

def test_depth_ok_within_4_levels():
    text = "□ 절\n ㅇ 요지\n   - 상세\n※ 단서\n＊ 각주\n"
    assert lint_text(text) == []

def test_bullet_run_resets_at_section():   # □ 경계에서 카운터 리셋 (R045 상한 2개 기준)
    text = ("ㅇ A\n   - a\n   - b\n"
            "□ 새 절\n   - c\n   - d\n")
    assert "bullet-overflow" not in rules(lint_text(text))

def test_chevron_label_not_html():         # 코퍼스 관례: < > 영문 혼용 라벨
    assert "html-tag" not in rules(lint_text("ㅇ <AI 활용 방안> 관련 논의\n"))

# ── 개선본 대조로 확정된 실무 관례 (R051~R053·R056) ──────────────────────────

def test_caption_numbered_detected():      # R056: 캡션에 표 일련번호 금지
    assert "caption-numbered" in rules(lint_text("[ 표1. 추진 총괄 요약 ]\n"))

def test_caption_descriptive_ok():         # 내용 서술형 캡션은 합법
    assert lint_text("[ 월별 바이브코딩 교육 진행 ]\n") == []

def test_annex_defer_detected():           # R053: 괄호로 붙임에 설명을 미루는 표기
    text = "ㅇ (초기 설계) 3레이어 하이브리드 구조(상세 붙임1 참조)\n"
    assert "annex-crossref" in rules(lint_text(text))

def test_annex_closing_note_ok():          # 맺음의 ※ 참조는 코퍼스 합법 관례
    assert "annex-crossref" not in rules(lint_text("※ 세부내용은 붙임 참조\n"))

def test_lead_two_syllable_detected():     # R051: 2음절 괄호 리드 (벌려쓴 형태·붙인 형태 모두)
    assert "lead-too-short" in rules(lint_text("ㅇ **(품 질)** 오류율 0%\n"))
    assert "lead-too-short" in rules(lint_text("ㅇ **(배포)** 배포 완료\n"))

def test_lead_specific_noun_ok():          # 3음절 이상 구체 명사구는 합법
    assert lint_text("ㅇ **(서비스 품질)** 오류율 0%\n") == []

def test_footnote_overflow_detected():     # R052: 용어 각주 4개 초과
    text = "".join(f"＊ 용어{i} : 설명\n" for i in range(5))
    assert "footnote-overflow" in rules(lint_text(text))

def test_footnote_within_limit_ok():
    text = "".join(f"＊ 용어{i} : 설명\n" for i in range(4))
    assert "footnote-overflow" not in rules(lint_text(text))
    assert "html-tag" in rules(lint_text("ㅇ 내용 <br> 줄바꿈\n"))
    assert "html-tag" in rules(lint_text("<table><tr><td>x</td></tr></table>\n"))

def test_nested_dash_is_depth_violation(): # 대시 중첩 = 위반 (들여쓰기 폭 무관)
    text = " ㅇ 요지\n  - 상세\n    - 중첩 세부\n"
    assert "depth-exceeded" in rules(lint_text(text))

def test_same_level_dashes_ok_any_indent():# 동일 레벨 대시는 들여쓰기 폭 무관 정상
    text = " ㅇ 요지\n     - 상세1\n     - 상세2\n"
    assert "depth-exceeded" not in rules(lint_text(text))

def test_triple_star_detected():           # ***볼드이탤릭*** 우회 차단
    assert "non-bold-markup" in rules(lint_text("ㅇ 이는 ***매우 중요***한 사안임\n"))

def test_midtext_box_symbol_detected():    # 문장 중간 □ 검출
    assert "misplaced-marker" in rules(lint_text("ㅇ 문장 중간에 □ 표기가 있는 경우\n"))

def test_inline_trailing_note_allowed():   # ※ 인라인 후행 참조는 코퍼스 합법 패턴
    assert lint_text("ㅇ 측정 3원칙 적용 ※ 등급별 산식은 붙임 2\n") == []

def test_grade_label_not_html():           # <A 등급> 등 단일문자+공백 라벨은 HTML 아님
    for s in ["ㅇ <A 등급> 사업 검토\n", "ㅇ <B 안> 채택\n", "ㅇ <I 유형> 분류\n", "ㅇ <P 형> 지정\n"]:
        assert "html-tag" not in rules(lint_text(s))

def test_second_box_on_valid_line_detected():  # 선두 □ 합법 + 같은 줄 두 번째 □ 검출
    assert "misplaced-marker" in rules(lint_text("□ 첫 항목: 세부는 별도 □ 서식 참조\n"))

def test_highlight_marker_allowed():       # R040: ==특히 강조== 하이라이트 문법 합법
    assert lint_text("ㅇ 핵심은 ==특히 강조== 사항\n") == []
    assert lint_text("ㅇ **볼드**와 ==하이라이트== 병용\n") == []

def test_highlight_unpaired_detected():    # 짝 안 맞는 == 는 잔존 위험 — 위반
    assert "highlight-unpaired" in rules(lint_text("ㅇ 핵심은 ==특히 강조 사항\n"))


# --- 텍스트 규범에서 결정론 검출로 내린 5종 (R029·R044·R046·R057·R059) ---------

def _rules(text):
    return [v["rule"] for v in lint_text(text)]


def test_date_full_form_flags_four_digit_year():
    """R046 — 본문 날짜는 'yy.m월. 4자리 연도 풀 표기는 위반."""
    assert "date-full-form" in _rules("ㅇ 2026. 7. 30. 회의에서 확정한 내용")


def test_date_full_form_allows_sending_line_and_short_form():
    """예외 둘 — 발신 줄은 일자·요일까지 적고, 축약형 `'26.6.23(화)`도 합법."""
    assert "date-full-form" not in _rules("< '26. 7. 30.(목), 경영기획본부 AI디지털심화팀 >")
    assert "date-full-form" not in _rules("ㅇ '26.6.23(화) 개최 예정인 심의에 상정")


def test_label_enumeration_needs_both_list_and_label():
    """R044 — 가운뎃점 나열과 'N단 구조' 라벨이 같은 줄에 있을 때만. 사양 나열은 통과."""
    assert "label-enumeration" in _rules("ㅇ 핵심결론·본문·보충안내·출처표기 4단 구조로 규격화")
    assert "label-enumeration" not in _rules("ㅇ Node.js 24.x · Next.js 16.2 · React 19.2 적용")
    assert "label-enumeration" not in _rules("ㅇ 근거 소실·실적 누락·작성부담 해소")


def test_nested_paren_lead():
    """R029 — ㅇ가 괄호 리드면 하위 대시는 괄호 리드를 쓰지 않는다."""
    bad = "ㅇ **(지적 사항)** 객관성이 부족하다는 지적\n\n   - (세부) 표본 집계였음"
    ok = "ㅇ **(지적 사항)** 객관성이 부족하다는 지적\n\n   - 표본 집계였음"
    assert "nested-paren-lead" in _rules(bad)
    assert "nested-paren-lead" not in _rules(ok)


def test_plan_subject_scoped_to_plan_section():
    """R059 — '향후 계획' 절에서만 조직 주어를 잡는다. 다른 절은 대상이 아니다."""
    plan = "□ 향후 계획\n\n ㅇ 검정관리팀이 외부용역 전환을 추진 중"
    other = "□ 추진 배경\n\n ㅇ 검정관리팀이 외부용역 전환을 추진 중"
    assert "plan-subject" in _rules(plan)
    assert "plan-subject" not in _rules(other)


def test_plan_subject_no_false_positive_on_common_nouns():
    """'처리결과는'의 '과는', '확인사실이'의 '실이' 같은 일반명사에 걸리면 안 된다."""
    t = "□ 향후 계획\n\n ㅇ 처리결과는 코드표로 관리하고 확인사실이 남도록 한다"
    assert "plan-subject" not in _rules(t)


def test_connective_repeat_counts_per_section():
    """R057 — 절 단위로 센다. 절이 바뀌면 카운트가 리셋된다."""
    over = "□ 절1\n\n ㅇ 확인하고 정리하고 반영하고 보고하고 종결한다"
    split = ("□ 절1\n\n ㅇ 확인하고 정리하고\n\n"
             "□ 절2\n\n ㅇ 반영하고 보고하고")
    assert "connective-repeat" in _rules(over)
    assert "connective-repeat" not in _rules(split)


def test_annex_banner_closes_section():
    """붙임 배너도 절 경계 — □가 없는 붙임 구간으로 '향후 계획' 상태가 새면 안 된다."""
    t = ("□ 향후 계획\n\n ㅇ 전환 추진 중\n\n"
         "| 붙임 1 | | 상세 |\n| --- | --- | --- |\n\n"
         " ㅇ 검정관리팀이 별도로 관리한다")
    assert "plan-subject" not in _rules(t)
