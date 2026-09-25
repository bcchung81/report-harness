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


def test_diagram_card_sentences_warn_on_formula_and_count_fragments(tmp_path):
    """R093 — 도식 카드 문장도 공문서 문장이다('26.9.25 게이트② f11 등호 정의식·f12 숫자 나열)."""
    import json
    import audit_style as au
    (tmp_path / "figures").mkdir()
    spec = {"type": "flow", "steps": [
        {"head": "과제 배정", "body": ["처리시간 = 시스템 속도만 측정", "과제당 3개, 18건 54개"]},
        {"head": "실적 수집", "body": ["18건 모두 같은 양식으로 실적 산출", "처리 1건을 1행 10칸에 적는 표준 로그로 수집"]}]}
    (tmp_path / "figures" / "흐름.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    md = tmp_path / "20_draft.md"
    text = BASE + "[ 흐름 ]\n\n도해: 흐름\n"
    w = au.audit_figures(md, text)
    assert sorted(rules(w)) == ["diagram-formula", "diagram-fragment"]
    assert all(x["line"] == text.splitlines().index("도해: 흐름") + 1 for x in w)
    assert not any("실적 산출" in x["text"] or "표준 로그로 수집" in x["text"] for x in w)
    assert au.audit_figures(tmp_path / "없는폴더" / "20_draft.md", text) == []      # 명세 없는 환경(웹앱)


def test_external_citation_needs_source_line():
    """R092 — 외부 자료를 가리키는 ※ 줄은 '※ 자료:' 출처 줄을 단다('26.9.25 1127 검증: 규격 출처 줄 0건)."""
    cite = "※ 미국 AI 평가 연구기관(METR)의 무작위 실험에서 체감과 실제 소요시간이 반대\n\n"
    src = "※ 자료: METR, 「Measuring the Impact of Early-2025 AI」(2025)\n"
    assert "source-line-missing" in _w(BASE + cite)
    assert "source-line-missing" not in _w(BASE + cite + src)
    table = "[ 해외 사례 ]\n\n| 구 분 | 결 과 |\n| --- | --- |\n| METR | 19% 증가 |\n\n"
    assert "source-line-missing" not in _w(BASE + cite + table + src)       # 표·캡션을 건너 출처 줄을 찾는다
    assert "source-line-missing" in _w(BASE + cite + "ㅇ **(다음 요지)** 다음 요지 문장\n\n" + src)   # 다음 ㅇ를 넘지 않는다
    inline = "※ 과제는 「공공부문 초거대 AI 도입·활용 가이드라인 2.0」(디지털플랫폼정부위원회, '25.4) 71쪽의 13분류에 배정\n"
    assert "source-line-missing" not in _w(BASE + inline)                   # 자료명·연도·쪽이 한 줄에 다 있으면 출처 줄
    # 출처 줄은 자료명(원어 제목·약칭)이라 약어·종결 검사에서 뺀다
    v, w = audit_text(BASE + "※ 자료: 한국지능정보사회진흥원, 「가이드」 부록 05 성과지표 POOL(2023) NO.2 재구성\n")
    assert "abbr-unexplained" not in rules(w) and v == []


def test_noun_endings_are_not_forbidden_endings():
    """'포함·위임·책임·모임'은 명사 자체의 끝이지 ~함·~임 종결이 아니다('26.9.1 교훈). 진짜 위반은 계속 잡는다."""
    for ok in ("처리시간에 포함", "부서장에게 위임", "운영 부서가 산출 책임", "협의 모임", "다음"):
        v, _ = audit_text(BASE + f"ㅇ **(측정 기준)** 성과 측정은 {ok}\n")
        assert "ending-forbidden" not in rules(v), ok
    for bad in ("처리가 불가함", "결과를 확인함", "할 것임", "해당 없음", "대상이 같음", "완료됨"):
        v, _ = audit_text(BASE + f"ㅇ **(측정 기준)** 성과 측정은 {bad}\n")
        assert "ending-forbidden" in rules(v), bad


def test_question_documents_use_their_own_title_and_section_vocab():
    """질의서·요청 문서는 단신 요약보고 어휘 밖이지만 합법이다('26.9.1 교훈 — title-no-suffix·offpool 4건)."""
    doc = ("장비 구매 절차 질의서\n< '26. 9. 1.(월), 경영기획본부 AI디지털심화팀 >\n\n□ 질의 배경\n\n"
           "ㅇ **(구매 방식)** 공시가격 단독공급 제품의 구매 절차를 확인\n\n□ 질의 사항\n\n"
           "ㅇ **(절차 확인)** 웹스토어 결제로 국가계약법 절차를 갈음할 수 있는지 확인\n")
    v, w = audit_text(doc)
    assert "title-no-suffix" not in rules(v) and "section-title-offpool" not in rules(w)


def test_one_syllable_stem_endings_are_still_forbidden():
    """'정함·전함·급함'(한 글자 줄기 ~하다)·'안임'(명사 + 서술격)은 명사 목록 밖이라 위반이다('26.9.25 코드 리뷰)."""
    for bad in ("평가 기준을 새로 정함", "개선 방향을 전함", "수요가 급함", "이것이 최종 안임"):
        v, _ = audit_text(BASE + f"ㅇ **(측정 기준)** {bad}\n")
        assert "ending-forbidden" in rules(v), bad


def test_broken_figure_spec_does_not_swallow_body_audit(tmp_path):
    """도식 명세가 깨져도(body: null) 본문 위반은 그대로 나온다 — 종전에는 TypeError로 감사가 통째로 멈췄다."""
    import json, subprocess
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "x.json").write_text(json.dumps({"type": "flow", "steps": [{"head": "x", "body": None}]}),
                                                 encoding="utf-8")
    md = tmp_path / "20_draft.md"
    md.write_text(BASE + "ㅇ **(현황 진단)** 자료가 흩어져 과제 수행이 불가함\n\n도해: x\n", encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts/audit_style.py"
    out = json.loads(subprocess.run([sys.executable, str(script), str(md)], capture_output=True, text=True).stdout)
    assert "ending-forbidden" in rules(out["violations"])


def test_later_citation_source_does_not_cover_earlier_citation():
    """뒤 인용의 '※ 자료:' 줄이 앞의 출처 없는 인용을 덮지 않는다('26.9.25 코드 리뷰)."""
    text = (BASE + "※ 영국 정부 실험에서 설문 절감만 보고\n\n※ OECD 통계로 본 도입률 비교\n\n"
            "※ 자료: OECD, 「AI 도입 통계」('24), 12쪽\n")
    w = [x for x in audit_text(text)[1] if x["rule"] == "source-line-missing"]
    assert len(w) == 1 and "영국" in w[0]["text"]


def test_note_line_and_shared_source_line_count_as_sourced():
    """인용에 붙은 '※ 주:' 단서 줄은 새 인용이 아니고, 잇단 인용은 출처 줄 하나에 ';'로 함께 적을 수 있다
    ('26.9.25 코드 리뷰 #2 — 종전에는 둘 다 source-line-missing 오탐)."""
    note = (BASE + "※ 영국 정부 실험에서 설문 절감만 보고\n\n※ 주: 해외 사례는 '24년 기준\n\n"
            "※ 자료: 영국 과학혁신기술부, 「AI 실험 보고서」('24)\n")
    assert "source-line-missing" not in _w(note)
    shared = (BASE + "※ 미국 연방 기관의 도입 사례 요약\n\n※ 영국 정부 실험에서 설문 절감만 보고\n\n"
              "※ 자료: 미국 관리예산처, 「AI 활용 보고」('24); 영국 과학혁신기술부, 「AI 실험 보고서」('24)\n")
    assert "source-line-missing" not in _w(shared)


def test_common_nouns_ending_in_ham_im_pass():
    """'운임·주임·상임·보관함'처럼 흔한 명사는 목록에 두어 막지 않는다('26.9.25 코드 리뷰 #2 — 명사 목록 전환 뒤 회귀)."""
    for ok in ("화물 운임", "위원 비상임", "민원 보관함", "담당 주임"):
        v, _ = audit_text(BASE + f"ㅇ **(측정 기준)** 산정 대상은 {ok}\n")
        assert "ending-forbidden" not in rules(v), ok


def test_internal_codes_laws_and_emphasis_are_not_external_citations():
    """외부 인용은 외부 주체 + 근거어가 함께 있을 때만 — 운영 초안 14건 재점검에서 12건이 오탐이었다('26.9.25):
    내부 약호 괄호, 법령명, 강조 괄호, 내부 문서 참조, 국가명만 든 판단, '※ 출처:' 줄."""
    fp = ("※ 구조화 설문·만족도(T3)는 반기 1회 수집하되 실적의 단독 근거로 불인정",
          "※ 상담·응답형 과제의 반려(REJ)는 답변 오류로 재응답이 필요했던 건",
          "※ 「인공지능 및 데이터 기반 행정 활성화에 관한 법률」('26.8월 시행)은 현황 제출만 규율",
          "※ 처리 건수 30건 미만 과제는 순절감을 「잠정」으로 표기해 다음 분기에 재산출",
          "※ 실무 상세는 「측정·산출 기준(안) 상세본」 별도 참조",
          "※ \"프랑스 제품\"도 \"중국 제품\"도 단독으로는 부정확하며, 인증 요건은 어느 쪽에나 동일",
          "※ 출처: 디지털플랫폼정부위원회, 「공공부문 초거대 AI 도입·활용 가이드라인 2.0」('25.4월) 그림 14")
    for line in fp:
        assert "source-line-missing" not in _w(BASE + line + "\n"), line
    tp = ("※ 재작업 소요는 음(-)의 절감으로 계상해 상쇄(영국 기업통상부 조정 규칙 준용)",
          "※ 해당 업체는 국내 24건·미국 80건의 인증 실적 보유",
          "※ 「2024 공공부문 AI 실태조사」에서 도입률 38%")
    for line in tp:
        assert "source-line-missing" in _w(BASE + line + "\n"), line


def test_numbered_section_with_subtitle_uses_pool_word():
    """'□ 검토 결과 ① : 부제'는 풀 어휘 '검토 결과'에 번호·부제가 붙은 것이다('26.9.25 운영 초안 재점검 — 4건 오탐)."""
    for title in ("검토 결과 ① : 발송 제품은 동일", "검토 결과 ②", "검토 결과: 요약"):
        _, w = audit_text(f"점검 결과 보고\n< '26. 9. 25.(금), 경영기획본부 AI디지털심화팀 >\n\n□ {title}\n\n"
                          "ㅇ **(판단)** 두 제품의 인증 요건이 같아 추가 시험 없이 도입 가능\n")
        assert "section-title-offpool" not in rules(w), title
    _, w = audit_text("점검 결과 보고\n< '26. 9. 25.(금), 경영기획본부 AI디지털심화팀 >\n\n□ 작성 개요\n\n"
                      "ㅇ **(판단)** 두 제품의 인증 요건이 같아 추가 시험 없이 도입 가능\n")
    assert "section-title-offpool" in rules(w)


def test_korean_name_with_acronym_and_method_titles_are_external():
    """한글 이름 + 괄호 원어·약칭(맥킨지(McKinsey)·진흥원(NIA))은 외부 주체이고, '방법·기법'으로 끝나는 자료명은
    법령이 아니다('26.9.25 코드 리뷰 #3 — 두 신호 전환 뒤 놓치던 줄)."""
    for line in ("※ 맥킨지(McKinsey) 보고서는 생산성 향상 폭을 최대 40%로 추정",
                 "※ 한국지능정보사회진흥원(NIA) 조사 결과 도입률 38%",
                 "※ 「AI 성과 측정 방법」(영향평가원)에서 절감률 20%"):
        assert "source-line-missing" in _w(BASE + line + "\n"), line
    assert "source-line-missing" not in _w(BASE + "※ 사람 이관(ESC)은 반려가 아닌 이관율로 별도 집계\n")


def test_r054_result_report_sections_are_in_the_pool():
    """R054가 정한 결과보고 절 구성의 제목은 모두 절 어휘 풀에 있다 — 규칙대로 쓴 초안을 어휘 밖으로 잡으면 안 된다
    ('26.9.25 하네스 실전 점검: '□ 추진 성과'가 section-title-offpool로 걸렸다)."""
    import re
    import audit_style as au
    seed = (Path(__file__).resolve().parents[1] / "skills/report-pipeline/references/rules-seed.md").read_text(encoding="utf-8")
    line = next(l for l in seed.splitlines() if l.startswith("- R054 "))
    order = re.search(r"\*\*결과보고 절 구성 표준 — ([^*]+)\*\*", line).group(1)
    titles = [t.strip() for t in order.split("→")]
    assert len(titles) == 5 and all(t in au.SECTION_POOL for t in titles), titles


def test_title_that_wraps_to_two_lines_is_warned():
    """제목이 제목표 한 줄(24pt)을 넘으면 집필 단계에서 경고한다 — 변환 뒤에야 2쪽이 된 것을 알고 승인된 초안을
    줄이던 것을 당긴다('26.9.25 하네스 실전 점검). 후처리·리뷰 화면과 같은 fit_title로 잰다."""
    body = "\n< '26. 9. 25.(금), 경영기획본부 AI디지털심화팀 >\n\n□ 개 요\n\nㅇ **(요지)** 검수 시간을 포함해도 건당 45분 절감을 확인\n"
    _, w = audit_text("작성 시간 단축 효과를 확인한 AI 문서 초안 도우미 시범운영 결과 보고" + body)
    assert "title-two-lines" in rules(w)
    _, w = audit_text("시간을 줄인 AI 초안 도우미 시범운영 결과 보고" + body)
    assert "title-two-lines" not in rules(w)


def test_result_report_flow_is_not_an_order_inversion():
    """결과보고의 '개 요 → 추진 성과 → 검토 결과 → 향후 계획'은 역전이 아니다(R054·R076, '26.9.25 실전 점검 채점)."""
    doc = ("시범운영 결과 보고\n< '26. 9. 25.(금), 경영기획본부 AI디지털심화팀 >\n\n"
           + "".join(f"□ {t}\n\nㅇ **(요지)** 검수 시간을 포함해 건당 45분 절감을 확인\n\n"
                     for t in ("개 요", "추진 성과", "검토 결과", "향후 계획")))
    v, _ = audit_text(doc)
    assert "section-order" not in rules(v)


def test_title_check_measures_curly_quotes_like_the_delivered_hwpx():
    """제목 한 줄 검사는 kordoc이 바꾼 둥근따옴표(전각)로 잰다 — 곧은따옴표(반각)로 재면 인도본에서 2줄인 제목을
    한 줄로 오판했다('26.9.25 코드 리뷰 #4)."""
    body = "\n< '26. 9. 25.(금), 경영기획본부 AI디지털심화팀 >\n\n□ 개 요\n\nㅇ **(요지)** 검수 시간을 포함해도 건당 45분 절감을 확인\n"
    _, w = audit_text("'26년 'AI 비서' 시범운영 결과와 확대 방안 보고" + body)
    assert "title-two-lines" in rules(w)
