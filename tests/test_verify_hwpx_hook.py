"""hwpx 인도 전 검증 훅 — 절차를 건너뛴 산출물을 차단하는지.

이 훅은 '모델이 검증을 부르는 것'에 기대지 않는 마지막 안전망이다. postprocess는 대상이
0건이어도 exit 0을 내고, 검증을 아예 부르지 않아도 파일은 만들어진다 — '26.8.7에 실제로
그렇게 배포된 건이 있었다.
"""
import json, os, subprocess, sys, zipfile, pathlib, shutil, tempfile
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "verify_hwpx_hook.py"


def run_payload(payload, cwd=None, plugin_root=str(ROOT), hook=None):
    env = dict(os.environ)
    if plugin_root:
        env["CLAUDE_PLUGIN_ROOT"] = plugin_root
    else:
        env.pop("CLAUDE_PLUGIN_ROOT", None)
    return subprocess.run([sys.executable, str(hook or HOOK)],
                          input=json.dumps(payload),
                          capture_output=True, text=True, env=env, cwd=cwd)


def run_hook(command, **kw):
    return run_payload({"tool_name": "Bash", "tool_input": {"command": command}}, **kw)


@pytest.fixture(scope="module")
def good_hwpx(tmp_path_factory):
    """생성 → 후처리까지 정상으로 마친 산출물."""
    d = tmp_path_factory.mktemp("hook")
    src = d / "prepared.md"
    src.write_text("제목\n\n< '26. 8. 4.(화), 본부 팀 >\n\n□ 절\n\n ㅇ **(리드)** 본문\n",
                   encoding="utf-8")
    out = d / "ok.hwpx"
    S = ROOT / "webapp" / "kca-report-hwpx" / "scripts"
    assert subprocess.run([sys.executable, str(S / "md2hwpx.py"), str(src), "-o", str(out)],
                          capture_output=True).returncode == 0
    assert subprocess.run([sys.executable, str(S / "postprocess_hwpx.py"), str(out),
                           "--all", "--sender-size", "12"], capture_output=True).returncode == 0
    return out


def test_passes_verified_output(good_hwpx):
    r = run_hook(f"python3 md2hwpx.py x.md -o '{good_hwpx}'")
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout


@pytest.fixture(scope="module")
def raw_hwpx(good_hwpx, tmp_path_factory):
    """정합화 이전 산출물 — kordoc generate_document가 내놓는 상태(version.xml 없음)."""
    raw = tmp_path_factory.mktemp("raw") / "raw.hwpx"
    src = zipfile.ZipFile(good_hwpx)
    with zipfile.ZipFile(raw, "w") as z:
        for n in src.namelist():
            if n == "version.xml":
                continue
            z.writestr(n, src.read(n),
                       zipfile.ZIP_STORED if n == "mimetype" else zipfile.ZIP_DEFLATED)
    return raw


def test_blocks_output_missing_canonical_members(raw_hwpx):
    """후처리를 안 거치면 version.xml이 없다 — R043 반입 거부의 원인."""
    r = run_hook(f"python3 md2hwpx.py x.md -o '{raw_hwpx}'")
    payload = json.loads(r.stdout)
    assert payload["decision"] == "block"
    assert "version.xml" in payload["reason"]


def mcp_payload(path, tool="mcp__kordoc__generate_document"):
    return {"tool_name": tool, "tool_input": {"markdown": "# 제목", "output_path": str(path)}}


def test_mcp_generation_reminds_remaining_steps(raw_hwpx):
    """MCP 생성 직후 산출물은 미정합이 정상이다 — 차단이 아니라 리마인더여야 한다.

    이 시점에 structural을 걸면 version.xml 부재·디렉터리 엔트리로 정상 흐름마다 실패한다
    ('26.8.11 실측). 매번 막히는 훅은 곧 무시되는 훅이다."""
    r = run_payload(mcp_payload(raw_hwpx))
    payload = json.loads(r.stdout)
    assert "decision" not in payload, payload
    ctx = payload["hookSpecificOutput"]["additionalContext"]
    assert "postprocess_hwpx.py" in ctx and "validate_hwpx.py" in ctx


def test_mcp_generation_blocks_corrupt_package(tmp_path):
    """생성 단계에서도 zip·XML 무결성은 판정 가능하다 — 깨진 산출물은 막는다."""
    broken = tmp_path / "broken.hwpx"
    broken.write_bytes(b"not a zip at all")
    payload = json.loads(run_payload(mcp_payload(broken)).stdout)
    assert payload["decision"] == "block"


def test_mcp_non_producer_tools_ignored(good_hwpx):
    """읽기 계열 MCP 도구까지 붙잡으면 훅이 매 호출 경로의 비용이 된다."""
    r = run_payload({"tool_name": "mcp__kordoc__parse_document",
                     "tool_input": {"file_path": str(good_hwpx)}})
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_ignores_unrelated_commands(good_hwpx):
    assert run_hook("ls -la").stdout.strip() == ""
    assert run_hook(f"cat '{good_hwpx}'").stdout.strip() == ""


def test_silent_when_validator_unavailable(tmp_path):
    """검증 스크립트를 못 찾으면 아무 것도 하지 않는다 — 훅이 파이프라인을 막으면 안 된다."""
    lone = tmp_path / "verify_hwpx_hook.py"
    shutil.copy(HOOK, lone)
    r = run_hook("md2hwpx.py -o /nonexistent.hwpx", plugin_root=None, hook=lone)
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_hooks_json_is_valid_and_points_to_the_script():
    cfg = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    entries = cfg["hooks"]["PostToolUse"]
    cmds = [h["command"] for e in entries for h in e["hooks"]]
    assert any("verify_hwpx_hook.py" in c and "CLAUDE_PLUGIN_ROOT" in c for c in cmds), cmds


def test_hooks_json_matcher_covers_the_primary_production_path():
    """파이프라인의 주 생성 경로는 Bash가 아니라 kordoc MCP다.

    matcher가 Bash뿐이면 훅 안의 generate_document 분기는 영원히 도달하지 않는다 —
    사고가 난 경로는 못 보고, 후처리를 이미 부른 안전한 경우에만 훅이 도는 상태가 된다."""
    import re
    cfg = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    matchers = [e["matcher"] for e in cfg["hooks"]["PostToolUse"]]
    hit = lambda t: any(re.fullmatch(m, t) for m in matchers)
    assert hit("Bash")
    assert hit("mcp__kordoc__generate_document")
    assert hit("mcp__kordoc__patch_document")
    assert not hit("mcp__kordoc__parse_document")
    assert not hit("Read")
