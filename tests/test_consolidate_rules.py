"""rules 통합 lint 회귀 (R068).

규칙 축적을 통폐합으로 되돌리는 장치가 살아 있는지 확인한다. 이 테스트가 실패하면
`consolidate_rules.py --check`를 돌려 원인을 보고, 통폐합 후 `--mark`로 마커를 갱신한다.
"""
import pathlib
import importlib.util

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "consolidate", ROOT / "skills/report-pipeline/scripts/consolidate_rules.py")
cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cr)

# 운영 축적본이 있으면 그것을, 없으면(fresh clone·CI) 배포 시드를 검사한다 —
# 시드도 같은 규약(마커·등급·참조 정합)을 지켜야 새 설치가 깨끗한 상태로 출발한다.
_OP = ROOT / "report/_harness/rules.md"
RULES = _OP if _OP.exists() else ROOT / "skills/report-pipeline/references/rules-seed.md"


def test_rule_parser_covers_every_rule():
    """다중 태그(`[draft][export]`) 규칙도 본문까지 파싱된다.

    회귀 대상: `\\[([^\\]]+)\\]` 정규식이 다중 태그를 못 잡아 6건이 집계에서 조용히
    빠졌고, 그 상태로 잰 '규칙 59개·4,600토큰'이 두 턴간 보고됐다 ('26.8.7).
    """
    a = cr.analyze(RULES)
    assert not a["parse_gap"], f"본문 파싱 실패: {a['parse_gap']}"


def test_no_dead_rule_references():
    """규칙이 가리키는 R0NN이 rules.md 또는 rules-history.md에 실재한다."""
    a = cr.analyze(RULES)
    assert not a["dead_refs"], f"죽은 참조: {a['dead_refs']}"


def test_every_rule_carries_evidence_grade():
    """근거란이 있는 규칙은 [실측]·[추론]·[관례] 등급을 단다 (등급 없이 승격 금지)."""
    a = cr.analyze(RULES)
    assert not a["ungraded"], f"근거 등급 누락: {a['ungraded']}"


def test_no_oversized_rule_bodies():
    """규칙 본문은 1,000자 이내 — 초과분은 경위를 rules-history.md로 이관한다.

    rules-history 스스로 정한 정책의 성문화다. 구 시드에는 1,000자 초과 변형이
    22건까지 쌓여 '길어서 안 읽히는' 상태가 재발했었다(운영본 동기화로 해소)."""
    a = cr.analyze(RULES)
    assert not a["oversized"], f"본문 비대: {a['oversized']}"


def test_growth_within_consolidation_limit():
    """마지막 통합 이후 규칙 증가가 임계(10건) 미만이다.

    임계를 넘으면 통폐합을 수행하고 `consolidate_rules.py --mark`로 마커를 갱신해야
    통과한다 — 축적만 하고 정리하지 않는 상태를 구조적으로 막는다.
    """
    a = cr.analyze(RULES)
    assert a["growth"] < a["limit"], (
        f"마지막 통합({a['marked_at']}) 이후 {a['growth']}건 증가 — "
        f"통폐합 후 `consolidate_rules.py --mark` 실행 필요")


def test_cross_references_survive_past_r099(tmp_path):
    """R100 이후에도 교차참조가 잡혀야 한다.

    참조 스캔만 `R0\\d\\d`로 자리수가 못박혀 있어 R100부터는 피참조가 0으로 집계됐다.
    그러면 살아서 참조받고 있는 규칙이 '통합 후보(피참조 0)'로 뒤집혀 삭제 권고가 나간다 —
    이 스크립트가 막으려던 바로 그 사고다. 규칙은 두 달에 43건꼴로 늘어 R100 도달이
    예정돼 있었다.
    """
    p = tmp_path / "rules.md"
    p.write_text(
        "- R100 [export] **[폐지]** 배너 규칙 (근거[실측]: x)\n"
        "- R105 [export] R100을 흡수해 대체한다 (근거[실측]: x)\n"
        "- R106 [export] R404를 가리킨다 (근거[실측]: x)\n",
        encoding="utf-8")
    a = cr.analyze(p)
    assert "R100" not in a["candidates"], f"참조받는 규칙이 통합 후보로 잡힘: {a['candidates']}"
    assert a["dead_refs"] == ["R404"], a["dead_refs"]


def test_per_tag_preflight_size_counts_multi_tag_rules(tmp_path):
    """태그별 프리플라이트 분량 — 다중 태그 규칙([draft][export])은 두 단계 모두에 센다('26.9.25 문맥 비용 추적)."""
    p = tmp_path / "rules.md"
    p.write_text("- R001 [draft] 가나다\n- R002 [draft][export] 라마\n- R003 [export] 바\n", encoding="utf-8")
    a = cr.analyze(p)
    assert a["per_tag"] == {"draft": (2, 5), "export": (2, 3)}


def test_local_rule_band_is_not_counted_as_growth(tmp_path):
    """설치자 로컬 규칙(R9NN)은 통합 증가분에 넣지 않는다 — R901 하나로 '+813' 영구 경고가 났다('26.9.25)."""
    p = tmp_path / "rules.md"
    p.write_text("# rules\n<!-- consolidated-at: R010 -->\n- R011 [draft] 시드 규칙 (근거[실측]: x)\n"
                 "- R901 [draft] 설치자 로컬 규칙 (근거[관례]: x)\n", encoding="utf-8")
    a = cr.analyze(p)
    assert a["latest"] == "R011" and a["growth"] == 1
