"""자가진단 미조치 lesson — kind·resolved_by로 센다('26.9.25 스키마; 종전 fix 키워드 판정은 끝난 조치까지 셌다)."""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import doctor


def test_classify_counts_only_unresolved_defects_and_features():
    rows = [
        {"date": "2026-09-24", "kind": "defect", "fix": "게이트② 뒤 정비"},                            # 미해결
        {"date": "2026-09-25", "kind": "feature", "fix": "요청", "resolved_by": "abc1234"},            # 해결
        {"date": "2026-09-20", "kind": "content", "fix": "초안 보강 필요"},                            # 내용 교훈
        {"date": "2026-09-01", "harness_defect": True, "fix": "훅 대상 정비"},                         # 옛 결함 표시
        {"date": "2026-08-01", "fix": "추가 검토 필요"},                                               # 옛 기록(참고)
        {"date": "2026-08-02", "fix": "보강 — 적용 완료", "resolved_by": "R074"},                      # 옛 기록·해결
        {"date": "2026-08-03", "kind": "defect", "fix": "…", "promoted": True},                        # 규칙으로 승격
    ]
    open_, legacy = doctor.classify_lessons(rows)
    assert [r["date"] for r in open_] == ["2026-09-24", "2026-09-01"]
    assert [r["date"] for r in legacy] == ["2026-08-01"]


def test_pending_check_reports_warn_only_for_open_items(tmp_path):
    p = tmp_path / "lessons.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"date": "2026-09-24", "kind": "defect", "fix": "x"},
        {"date": "2026-08-01", "fix": "보강 필요"}]) + "\n", encoding="utf-8")
    out = doctor.pending_lessons_check(p)
    assert out["상태"] == doctor.WARN and "미해결 결함·기능 1건" in out["값"] and "참고" in out["값"]
    p.write_text(json.dumps({"date": "2026-09-24", "kind": "defect", "fix": "x", "resolved_by": "eb88d24"}) + "\n",
                 encoding="utf-8")
    assert doctor.pending_lessons_check(p)["상태"] == doctor.OK
    assert doctor.pending_lessons_check(tmp_path / "없음.jsonl")["값"].startswith("축적본 없음")


def test_installed_copy_check_flags_stale_or_missing_files(tmp_path):
    """저장소 스킬과 ~/.claude/skills 사본이 다르면 경고 — 새 세션이 옛 하네스로 도는 것을 막는다('26.9.15 사고)."""
    repo, inst = tmp_path / "repo", tmp_path / "installed"
    for rel, body in (("skills/report-pipeline/SKILL.md", "v2"), ("skills/report-pipeline/references/factcheck.md", "x")):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(body, encoding="utf-8")
    (inst / "report-pipeline").mkdir(parents=True)
    (inst / "report-pipeline" / "SKILL.md").write_text("v1", encoding="utf-8")                  # 옛 사본, factcheck.md 없음
    files = ["skills/report-pipeline/SKILL.md", "skills/report-pipeline/references/factcheck.md"]
    out = doctor.installed_copy_check(repo, inst, files)
    assert out["상태"] == doctor.WARN and "2개" in out["값"]
    (inst / "report-pipeline" / "SKILL.md").write_text("v2", encoding="utf-8")
    (inst / "report-pipeline" / "references").mkdir()
    (inst / "report-pipeline" / "references" / "factcheck.md").write_text("x", encoding="utf-8")
    assert doctor.installed_copy_check(repo, inst, files)["상태"] == doctor.OK
    assert doctor.installed_copy_check(repo, tmp_path / "없음", files) is None                  # 사본 없는 환경(플러그인)


def test_harness_version_comes_from_plugin_manifest(tmp_path):
    """자가진단은 하네스 버전을 보인다 — 매니페스트가 없으면(스킬 사본) None."""
    import json as _json
    root = pathlib.Path(__file__).resolve().parents[1]
    assert doctor.harness_version() == _json.loads((root / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["version"]
    assert doctor.harness_version(tmp_path) is None


def test_kordoc_recovery_command_uses_the_pinned_version(tmp_path):
    """자가진단의 복구 명령은 `.mcp.json`에 고정된 kordoc 버전을 쓴다 — 못 읽으면 버전 없이."""
    assert doctor.kordoc_package().startswith("kordoc@")
    assert doctor.kordoc_package(tmp_path) == "kordoc"


def test_installed_copy_check_covers_user_commands(tmp_path):
    """사용자 커맨드 폴더에 하네스 커맨드 사본이 있으면 빠진 것·다른 것도 경고한다('26.9.25: /report-export 사본이
    후처리 문구가 빠진 옛 판, /report-doctor 미등록)."""
    repo, inst = tmp_path / "repo", tmp_path / "skills"
    (repo / "commands").mkdir(parents=True)
    (repo / "commands" / "report-export.md").write_text("new", encoding="utf-8")
    (repo / "commands" / "report-review.md").write_text("r", encoding="utf-8")
    files = ["commands/report-export.md", "commands/report-review.md"]
    assert doctor.installed_copy_check(repo, inst, files) is None                   # 커맨드 사본을 쓰지 않는 환경
    (tmp_path / "commands").mkdir()
    (tmp_path / "commands" / "report-export.md").write_text("old", encoding="utf-8")
    out = doctor.installed_copy_check(repo, inst, files)
    assert out["상태"] == doctor.WARN and "2개" in out["값"] and "commands" in out["조치"]
    (tmp_path / "commands" / "report-export.md").write_text("new", encoding="utf-8")
    (tmp_path / "commands" / "report-review.md").write_text("r", encoding="utf-8")
    assert doctor.installed_copy_check(repo, inst, files)["상태"] == doctor.OK
