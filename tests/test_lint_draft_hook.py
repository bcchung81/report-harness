"""초안 린트 훅 — 20_draft.md만 검사하고, 위반이 있으면 block, 파생 md는 건드리지 않는다('26.9.25 결함 정비)."""
import json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "lint_draft_hook.py"
CLEAN = "개선 추진 보고\n\n< '26. 9. 25.(목), 경영기획본부 AI디지털심화팀 >\n\n□ 개 요\n\nㅇ **(측정 목적)** 기관 AI 과제 18건의 성과를 같은 기준으로 재는 측정 체계를 마련해 경영평가 지적에 대응\n"


def run_hook(path, tool="Write"):
    payload = {"tool_name": tool, "tool_input": {"file_path": str(path)}, "tool_response": {"filePath": str(path)}}
    env = {"PATH": "/usr/bin:/bin", "CLAUDE_PLUGIN_ROOT": str(ROOT)}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env)


def test_blocks_draft_with_violations(tmp_path):
    p = tmp_path / "20_draft.md"
    p.write_text(CLEAN + "\nㅇ **(현황)** 자료가 흩어져 과제 수행이 불가함\n", encoding="utf-8")   # ~함 종결(철칙 위반)
    r = run_hook(p)
    out = json.loads(r.stdout)
    assert out["decision"] == "block" and "audit_style.py" in out["reason"] and "ending-forbidden" in out["reason"]


def test_clean_draft_passes_silently(tmp_path):
    p = tmp_path / "20_draft.md"
    p.write_text(CLEAN, encoding="utf-8")
    r = run_hook(p, tool="Edit")
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_derived_markdown_is_not_linted(tmp_path):
    """되읽기 기록·변환 입력·이력 스냅샷은 초안 규칙 대상이 아니다(종전 훅이 40_roundtrip.md를 막던 결함)."""
    bad = CLEAN + "\nㅇ **(현황)** 자료가 흩어져 과제 수행이 불가함\n# 제목 헤딩\n"
    for name in ("40_roundtrip.md", "40_prepared.md", "20_draft.20260925-1220.외부근거검증반영전.md", "10_outline.md"):
        p = tmp_path / name
        p.write_text(bad, encoding="utf-8")
        assert run_hook(p).stdout.strip() == "", name


def run_codex_patch(patch, cwd, root_var="PLUGIN_ROOT"):
    """Codex 0.167 실측 페이로드 — 편집은 apply_patch 하나, 경로는 패치 본문에 있다."""
    payload = {"hook_event_name": "PostToolUse", "tool_name": "apply_patch", "cwd": str(cwd),
               "tool_input": {"command": patch},
               "tool_response": "Exit code: 0\nOutput:\nSuccess. Updated the following files:\n"}
    env = {"PATH": "/usr/bin:/bin", root_var: str(ROOT)}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env)


def test_codex_apply_patch_on_draft_is_linted(tmp_path):
    """Codex의 apply_patch — 절대경로(Update File)·상대경로(Add File, cwd 기준) 둘 다 초안이면 검사한다."""
    bad = CLEAN + "\nㅇ **(현황)** 자료가 흩어져 과제 수행이 불가함\n"
    p = tmp_path / "20_draft.md"
    p.write_text(bad, encoding="utf-8")
    r = run_codex_patch(f"*** Begin Patch\n*** Update File: {p}\n@@\n-x\n+y\n*** End Patch", tmp_path)
    assert json.loads(r.stdout)["decision"] == "block" and "ending-forbidden" in r.stdout
    r = run_codex_patch("*** Begin Patch\n*** Add File: 20_draft.md\n+x\n*** End Patch", tmp_path, root_var="CLAUDE_PLUGIN_ROOT")
    assert json.loads(r.stdout)["decision"] == "block"


def test_codex_apply_patch_clean_or_derived_passes(tmp_path):
    (tmp_path / "20_draft.md").write_text(CLEAN, encoding="utf-8")
    (tmp_path / "40_roundtrip.md").write_text(CLEAN + "\nㅇ **(현황)** 수행이 불가함\n", encoding="utf-8")
    assert run_codex_patch("*** Begin Patch\n*** Update File: 20_draft.md\n@@\n-x\n+y\n*** End Patch", tmp_path).stdout.strip() == ""
    assert run_codex_patch("*** Begin Patch\n*** Update File: 40_roundtrip.md\n@@\n-x\n+y\n*** End Patch", tmp_path).stdout.strip() == ""


def run_bash(command, cwd, extra_env=None):
    payload = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": str(cwd),
               "tool_input": {"command": command}, "tool_response": ""}
    env = {"PATH": "/usr/bin:/bin", "CLAUDE_PLUGIN_ROOT": str(ROOT), "TMPDIR": str(cwd), **(extra_env or {})}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, env=env)


def test_shell_written_draft_is_linted_once_per_change(tmp_path):
    """Codex는 초안을 셸(heredoc)로 쓰는 일이 잦다('26.11.10 실전 점검 전량) — 명령에 20_draft가 보이면 검사하되,
    같은 내용을 읽기만 하는 다음 명령은 다시 막지 않는다. 내용이 바뀌면 다시 본다."""
    p = tmp_path / "20_draft.md"
    p.write_text(CLEAN + "\nㅇ **(현황)** 자료가 흩어져 과제 수행이 불가함\n", encoding="utf-8")
    write = f"python3 - <<'PY'\nimport pathlib\npathlib.Path('{p}').write_text('...')\nPY"
    assert json.loads(run_bash(write, tmp_path).stdout)["decision"] == "block"
    assert run_bash(f"cat {p}", tmp_path).stdout.strip() == ""                # 그대로면 되풀이하지 않는다
    import os, time
    p.write_text(CLEAN + "\nㅇ **(현황)** 수행이 불가함\n", encoding="utf-8")
    os.utime(p, (time.time() + 5, time.time() + 5))
    assert json.loads(run_bash("sed -i '' 's/a/b/' 20_draft.md", tmp_path).stdout)["decision"] == "block"
    assert run_bash("ls -la && echo done", tmp_path).stdout.strip() == ""   # 초안과 무관한 명령은 바로 끝난다


def test_shell_draft_with_assembled_path_uses_recent_drafts(tmp_path):
    """경로를 조립해 쓴 경우(`p/'20_draft.md'`) — 설정의 reports_dir 아래 최근 초안을 본다."""
    wd = tmp_path / "reports" / "20261110" / "0900_시험"
    wd.mkdir(parents=True)
    (wd / "20_draft.md").write_text(CLEAN + "\nㅇ **(현황)** 자료가 흩어져 과제 수행이 불가함\n", encoding="utf-8")
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"reports_dir": str(tmp_path / "reports")}), encoding="utf-8")
    cmd = "python3 - <<'PY'\nimport pathlib\np=pathlib.Path(open('work_path.txt').read().strip())\n(p/'20_draft.md').write_text(x)\nPY"
    r = run_bash(cmd, tmp_path, {"REPORT_HARNESS_CONFIG": str(cfg)})
    assert json.loads(r.stdout)["decision"] == "block" and "0900_시험" in r.stdout


def test_hook_is_registered_for_file_edits():
    cfg = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    entry = [e for e in cfg["hooks"]["PostToolUse"] if any("lint_draft_hook.py" in h["command"] for h in e["hooks"])]
    assert entry and all(t in entry[0]["matcher"] for t in ("Write", "Edit", "apply_patch", "Bash"))   # apply_patch = Codex 편집, Bash = 셸로 쓴 초안
    assert all("CLAUDE_PLUGIN_ROOT" in h["command"] for h in entry[0]["hooks"])               # Codex도 이 변수를 준다
