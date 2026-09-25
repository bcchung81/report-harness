#!/usr/bin/env python3
"""PostToolUse 훅 — 초안(`20_draft.md`)을 쓰거나 고칠 때마다 결정론 린트·문체 감사를 돌린다 (stdlib-only).

## 왜 필요한가

린트(`lint_md_profile.py`)와 감사(`audit_style.py`)는 모델이 부를 때만 돕는다. '26.9.10 kca-ax-invest 건에서
규칙 프리플라이트와 린트를 건너뛰어 lint 33건·audit 9건이 쌓인 채 게이트②에 올라갔다. 이 훅은 모델의 협조 없이
걸린다 — 위반(violations)이 있으면 `decision: block`으로 되돌려 0건이 될 때까지 고치게 한다. 경고(warnings)는
문서 유형에 따라 합법일 수 있어 막지 않는다.

## 대상은 초안 한 파일이다

종전 사용자 설정 훅은 '□ 줄이 2개 이상인 md'를 전부 검사해 되읽기 기록(`40_roundtrip.md`)·변환 입력
(`40_prepared.md`)·이력 스냅샷까지 초안 규칙으로 막았다('26.9.24 결함). 작업폴더 규약상 원본(SSOT)은
`20_draft.md` 하나이고 나머지는 파생물이라, 파일 이름이 정확히 `20_draft.md`일 때만 검사한다.

검사 스크립트를 찾지 못하면 아무 것도 하지 않는다 — 훅이 작성을 막는 원인이 되면 안 된다.
"""
import json
import os
import subprocess
import sys

DRAFT = "20_draft.md"


def find_scripts():
    """플러그인 루트 우선, 없으면 저장소 상대 경로."""
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (os.environ.get("CLAUDE_PLUGIN_ROOT", ""), os.path.dirname(here)):
        if base:
            d = os.path.join(base, "skills", "report-pipeline", "scripts")
            if os.path.isfile(os.path.join(d, "lint_md_profile.py")):
                return d
    return None


def target(data):
    """훅 페이로드에서 방금 쓴 파일 — 초안이면 그 경로, 아니면 None."""
    resp = data.get("tool_response") or {}
    inp = data.get("tool_input") or {}
    path = (resp.get("filePath") if isinstance(resp, dict) else None) or inp.get("file_path") or ""
    return path if os.path.basename(path) == DRAFT and os.path.isfile(path) else None


def violations(scripts, path):
    """(스크립트 이름, 위반 목록) — 실행이 실패하면 건너뛴다(훅이 소음이 되지 않게)."""
    out = []
    for name in ("lint_md_profile.py", "audit_style.py"):
        try:
            r = subprocess.run([sys.executable, os.path.join(scripts, name), path],
                               capture_output=True, text=True, timeout=60)
            found = json.loads(r.stdout).get("violations", [])
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
        if found:
            out.append((name, found))
    return out


def main():
    try:
        data = json.load(sys.stdin)
    except ValueError:
        print("lint_draft_hook: stdin 페이로드 파싱 실패 — 초안 린트를 건너뜀", file=sys.stderr)
        return
    path = target(data)
    scripts = find_scripts() if path else None
    if not path or not scripts:
        return
    found = violations(scripts, path)
    if not found:
        return
    lines = []
    for name, vs in found:
        rules = {}
        for v in vs:
            rules[v.get("rule", "?")] = rules.get(v.get("rule", "?"), 0) + 1
        where = ", ".join(str(v.get("line")) for v in vs[:8])
        lines.append(f"- {name}: {len(vs)}건 — " + ", ".join(f"{k} {n}건" for k, n in rules.items()) + f" (줄 {where})")
    print(json.dumps({
        "decision": "block",
        "reason": f"초안 규칙 위반({os.path.basename(os.path.dirname(path))}/{DRAFT}) — md-profile.md와 rules.md의 [draft] "
                  "항목을 보고 0건이 될 때까지 고친다.\n" + "\n".join(lines),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
