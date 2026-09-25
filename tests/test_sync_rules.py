"""규칙 시드 동기화 — 새 규칙은 설치자 운영본에 들어가고, 설치자의 축적·수정은 지워지지 않는다('26.9.25)."""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import sync_rules as sr

SEED = "# rules\n\n- R001 [draft] 첫 규칙\n- R002 [export] 둘째 규칙(정정본)\n- R003 [draft][export] 새 규칙\n"
STATE = "# rules\n\n- R001 [draft] 첫 규칙\n- R002 [export] 둘째 규칙\n- R901 [draft] 설치자가 쌓은 규칙\n"


def test_plan_separates_new_changed_and_local_rules():
    assert sr.plan(STATE, SEED) == {"added": ["R003"], "superseded": [], "collision": [], "changed": ["R002"],
                                    "local_only": ["R901"]}


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


def test_first_run_copies_seed_only_with_apply(tmp_path, capsys):
    """점검(--apply 없음)은 아무것도 쓰지 않는다 — 자가진단이 상태를 바꾸면 안 된다('26.9.25 코드 리뷰)."""
    state, seed = tmp_path / "new" / "rules.md", tmp_path / "seed.md"
    seed.write_text(SEED, encoding="utf-8")
    assert sr.main(["--state", str(state), "--seed", str(seed)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["missing"] is True and out["seeded"] is False and not state.exists()
    assert sr.main(["--apply", "--state", str(state), "--seed", str(seed)]) == 0
    assert state.read_text(encoding="utf-8") == SEED and json.loads(capsys.readouterr().out)["seeded"] is True


def test_superseded_marks_reach_installers_and_collisions_are_reported(tmp_path, capsys):
    """시드가 '대체됨' 표기를 단 규칙은 운영본 줄도 바꾸고, 번호만 같은 다른 규칙(설치자 로컬 선점)은 알리기만 한다."""
    seed = ("- R001 [draft] **[대체됨 → R003]** 첫 규칙\n- R002 [export] 시드의 새 표 규칙 — 열 폭 하한은 실폭 기준\n"
            "- R003 [draft] 첫 규칙 개정\n")
    state = "- R001 [draft] 첫 규칙\n- R002 [export] 설치자가 붙인 발표자료 색상 규칙\n- R003 [draft] 첫 규칙 개정\n"
    plan = sr.plan(state, seed)
    assert plan["superseded"] == ["R001"] and plan["collision"] == ["R002"] and plan["changed"] == []
    sp, dp = tmp_path / "rules.md", tmp_path / "seed.md"
    sp.write_text(state, encoding="utf-8")
    dp.write_text(seed, encoding="utf-8")
    assert sr.main(["--apply", "--state", str(sp), "--seed", str(dp)]) == 0
    text = sp.read_text(encoding="utf-8")
    assert "**[대체됨 → R003]**" in text and "설치자가 붙인 발표자료 색상 규칙" in text     # 충돌 규칙은 보존


def test_real_seed_parses_every_rule():
    """배포 시드의 규칙 줄을 빠짐없이 읽는다 — 다중 태그 규칙(R090 [draft][export] 등)도 포함."""
    text = sr.SEED.read_text(encoding="utf-8")
    ids = list(sr.rules(text))
    assert ids and ids == sorted(set(ids), key=ids.index) and "R094" in ids and "R090" in ids


def test_local_rule_on_superseded_seed_number_is_a_collision_not_overwritten(tmp_path, capsys):
    """시드가 대체 표기를 단 번호를 설치자 로컬 규칙이 쓰고 있으면 덮지 않고 충돌로 알린다('26.9.25 코드 리뷰 #2)."""
    local = "- R005 [draft] 설치자 로컬: 발표자료 색상은 남색으로 통일\n"
    seed = tmp_path / "seed.md"
    seed.write_text("- R005 [draft] **[대체됨 → R010]** 표 머리행 음영은 회색\n", encoding="utf-8")
    state = tmp_path / "rules.md"
    state.write_text(local, encoding="utf-8")
    out = sr.plan(local, seed.read_text(encoding="utf-8"))
    assert out["collision"] == ["R005"] and out["superseded"] == []
    assert sr.main(["--apply", "--state", str(state), "--seed", str(seed)]) == 0
    assert state.read_text(encoding="utf-8") == local
