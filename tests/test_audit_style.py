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


# ── '26.8.15 사용자 지적 4건 회귀 (R003·R045·R076·R077) ────────────────────

def test_confidence_tag_in_body_detected():
    """R003 — [확정]·[추정]은 작업 표기이며 인도본 본문에 노출되면 안 된다."""
    v, _ = audit_text(OK_HEAD + "□ 추진 배경\n\n ㅇ **(공통 과제)** 자료가 흩어져 과제 수행 불가 [확정]\n")
    assert "confidence-tag-in-body" in rules(v)


def test_confidence_tag_allowed_in_annex():
    """붙임 「확인 방법과 범위」에서 근거 범위를 밝히는 것은 허용한다."""
    doc = OK_HEAD + "□ 추진 배경\n\n| 붙임 2 | | 근거 출처 |\n|---|---|---|\n\n□ 확인 방법과 범위\n\n ㅇ **(법령 원문)** 원문 대조 [확정]\n"
    v, _ = audit_text(doc)
    assert "confidence-tag-in-body" not in rules(v)


def test_section_order_inversion_detected():
    """R076 — 「추진 방법」(5)이 「추진 과제」(3)보다 앞서면 서사 역전."""
    doc = OK_HEAD + "□ 추진 배경\n\n□ 추진 방법\n\n□ 추진 과제(안)\n"
    v, _ = audit_text(doc)
    assert "section-order" in rules(v)


def test_section_order_correct_passes():
    doc = OK_HEAD + "□ 추진 배경\n\n□ 현황 및 문제점\n\n□ 추진 과제(안)\n\n□ 기대 효과\n\n□ 추진 방법\n\n□ 향후 계획\n"
    v, _ = audit_text(doc)
    assert "section-order" not in rules(v)


def test_article_numbers_in_body_detected():
    """R077 — 본문 조문 나열 3개소 이상이면 붙임 대조표로 배출."""
    body = "".join(f" ㅇ **(근거 {n})** 시행령 제12{n}조제2항제2호에 따라 배정\n\n" for n in (1, 2, 3))
    v, _ = audit_text(OK_HEAD + "□ 현황 및 문제점\n\n" + body)
    assert "article-in-body" in rules(v)


def test_article_numbers_in_annex_exempt():
    """붙임의 근거 법령 대조표는 조문이 본문이므로 대상이 아니다."""
    body = "".join(f" ㅇ **(근거 {n})** 시행령 제12{n}조제2항제2호에 따라 배정\n\n" for n in (1, 2, 3))
    doc = OK_HEAD + "□ 추진 배경\n\n| 붙임 2 | | 근거 법령 |\n|---|---|---|\n\n□ 본문 서술의 근거 조문\n\n" + body
    v, _ = audit_text(doc)
    assert "article-in-body" not in rules(v)


# ── R080: 절 안 종결 명사 반복 ────────────────────────────────────────────────

def test_ending_repeat_detected():
    """R080 — 한 절에서 같은 종결 명사가 3회면 violation."""
    body = "".join(f" ㅇ **(항목 {n})** 상대 기관이 보유한 자료의 제공 조건을 회의에서 확인\n\n"
                   for n in (1, 2, 3))
    v, _ = audit_text(OK_HEAD + "□ 검토 사항\n\n" + body)
    assert "ending-repeat" in rules(v)


def test_ending_repeat_in_annex_exempt():
    """붙임(회의록·대조표)의 종결 반복은 자료 성격이라 R080 대상이 아니다.

    R074가 audit_style violation 0을 초안 확정 조건으로 못박은 뒤로, 붙임 전수 데이터가
    본문 산문 규칙에 걸려 게이트를 막는 구도였다 — article-in-body·confidence-tag와
    같은 층위의 제외로 맞춘다."""
    body = "".join(f" ㅇ **(항목 {n})** 상대 기관이 보유한 자료의 제공 조건을 회의에서 확인\n\n"
                   for n in (1, 2, 3))
    doc = OK_HEAD + "□ 추진 배경\n\n| 붙임 1 | | 회의 결과 |\n|---|---|---|\n\n□ 협의 경과\n\n" + body
    v, w = audit_text(doc)
    assert "ending-repeat" not in rules(v) and "ending-repeat" not in rules(w)


def test_ending_repeat_twice_is_warning():
    """2회는 문서 유형상 합법일 수 있어 warning으로만 낸다."""
    body = "".join(f" ㅇ **(항목 {n})** 상대 기관이 보유한 자료의 제공 조건을 회의에서 확인\n\n"
                   for n in (1, 2))
    v, w = audit_text(OK_HEAD + "□ 검토 사항\n\n" + body)
    assert "ending-repeat" not in rules(v)
    assert "ending-repeat" in rules(w)


def test_ending_repeat_resets_per_section():
    """절이 바뀌면 집계도 초기화된다 — 절마다 2회씩은 violation이 아니다."""
    blk = "".join(f" ㅇ **(항목 {n})** 상대 기관이 보유한 자료의 제공 조건을 회의에서 확인\n\n"
                  for n in (1, 2))
    doc = OK_HEAD + "□ 추진 배경\n\n" + blk + "□ 검토 사항\n\n" + blk
    v, _ = audit_text(doc)
    assert "ending-repeat" not in rules(v)


def test_varied_endings_pass():
    """행위 명사로 갈아 쓴 문구는 통과한다."""
    doc = (OK_HEAD + "□ 검토 사항\n\n"
           " ㅇ **(안테나 정보)** 상대 기관의 보유 여부와 제공 가능 조건을 회의에서 확인\n\n"
           " ㅇ **(허가 자료)** 위성 관련 허가 정보의 제공 주체와 제출 가능 여부를 협의\n\n"
           " ㅇ **(기관별 수요)** 업무 수요 표에서 비어 있는 상대 기관 쪽 항목을 보완\n")
    v, w = audit_text(doc)
    assert "ending-repeat" not in rules(v) and "ending-repeat" not in rules(w)


# ---------------------------------------------------------------- 쉬운 말·두괄식 (R091)
def _w(text):
    import audit_style as au
    return [x["rule"] for x in au.audit_text(text)[1]]


BASE = "개선 추진 보고\n< '26. 9. 25.(목), 경영기획본부 AI디지털심화팀 >\n\n□ 개 요\n\n"


def test_plain_words_come_from_style_guide_and_report_once_per_term():
    import audit_style as au
    assert au.PLAIN_WORDS.get("파생값") == "계산값" and "AI" in au.ABBR_OK
    rules = _w(BASE + "ㅇ **(수집)** 파생값은 파생값 계산으로 처리\n\nㅇ **(검증)** 파생값을 대조\n")
    assert rules.count("plain-word") == 1


def test_annex_is_not_checked_for_plain_words():
    text = BASE + "ㅇ **(수집)** 계산값을 모아 보고\n\n| 붙임 1 | | 상세 |\n| --- | --- | --- |\n\nㅇ **(구성)** 파생값·스크립트 사양\n"
    assert "plain-word" not in _w(text)


def test_abbreviation_needs_korean_explanation_once():
    assert "abbr-unexplained" in _w(BASE + "ㅇ **(인정)** T1만 실적으로 인정\n")
    assert "abbr-unexplained" not in _w(BASE + "ㅇ **(인정)** 시스템 기록(T1)만 실적으로 인정\n")
    assert "abbr-unexplained" not in _w(BASE + "ㅇ **(인정)** AI 처리 건수로 인정\n")      # 허용 약어


def test_clause_chain_and_history_and_background_lead():
    chained = BASE + "ㅇ **(수집 착수)** 보존 기간을 조회해 범위를 정한 뒤, 기록지를 배포하고 수집 착수\n"
    assert {"clause-chain", "history-narration"} <= set(_w(chained))
    assert "lead-not-conclusion" in _w(BASE + "ㅇ **(추진 배경)** 그간 부서별로 따로 산정해 비교가 어려움\n")
    assert "lead-not-conclusion" not in _w(BASE + "ㅇ **(측정 기준)** 18건을 4개 유형으로 나눠 성과를 보고\n")


def test_skeleton_lists_section_titles_and_first_points():
    import audit_style as au
    sk = au.skeleton(BASE + "ㅇ **(결론)** 표준 기록으로 성과를 산정\n\nㅇ 둘째\n\n□ 향후 계획\n\nㅇ 10월 1차 산정\n\n"
                     "| 붙임 1 | | 상세 |\n| --- | --- | --- |\n\n□ 붙임 절\n")
    assert [x["section"] for x in sk] == ["개 요", "향후 계획"]
    assert sk[0]["first"].startswith("ㅇ (결론) 표준 기록")
