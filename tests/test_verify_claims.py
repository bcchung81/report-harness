"""패널 주장 수치 대조 회귀 (cross-verify ③단계).

픽스처는 '26.8.27 실제 교차검증에서 나온 것이다. 패널 하나가 원문에 없는 수치를 지어냈고
(14.2배), 원문에 있는 값을 엉뚱한 과제에 붙였다('#4가 분모 2,000h를 독식' — 실제 독식은 #5).
범용 다중모델 도구는 이것을 통과시킨다. 이 테스트가 지키는 것은 **그 두 유형이 계속 잡히는
것**이다.
"""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "verify_claims", ROOT / "skills/cross-verify/scripts/verify_claims.py")
vc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vc)

# 원문 축약 — 판정에 관여하는 줄만 옮기되 **절 사이 거리는 원문대로 남긴다**.
# 압축하면 모든 값이 모든 앵커와 가까워져 귀속 판정이 통째로 무력화된다(실제 원문에서
# #4와 2,000h는 527자 떨어져 있고, 이것이 오귀속을 검출하는 근거다).
SOURCE = """
□ 적용 결과

 ㅇ (과제 배정) 과제 20건 적용 결과 절감 실적형 5건·운영 실적형 12건·측정 제외 3건이며,
    구분별 해당 과제와 산출 시점은 아래 표와 같이 배정

| 구 분 | 과제 수 | 해당 과제 | 산출 시점 |
| 문서·자료 처리 | 5 | #1 방송 심사자료·#2 시험문제 검토·#3 자산운용 보고·#4 응시서류심사·#5 NCS 자동매칭 | 9월(#1)·12월(4건) |
| 감시·경보 | 4 | #6 무전기 모니터링·#7 안전 신호등·#8 말벌탐지·#9 KCA-SCAN | 9월(#7)·10월(#8)·12월(#6) |
| 판독·진단 | 2 | #10 어선표지판 판독·#11 SafeVision | 9월부터(#10)·배치 실행 시(#11) |
| 응답·안내 | 4 | #12 AI 어드바이저·#13 청렴감사 챗봇·#14 5G특화망 포털·#15 민원상담 보조 | 운영 개시 후 |
| 예측·배정 | 2 | #16 선박 탑승 예측·#17 출장 배정 도우미 | 9월부터(#17) |
| 측정 제외 | 3 | #18 민생위기 조기경보·#19 알쓸업무ZIP·#20 홍보 콘텐츠 | 정성 사례 |

□ 향후 계획

| 구 분 | 지표명(단위) | '25년 실적(구기준 / 신기준 환산) | '26년 목표 |
| 대표 | AI 순절감시간(시간) | 12,754 / 899 | 1,000 |
| 대표 | 업무시간 단축률(%) | 75.1 / 46.8(총량 1,921h) | 50(총량 2,000h) |

[ 경영평가 제출용 전사 총괄 보고 축 ]

| 보고 축 | 대상 과제 | 전사 합산 방식 | 제출 문구에 반드시 병기 |
| 직원 업무시간 | 절감 5건 | 순절감 합산, 단축률 = 순절감 나누기 도입 전 총량 | 과제 수·증거 등급 구성 |
| 대국민 서비스 | 응답·안내 4건 | 이관율 분자 나누기 분모 | 응답 건수·재문의율 |
| 운영 품질 | 감시·판독·예측 8건 | 처리 건수 합산 | 검증 표본 수 |

[ 월별 추진 계획 ]

| 시 기 | 추진 사항 | 확보되는 산출물 |
| 9월 | 측정설계 승인, 부서 고지·노사협의, 검증 표본 설계 승인 | 도입 전 투입시간 |
| 10월 | 실측 2차와 제3자 재측정, 기록 재구성 승인 판정 | 절감 산출 모집단 확정 |
| 11월 | 대장 중간 집계, 부서 재계산·협의체 심의 | 대장 중간본, 심의 결과 |
| 12월 | 외부 제3자 재산출 검증, 실적 확정, 단절점 선언 | 확정 실적 |

 ㅇ (실측 착수) 도입 전 업무 소멸이 임박한 과제부터 순서대로 실측

   - #5 NCS 코드 자동매칭(진도 90%)이 1순위, #4 응시서류심사(11월 완료)가 2순위이며,
     실패한 과제는 순절감 미산출로 처리하고 처리 건수만 보고

| 붙임 1 | | 과제 20건 산출 대장 |

| No | 유형(구분) | 과제명 | 산출 시점·비고 |
| 11 | 운영(판독·진단) | SafeVision 안전진단 | 배치 실행 시. 부서 검증 계획(95% 목표) 활용 |
"""


def _kinds(panel_text, window=vc.DEFAULT_WINDOW):
    claims = vc.extract_claims(panel_text)
    return {(f["kind"], f["value"], f["anchor"]) for f in vc.audit(SOURCE, claims, window)}


def test_fabricated_number_is_caught():
    """원문 어디에도 없는 수치는 잡힌다 — 패널이 지어낸 '14.2배' 사례."""
    panel = "전년도에 14.2배 과대계상된 허위 실적을 제출했음을 시인하는 셈이다."
    assert ("수치-미검출", "14.2", None) in _kinds(panel)


def test_misattributed_number_is_caught():
    """수치는 원문에 있으나 다른 과제 것이면 잡힌다 — '#4가 2,000h 독식' 사례.

    이 유형이 가장 위험하다. 값 자체가 원문에 있어 단순 grep 검증은 통과시킨다."""
    panel = "| 단축률 | 닫히지 않음 | 특정 과제(#4 등)의 도입 전 총량이 분모(2,000h)를 독식 |"
    assert ("귀속-불일치", "2,000", "4") in _kinds(panel)


def test_table_cell_anchor_is_not_false_positive():
    """붙임 대장이 `| 11 |` 표 셀로 쓴 과제도 앵커로 읽어야 한다.

    본문 `#11` 형식만 보면 대장에만 있는 값이 전부 오탐된다 — SafeVision 95% 사례."""
    panel = "| #11 | SafeVision | 부서 검증 계획 95% 목표 미달 시 지표 왜곡 |"
    assert not [k for k in _kinds(panel) if k[1] == "95"]


def test_quantity_with_comma_is_not_read_as_year():
    """'2,000h'를 연도로 걸러 검사에서 통째로 빠뜨리면 안 된다."""
    assert vc.is_significant("2,000", "h")
    assert vc.is_significant("2000", "h")
    assert not vc.is_significant("2026", None)


def test_sentence_split_prevents_cross_sentence_attribution():
    """앞 문장의 과제 번호가 뒷 문장의 무관한 수치에 달라붙지 않아야 한다.

    실제 오탐: '#2·#3·#5가 불승인된다. … 1,000h 목표가 재설정된다'에서 1,000h가 #3에 귀속됐다."""
    panel = "#2·#3·#5가 T2 불승인된다. 그 결과 11월에 1,000h 목표가 재설정된다."
    assert not _kinds(panel)


def test_table_row_stays_one_unit():
    """표 행은 문장으로 쪼개지 않는다 — 셀 하나가 한 과제의 서술이다."""
    assert vc.units("| a. b. | c. d. |") == ["| a. b. | c. d. |"]
    assert len(vc.units("첫 문장이다. 둘째 문장이다.")) == 2


def test_grounded_panel_reports_clean():
    """원문 근거대로 쓴 패널은 미검증 0건이어야 한다 — 오탐이 잦으면 아무도 안 본다.

    종전 픽스처는 `목표 1,000h의 경계값`을 함께 달고도 통과했는데, 그건 근거가 있어서가
    아니라 `1,000h의`의 한글 경계에 걸려 **주장 추출 자체가 안 됐기 때문**이었다
    ('26.9.10 발견). 전사 목표값을 과제 앵커에 붙이는 것은 이 도구의 계약상 귀속-불일치가
    맞다(‘26.8.27 사건의 `#4가 2,000h를 독식`과 같은 형태) — 근거 있는 문장만 남긴다."""
    panel = "| #5 | NCS 자동매칭 | 진도 90%, 소멸 임박 |"
    assert not _kinds(panel)


def test_number_adjacent_to_hangul_is_extracted():
    r"""한글에 붙은 수치도 주장으로 잡는다 — 앞(`총3,500h`)·뒤(`3,500회의`) 모두.

    파이썬 `\w`가 한글을 포함해서 경계 검사가 이 형태를 통째로 걸러냈고, 지어낸 수치가
    주장 목록에 오르지도 않아 검사가 조용히 비어 있었다."""
    assert [c["value"] for c in vc.extract_claims("총3,500h를 소진")] == ["3,500"]
    assert [c["value"] for c in vc.extract_claims("3,500회의 처리")] == ["3,500"]
    # 앞뒤가 ASCII 식별자면 종전대로 수치가 아니다
    assert vc.extract_claims("abc123 로그") == []


def test_substring_does_not_ground_a_fabricated_number():
    """원문 `3,500h`가 패널의 `500h`를 근거로 인정하면 안 된다.

    근거 대조가 부분문자열 포함이라 정규화된 `3500` 안의 `500`이 통과했다 — 이 도구의
    유일한 탐지 수단이라 여기가 새면 검사 전체가 무의미해진다('26.9.10 실측)."""
    source = "ㅇ (총량) 전사 투입은 3,500h 규모로 집계\n"
    assert "500" not in vc.number_tokens(source)
    claims = vc.extract_claims("패널: 500h를 소진했다고 본다")
    kinds = [f["kind"] for f in vc.audit(source, claims, vc.DEFAULT_WINDOW)]
    assert kinds == ["수치-미검출"]
    # 원문에 실재하는 값은 그대로 통과한다
    ok = vc.extract_claims("패널: 3,500h 규모")
    assert not vc.audit(source, ok, vc.DEFAULT_WINDOW)


def test_cli_reports_findings_and_exits_nonzero(tmp_path, capsys):
    """CLI 경로 — 미검증 주장이 있으면 exit 1로 알린다."""
    src = tmp_path / "src.md"
    src.write_text(SOURCE, encoding="utf-8")
    panel = tmp_path / "panel.md"
    panel.write_text("전년도 대비 14.2배 과대계상이다.", encoding="utf-8")
    code = vc.main([str(src), "--panel", f"agy={panel}"])
    assert code == 1
    assert "14.2" in capsys.readouterr().out


def test_cli_rejects_malformed_panel_spec(tmp_path):
    """이름=경로 형식이 아니면 조용히 넘어가지 않는다."""
    src = tmp_path / "src.md"
    src.write_text(SOURCE, encoding="utf-8")
    assert vc.main([str(src), "--panel", "경로만적음.md"]) == 2


def test_render_marks_anchor_and_kind():
    """터미널 출력에 유형과 앵커가 남아야 사람이 원문을 찾아갈 수 있다."""
    report = {"source_chars": 1, "panels": {"agy": {"claims": 1, "ungrounded": [
        {"kind": "귀속-불일치", "value": "2,000", "unit": "h", "anchor": "4",
         "line": 40, "text": "…"}]}}}
    out = vc.render(report)
    assert "귀속-불일치" in out and "#4" in out and "L40" in out
