"""규칙 시드 동기화 — 새 규칙은 설치자 운영본에 들어가고, 설치자의 축적·수정은 지워지지 않는다('26.9.25)."""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import sync_rules as sr

SEED = "# rules\n\n- R001 [draft] 첫 규칙\n- R002 [export] 둘째 규칙(정정본)\n- R003 [draft][export] 새 규칙\n"
STATE = "# rules\n\n- R001 [draft] 첫 규칙\n- R002 [export] 둘째 규칙\n- R901 [draft] 설치자가 쌓은 규칙\n"


def test_plan_separates_new_changed_and_local_rules():
    assert sr.plan(STATE, SEED) == {"added": ["R003"], "changed": ["R002"], "local_only": ["R901"]}


def test_apply_appends_only_seed_only_rules(tmp_path, capsys):
    state, seed = tmp_path / "rules.md", tmp_path / "seed.md"
    state.write_text(STATE, encoding="utf-8")
    seed.write_text(SEED, encoding="utf-8")
    assert sr.main(["--apply", "--state", str(state), "--seed", str(seed)]) == 0
    text = state.read_text(encoding="utf-8")
    assert text.startswith(STATE) and text.endswith("- R003 [draft][export] 새 규칙\n")     # 기존 줄은 그대로
    assert "- R002 [export] 둘째 규칙\n" in text and "정정본" not in text                  # 바뀐 규칙은 보고만
    out = json.loads(capsys.readouterr().out)
    assert out["added"] == ["R003"] and out["changed"] == ["R002"] and out["local_only"] == ["R901"]
    assert sr.main(["--apply", "--state", str(state), "--seed", str(seed)]) == 0             # 두 번째는 할 일 없음
    assert json.loads(capsys.readouterr().out)["added"] == []


def test_first_run_copies_seed(tmp_path, capsys):
    state, seed = tmp_path / "new" / "rules.md", tmp_path / "seed.md"
    seed.write_text(SEED, encoding="utf-8")
    assert sr.main(["--state", str(state), "--seed", str(seed)]) == 0
    assert state.read_text(encoding="utf-8") == SEED and json.loads(capsys.readouterr().out)["seeded"] is True


def test_real_seed_parses_every_rule():
    """배포 시드의 규칙 줄을 빠짐없이 읽는다 — 다중 태그 규칙(R090 [draft][export] 등)도 포함."""
    text = sr.SEED.read_text(encoding="utf-8")
    ids = list(sr.rules(text))
    assert ids and ids == sorted(set(ids), key=ids.index) and "R094" in ids and "R090" in ids
