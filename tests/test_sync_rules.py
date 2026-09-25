"""규칙 시드 동기화 — 새 규칙은 설치자 운영본에 들어가고, 설치자의 축적·수정은 지워지지 않는다('26.9.25)."""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import sync_rules as sr

SEED = "# rules\n\n- R001 [draft] 첫 규칙\n- R002 [export] 둘째 규칙(정정본)\n- R003 [draft][export] 새 규칙\n"
STATE = "# rules\n\n- R001 [draft] 첫 규칙\n- R002 [export] 둘째 규칙\n- R901 [draft] 설치자가 쌓은 규칙\n"


def test_plan_separates_new_changed_and_local_rules():
    assert sr.plan(STATE, SEED) == {"added": ["R003"], "updated": [], "superseded": [], "collision": [],
                                    "changed": ["R002"], "retired": [], "local_only": ["R901"], "marker": None}


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


def test_history_is_copied_and_missing_sections_appended(tmp_path, capsys):
    """경위 로그도 맞춘다 — 없으면 복사, 있으면 시드에만 있는 절만 덧붙인다. --apply 없이는 쓰지 않는다
    ('26.9.25 격리 설치 재현: 새 설치 자가진단이 흡수된 번호 6건을 죽은 참조로 경고)."""
    seed_dir, state_dir = tmp_path / "ref", tmp_path / "state"
    seed_dir.mkdir()
    seed = seed_dir / "rules-seed.md"
    seed.write_text("- R001 [draft] 첫 규칙\n", encoding="utf-8")
    (seed_dir / "rules-history.md").write_text("# 경위\n\n## R050 [흡수]\n\n- 옛 규칙\n\n## R060\n\n- 경위\n",
                                              encoding="utf-8")
    state = state_dir / "rules.md"
    args = ["--state", str(state), "--seed", str(seed)]
    assert sr.main(args) == 0 and not state_dir.exists()                           # 점검은 아무것도 쓰지 않는다
    assert json.loads(capsys.readouterr().out)["history_added"] == ["R050", "R060"]
    assert sr.main(["--apply"] + args) == 0                                           # 첫 실행 — 둘 다 복사
    capsys.readouterr()
    hist = state_dir / "rules-history.md"
    assert hist.read_text(encoding="utf-8") == (seed_dir / "rules-history.md").read_text(encoding="utf-8")
    hist.write_text("# 운영 경위\n\n## R060\n\n- 설치자가 고친 경위\n", encoding="utf-8")   # R050 절이 빠진 옛 설치
    assert sr.main(["--apply"] + args) == 0
    assert json.loads(capsys.readouterr().out)["history_added"] == ["R050"]
    text = hist.read_text(encoding="utf-8")
    assert "설치자가 고친 경위" in text and "## R050 [흡수]" in text and text.count("## R060") == 1
    assert sr.main(["--apply"] + args) == 0                                           # 멱등
    assert json.loads(capsys.readouterr().out)["history_added"] == []


def test_untouched_old_seed_lines_are_updated_and_retired_by_lineage(tmp_path, capsys):
    """계보에 있는 옛 시드 줄은 설치자가 손대지 않은 것이다 — 새 시드 줄로 바꾸고, 시드에서 폐지된 번호면 지운다.
    설치자가 고친 줄·로컬 규칙은 그대로 둔다('26.9.25 격리 설치 재현: 0.4.0 설치자의 옛 시드 줄 7건을 '번호 충돌'로
    오판해 새 값이 들어가지 않았고 폐지된 R053이 살아 있었다)."""
    old = {"R001": "- R001 [draft] 표 머리행 음영은 회색", "R002": "- R002 [export] 옛 규칙 — 뒤에 흡수됨",
           "R003": "- R003 [draft] 열 폭 하한은 글자 수 기준"}
    lineage = {k: {sr.fingerprint(v)} for k, v in old.items()}
    seed = ("<!-- consolidated-at: R003 -->\n- R001 [draft] 표 머리행 음영은 연회색(#F2F2F2) — 인쇄 대비\n"
            "- R003 [draft] 열 폭 하한은 실폭 기준(글자 수 아님)\n- R004 [export] 새 규칙\n")
    state = ("<!-- consolidated-at: R001 -->\n" + old["R001"] + "\n" + old["R002"] + "\n"
             "- R003 [draft] 열 폭 하한은 글자 수 기준 — 우리 부서는 12자\n- R901 [draft] 설치자 로컬 규칙\n")
    plan = sr.plan(state, seed, lineage)
    assert plan["updated"] == ["R001"] and plan["retired"] == ["R002"] and plan["added"] == ["R004"]
    assert plan["changed"] == ["R003"] and plan["local_only"] == ["R901"] and plan["marker"] == "R003"
    sp, dp = tmp_path / "rules.md", tmp_path / "seed.md"
    sp.write_text(state, encoding="utf-8")
    dp.write_text(seed, encoding="utf-8")
    sr.apply(sp, seed, plan["added"], plan["updated"], plan["retired"], plan["marker"])
    text = sp.read_text(encoding="utf-8")
    assert "연회색(#F2F2F2)" in text and "R002" not in text and "- R004 [export] 새 규칙" in text
    assert "우리 부서는 12자" in text and "R901" in text and "consolidated-at: R003" in text
    assert sr.plan(text, seed, lineage)["updated"] == [] and sr.plan(text, seed, lineage)["marker"] is None   # 멱등


def test_lineage_covers_the_current_seed():
    """배포하는 시드 줄은 모두 계보에 있어야 한다 — 빠지면 다음 판에서 이 줄을 받은 설치자의 줄을 '고친 줄'로 오판한다.
    시드를 고쳤으면 `python3 scripts/build_seed_lineage.py`."""
    lineage = sr.load_lineage()
    missing = [k for k, line in sr.rules(sr.SEED.read_text(encoding="utf-8")).items()
               if sr.fingerprint(line) not in lineage.get(k, ())]
    assert missing == [], f"계보에 없는 시드 줄 {missing} — python3 scripts/build_seed_lineage.py 실행"


def test_old_release_seeds_upgrade_cleanly(tmp_path):
    """계보에 든 옛 시드 판본을 그대로 쓰던 설치자는 --apply 한 번으로 현재 시드와 같아진다."""
    import subprocess
    root = pathlib.Path(__file__).resolve().parents[1]
    revs = subprocess.run(["git", "-C", str(root), "log", "--format=%H", "--", "skills/report-pipeline/references/rules-seed.md"],
                          capture_output=True, text=True).stdout.split()
    if len(revs) < 2:
        import pytest
        pytest.skip("git 이력 없음(얕은 clone)")
    seed = sr.SEED.read_text(encoding="utf-8")
    for rev in revs[1:4]:
        old = subprocess.run(["git", "-C", str(root), "show", f"{rev}:skills/report-pipeline/references/rules-seed.md"],
                             capture_output=True, text=True).stdout
        sp = tmp_path / f"{rev[:7]}.md"
        sp.write_text(old, encoding="utf-8")
        p = sr.plan(old, seed)
        assert p["collision"] == [] and p["changed"] == [], rev[:7]
        sr.apply(sp, seed, p["added"], p["updated"] + p["superseded"], p["retired"], p["marker"])
        assert sr.rules(sp.read_text(encoding="utf-8")) == sr.rules(seed), rev[:7]
