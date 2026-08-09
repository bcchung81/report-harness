"""hwpx 인도 전 검증 훅 — 절차를 건너뛴 산출물을 차단하는지.

이 훅은 '모델이 검증을 부르는 것'에 기대지 않는 마지막 안전망이다. postprocess는 대상이
0건이어도 exit 0을 내고, 검증을 아예 부르지 않아도 파일은 만들어진다 — '26.8.7에 실제로
그렇게 배포된 건이 있었다.
"""
import json, os, subprocess, sys, zipfile, pathlib, shutil, tempfile
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "verify_hwpx_hook.py"


def run_hook(command, cwd=None, plugin_root=str(ROOT), hook=None):
    env = dict(os.environ)
    if plugin_root:
        env["CLAUDE_PLUGIN_ROOT"] = plugin_root
    else:
        env.pop("CLAUDE_PLUGIN_ROOT", None)
    return subprocess.run([sys.executable, str(hook or HOOK)],
                          input=json.dumps({"tool_input": {"command": command}}),
                          capture_output=True, text=True, env=env, cwd=cwd)


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


def test_blocks_output_missing_canonical_members(good_hwpx, tmp_path):
    """후처리를 안 거치면 version.xml이 없다 — R043 반입 거부의 원인."""
    raw = tmp_path / "raw.hwpx"
    src = zipfile.ZipFile(good_hwpx)
    with zipfile.ZipFile(raw, "w") as z:
        for n in src.namelist():
            if n == "version.xml":
                continue
            z.writestr(n, src.read(n),
                       zipfile.ZIP_STORED if n == "mimetype" else zipfile.ZIP_DEFLATED)
    r = run_hook(f"python3 md2hwpx.py x.md -o '{raw}'")
    payload = json.loads(r.stdout)
    assert payload["decision"] == "block"
    assert "version.xml" in payload["reason"]


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
    assert any(e.get("matcher") == "Bash" for e in entries)
    cmds = [h["command"] for e in entries for h in e["hooks"]]
    assert any("verify_hwpx_hook.py" in c and "CLAUDE_PLUGIN_ROOT" in c for c in cmds), cmds
