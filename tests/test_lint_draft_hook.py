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


def test_hook_is_registered_for_file_edits():
    cfg = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    entry = [e for e in cfg["hooks"]["PostToolUse"] if any("lint_draft_hook.py" in h["command"] for h in e["hooks"])]
    assert entry and all(t in entry[0]["matcher"] for t in ("Write", "Edit"))
    assert all("CLAUDE_PLUGIN_ROOT" in h["command"] for h in entry[0]["hooks"])
