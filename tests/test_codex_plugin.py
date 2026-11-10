"""Codex용 플러그인 사본 — `plugins/report-harness/`가 실행 파일 원본과 바이트 동일하고, Codex 마켓이 그 사본을 가리킨다.

Codex는 훅 신뢰를 플러그인 폴더 전체의 내용 지문으로 기록하고 세션마다 Git 마켓을 자동 갱신한다 — 판이 바뀔 때마다
'plugin contents changed; hook approval required'가 되풀이돼('26.11.10 실측) 사본에는 훅을 싣지 않는다(0.7.5).
사본이 원본과 갈라지면 Codex 사용자만 옛 하네스로 돈다.
"""
import importlib.util, json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("build_codex_plugin", ROOT / "scripts/build_codex_plugin.py")
bcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bcp)


def test_codex_copy_matches_runtime_sources():
    """스킬·.mcp.json·plugin.json을 고쳤으면 `python3 scripts/build_codex_plugin.py`로 사본을 맞춘다."""
    assert bcp.drift() == [], "Codex 사본이 원본과 다르다 — python3 scripts/build_codex_plugin.py"


def test_codex_market_points_to_the_copy_and_mirrors_claude_market():
    claude = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    codex = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
    assert codex["name"] == claude["name"] == "report-harness"            # 설치명 report-harness@report-harness 유지
    assert claude["plugins"][0]["source"] == "./"                          # Claude Code는 종전대로 루트
    assert codex["plugins"][0]["source"] == {"source": "local", "path": "./plugins/report-harness"}
    strip = lambda m: [{k: v for k, v in p.items() if k != "source"} for p in m["plugins"]]
    assert strip(codex) == strip(claude)


def test_codex_copy_holds_only_runtime_files():
    """문서·테스트·작업 산출물이 들어가면 그 커밋마다 신뢰가 풀린다 — 실행 파일만 둔다."""
    top = {p.name for p in (ROOT / "plugins/report-harness").iterdir()}
    assert top == {".claude-plugin", ".mcp.json", "skills"}, top
    assert not list((ROOT / "plugins/report-harness").rglob("__pycache__"))


def test_codex_copy_ships_no_hooks():
    """훅이 있으면 Codex가 판마다 신뢰를 다시 묻고, 못 받으면 도구 호출마다 'Hook failed'를 띄운다 — 훅은 Claude Code 전용."""
    copy = ROOT / "plugins/report-harness"
    assert not (copy / "hooks").exists()
    assert not list(copy.rglob("hooks.json"))
    assert "hooks" not in json.loads((copy / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert (ROOT / "hooks/hooks.json").is_file()                            # Claude Code는 종전대로 루트의 훅을 쓴다
