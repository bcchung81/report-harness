import json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

def test_plugin_manifest_valid():
    m = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert m["name"] == "report-harness"
    assert "version" in m and "description" in m


def test_license_present_and_declared():
    """공개 배포판은 라이선스가 없으면 법적으로 all rights reserved가 된다."""
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in text and "Copyright (c)" in text
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["license"] == "MIT"
    # 번들 서드파티(humanizer)의 별도 라이선스 고지가 유지되는지
    assert (ROOT / "skills/humanizer/LICENSE").is_file()
    assert "DaleSeo" in text


def test_mcp_bundle_valid():
    """번들 MCP는 kordoc(필수)·korean-law(선택) 둘뿐이며, 인증키를 값으로 박아두면 안 된다."""
    mcp = json.loads((ROOT / ".mcp.json").read_text())
    servers = mcp["mcpServers"]
    assert set(servers) == {"kordoc", "korean-law"}, set(servers)
    assert "kordoc" in servers["kordoc"]["args"]
    # 키는 환경변수 참조만 허용 — 실제 값이 커밋되면 공개 저장소에 유출된다
    law_oc = servers["korean-law"]["env"]["LAW_OC"]
    assert law_oc.startswith("${") and law_oc.endswith("}"), f"LAW_OC 실값 유출 의심: {law_oc}"


def test_marketplace_manifest_valid():
    mk = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert mk["name"] and mk["description"] and mk["owner"]["name"]
    entries = [p for p in mk["plugins"] if p["name"] == "report-harness"]
    assert len(entries) == 1, "report-harness 항목이 정확히 하나여야 한다"
    assert entries[0]["source"] == "./", "저장소 루트를 플러그인으로 등록한다"


def test_marketplace_version_matches_plugin():
    """배포 시 두 매니페스트의 버전이 어긋나면 설치본과 카탈로그가 불일치한다."""
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    mk = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    entry = next(p for p in mk["plugins"] if p["name"] == "report-harness")
    assert entry["version"] == plugin["version"], (
        f"marketplace.json {entry['version']} != plugin.json {plugin['version']}"
    )

def test_version_consistent_across_changelog_and_readme():
    """plugin.json 버전이 CHANGELOG 최신 릴리스·README 배지와 일치한다.

    실사고: 0.3.1 배지인 채 CHANGELOG에 'Unreleased' 절이 5개까지 쌓이고 릴리스가
    두 달 밀렸다 — 버전을 올리려면 세 곳을 함께 움직여야 통과한다."""
    import re
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    releases = re.findall(r"^## (\d+\.\d+\.\d+) \(", changelog, re.M)
    assert releases and releases[0] == plugin["version"], (
        f"CHANGELOG 최신 릴리스 {releases[:1]} != plugin.json {plugin['version']}")
    assert not re.search(r"^## Unreleased", changelog, re.M), \
        "CHANGELOG에 Unreleased 절 잔존 — 릴리스에 귀속시킬 것"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    m = re.search(r"badge/version-(\d+\.\d+\.\d+)-", readme)
    assert m and m.group(1) == plugin["version"], (
        f"README 배지 {m and m.group(1)} != plugin.json {plugin['version']}")


def test_research_skill_exists():
    t = (ROOT / "skills/report-research/SKILL.md").read_text(encoding="utf-8")
    assert t.startswith("---") and "name: report-research" in t
    assert "_manifest.jsonl" in t and "확정" in t

def test_pipeline_skill_references_exist():
    t = (ROOT / "skills/report-pipeline/SKILL.md").read_text(encoding="utf-8")
    for ref in ["style-guide.md", "md-profile.md", "hwpx-recipe.md", "diagram-pool.md",
                "format-profile.kca.md", "rules-seed.md", "lint_md_profile.py", "harness_config.py"]:
        assert ref in t, ref
    for f in ["style-guide.md", "md-profile.md", "hwpx-recipe.md", "rules-seed.md"]:
        assert (ROOT / "skills/report-pipeline/references" / f).is_file()

def test_skill_docs_call_scripts_via_skill_dir():
    """스킬 문서의 스크립트 호출은 전부 `$SKILL_DIR` 기준이어야 한다(SKILL.md §0 경로 규약).

    플러그인 설치 환경은 cwd가 사용자 프로젝트라 저장소 상대경로(`python3 skills/…/scripts/x.py`)가
    전부 No such file로 깨진다. 절차서를 그대로 따른 모델이 후처리·구조검증을 조용히 건너뛴
    hwpx를 인도하게 되는 경로다 — verify_hwpx_hook.py가 막으려던 바로 그 사고."""
    import re
    bad = []
    for md in sorted((ROOT / "skills").rglob("*.md")):
        for i, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"python3\s+['\"]?skills/", line):
                bad.append(f"{md.relative_to(ROOT)}:{i}")
    assert not bad, "저장소 상대경로 스크립트 호출: " + ", ".join(bad)


def test_commands_and_bundle():
    for c in ["report-research", "report-analyze", "report-draft", "report-export",
              "report-doctor"]:
        assert (ROOT / "commands" / f"{c}.md").is_file()
    assert (ROOT / "skills/humanizer/SKILL.md").is_file()
