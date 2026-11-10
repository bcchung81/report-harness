#!/usr/bin/env python3
"""Codex용 플러그인 사본 — 실행 파일만 담은 `plugins/report-harness/`와 그것을 가리키는 `.agents/plugins/marketplace.json`.

## 왜 따로 두나

Codex는 플러그인 훅 신뢰를 **플러그인 폴더 전체의 내용 지문**으로 기록하고(`trusted_content_hash`), 세션을 시작할
때마다 Git 마켓을 최신 커밋으로 자동 갱신한다. 저장소 루트가 곧 플러그인이면 README·docs·tests 커밋 하나에도 지문이
바뀌어 모든 Codex 설치자의 훅이 'plugin contents changed; hook approval required'로 멈춘다('26.11.10 실측 — README만
바꿔도 `modified`, 실행 파일만 담은 하위 폴더는 README를 바꿔도 `trusted`).

Codex는 마켓 매니페스트를 `.agents/plugins/marketplace.json` → `.claude-plugin/marketplace.json` 순으로 찾는다. 그래서
Codex만 이 사본을 설치하고, Claude Code는 종전대로 루트(`.claude-plugin/marketplace.json`, source `./`)를 쓴다.
신뢰는 실행 파일(스킬·훅·MCP·매니페스트)이 바뀐 판에서만 다시 묻는다.

    python3 scripts/build_codex_plugin.py           # 사본을 원본에 맞춘다
    python3 scripts/build_codex_plugin.py --check   # 어긋남만 보고(exit 1) — 테스트가 같은 판정을 쓴다

원본은 git이 추적하는 파일만이다 — gitignore된 기관 자산(`assets/경영관리프레임워크` 등)은 사본에 들어가지 않는다.
exit 0: 일치(또는 맞춤 완료) | 1: 어긋남(--check) | 2: git 없음 등 환경 오류
"""
import json
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
REL = pathlib.PurePosixPath("plugins/report-harness")
MARKET = pathlib.PurePosixPath(".agents/plugins/marketplace.json")
RUNTIME = ("skills", "hooks", ".mcp.json", ".claude-plugin/plugin.json")


def runtime_files(root=ROOT):
    """사본에 들어갈 원본 — git이 추적하는 실행 파일(저장소 기준 경로)."""
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--", *RUNTIME],
                         capture_output=True, text=True, check=True).stdout
    return sorted(f for f in out.split("\0") if f)


def codex_market(root=ROOT):
    """Claude 마켓 매니페스트와 같고, 플러그인 경로만 사본 폴더로."""
    m = json.loads((pathlib.Path(root) / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
    for p in m["plugins"]:
        p["source"] = {"source": "local", "path": f"./{REL}"}
    return json.dumps(m, ensure_ascii=False, indent=2) + "\n"


def expected(root=ROOT):
    """{저장소 기준 경로: 바이트} — 사본과 Codex 마켓 파일이 가져야 할 내용."""
    root = pathlib.Path(root)
    want = {str(REL / f): (root / f).read_bytes() for f in runtime_files(root)}
    want[str(MARKET)] = codex_market(root).encode("utf-8")
    return want


def drift(root=ROOT):
    """어긋남 목록 — 빠진 파일·다른 파일·사본에만 있는 파일."""
    root = pathlib.Path(root)
    want = expected(root)
    have = {str(p.relative_to(root)) for p in (root / REL).rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    out = [f"빠짐 {k}" for k in want if not (root / k).is_file()]
    out += [f"다름 {k}" for k in want if (root / k).is_file() and (root / k).read_bytes() != want[k]]
    out += [f"사본에만 {k}" for k in sorted(have - set(want))]
    return out


def build(root=ROOT):
    """사본을 원본에 맞춘다 — 바뀐 파일만 쓰고 원본에 없는 파일은 지운다."""
    root = pathlib.Path(root)
    want = expected(root)
    for k, data in want.items():
        p = root / k
        if not p.is_file() or p.read_bytes() != data:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
            shutil.copymode(root / pathlib.PurePosixPath(k).relative_to(REL), p) if k.startswith(str(REL)) else None
    for p in sorted((root / REL).rglob("*"), reverse=True):
        rel = str(p.relative_to(root))
        if p.is_file() and rel not in want:
            p.unlink()
        elif p.is_dir() and not any(p.iterdir()):
            p.rmdir()
    return drift(root)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        left = drift() if "--check" in argv else build()
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps({"plugin": str(REL), "market": str(MARKET), "drift": left}, ensure_ascii=False, indent=1))
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main())
