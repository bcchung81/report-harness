"""하네스 실전 점검 도구 — 헤드리스 실행 없이 채점부만 검증한다(CI에는 claude CLI가 없다)."""
import json, pathlib, sys, importlib.util

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("smoke_pipeline", ROOT / "scripts/smoke_pipeline.py")
sp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sp)

DRAFT = ("시범운영 결과 보고\n< '26. 9. 25.(금), 경영기획본부 AI디지털심화팀 >\n\n□ 개 요\n\n"
         " ㅇ **(요지)** 검수 시간을 포함해도 건당 45분이 줄어 전사 확대를 경영회의에 상정\n")


def test_score_reports_missing_work_and_undelivered_runs(tmp_path):
    run = tmp_path / "run1"
    (run / "reports").mkdir(parents=True)
    assert sp.score(run)["work_dirs"] == 0 and sp.score(run)["delivered"] is False
    wd = run / "reports/20260925/0900_시험"
    wd.mkdir(parents=True)
    (wd / "00_context.md").write_text("# 맥락\n", encoding="utf-8")
    (wd / "20_draft.md").write_text(DRAFT, encoding="utf-8")
    (run / "session.json").write_text(json.dumps({"num_turns": 12, "total_cost_usd": 0.5}), encoding="utf-8")
    s = sp.score(run)
    assert s["work_dirs"] == 1 and s["num_turns"] == 12 and s["delivered"] is False     # hwpx가 없으면 미인도
    assert s["craft_missing"] == ["context", "analysis", "outline"] and "lint_ok" in s
    assert sp.summarize([s]).splitlines()[0].startswith("run | delivered")


def test_fixture_and_prompt_stay_isolated():
    """가상 자료임을 밝히고, 요청문이 게이트에 미리 답하며 리뷰어를 띄우지 않게 한다."""
    assert "가상 자료" in sp.FIXTURE
    assert "AskUserQuestion" in sp.PROMPT and "review_server" in sp.PROMPT and "reports_dir" in sp.PROMPT


def test_preflight_rejects_rule_variants_that_drop_seed_numbers(tmp_path):
    """판본에서 시드 규칙 번호를 빼면 첫 단계 sync_rules가 되살려 A/B가 무효 — 실행 전에 막는다(리뷰 #4)."""
    seed = (ROOT / "skills/report-pipeline/references/rules-seed.md").read_text(encoding="utf-8")
    variant = tmp_path / "slim.md"
    variant.write_text("\n".join(l for l in seed.splitlines() if not l.startswith("- R054 ")) + "\n", encoding="utf-8")
    errors = sp.preflight(variant, allow_stale=True)
    assert any("시드 번호 1개" in e and "R054" in e for e in errors)
    same = tmp_path / "same.md"
    same.write_text(seed, encoding="utf-8")
    assert not any("시드 번호" in e for e in sp.preflight(same, allow_stale=True))


def test_run_refuses_a_folder_with_old_results(tmp_path):
    """같은 --out을 다시 쓰면 옛 결과를 새 실행으로 채점했다 — 실행 전에 거부한다(리뷰 #4)."""
    run = tmp_path / "run1"
    (run / "reports").mkdir(parents=True)
    import pytest
    with pytest.raises(FileExistsError):
        sp.run_once(run)


def test_session_error_is_never_delivered(tmp_path):
    """세션이 오류로 끝났으면(또는 기록이 없으면) 산출물이 있어도 인도로 세지 않는다(리뷰 #4)."""
    run = tmp_path / "run1"
    (run / "reports").mkdir(parents=True)
    (run / "session.json").write_text(json.dumps({"is_error": True}), encoding="utf-8")
    s = sp.score(run)
    assert s["session_ok"] is False and s["delivered"] is False
    assert sp.main(["--score-only", str(tmp_path / "없음")]) == 2
    assert sp.main(["--score-only", str(run)]) == 1                       # 실행 폴더 하나도 받는다 — 미인도라 1
