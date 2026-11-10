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

## 두 실행기의 페이로드

- Claude Code — `Write`·`Edit`·`MultiEdit`, 경로는 `tool_input.file_path`(응답의 `filePath`).
- Codex — 파일 편집이 `apply_patch` 하나이고 경로는 패치 본문(`tool_input.command`)의
  `*** Add File:`·`*** Update File:`·`*** Move to:` 줄에 있다('26.11.10 codex 0.167 실측). 상대경로는
  페이로드의 `cwd` 기준이다.
- **셸로 쓴 초안**(`Bash`) — Codex는 초안을 `python3 - <<PY … write_text` 같은 셸 명령으로 쓰는 일이 잦다('26.11.10
  실전 점검에서 초안 전량이 이 경로였다). 명령에 `20_draft`가 보이면 명령 속 경로, 없으면 `reports_dir` 아래 최근
  초안을 후보로 삼고, **훅이 마지막으로 본 뒤 바뀐 초안만** 검사한다 — 초안을 읽기만 하는 명령마다 같은 위반을 되풀이해
  막지 않게(본 시각은 임시 폴더 `report-harness-lint-seen.json`).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

DRAFT = "20_draft.md"
PATCH_FILE = re.compile(r"^\*\*\* (?:Add File|Update File|Move to): (.+?)\s*$", re.M)
DRAFT_IN_CMD = re.compile(r"[^\s\"'`=(),;<>|&]*20_draft\.md")
RECENT_SEC = 600                     # 명령 속 경로를 못 찾을 때 '방금 쓴 초안'으로 볼 범위
SEEN = os.path.join(tempfile.gettempdir(), "report-harness-lint-seen.json")


def _seen_load():
    try:
        with open(SEEN, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def changed(paths):
    """마지막으로 본 뒤 내용이 바뀐(mtime) 초안만 — 본 시각을 갱신한다."""
    seen, out = _seen_load(), []
    for p in paths:
        m = os.stat(p).st_mtime_ns
        if seen.get(p) != m:
            out.append(p)
            seen[p] = m
    if out:
        try:
            with open(SEEN, "w", encoding="utf-8") as f:
                json.dump(seen, f)
        except OSError:
            pass
    return out


def recent_drafts(scripts):
    """설정의 reports_dir 아래 `{날짜}/{건}/20_draft.md` 중 최근에 바뀐 것(셸 명령이 경로를 조립해 쓴 경우)."""
    try:
        sys.path.insert(0, scripts)
        import harness_config
        base = harness_config.load_config()["reports_dir"]
    except Exception:
        return []
    now = time.time()
    return [str(p) for p in base.glob(f"*/*/{DRAFT}") if now - p.stat().st_mtime < RECENT_SEC]


def find_scripts():
    """플러그인 루트 우선(Codex는 PLUGIN_ROOT·CLAUDE_PLUGIN_ROOT 둘 다 준다), 없으면 저장소 상대 경로."""
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (os.environ.get("CLAUDE_PLUGIN_ROOT", ""), os.environ.get("PLUGIN_ROOT", ""), os.path.dirname(here)):
        if base:
            d = os.path.join(base, "skills", "report-pipeline", "scripts")
            if os.path.isfile(os.path.join(d, "lint_md_profile.py")):
                return d
    return None


def targets(data, scripts=None):
    """훅 페이로드에서 방금 쓴 초안 경로 목록 — 초안이 아니면 빈 목록."""
    resp = data.get("tool_response") if isinstance(data.get("tool_response"), dict) else {}
    inp = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    cmd = inp.get("command")
    cmd = " ".join(str(x) for x in cmd) if isinstance(cmd, (list, tuple)) else (cmd if isinstance(cmd, str) else "")
    shell = data.get("tool_name") == "Bash"
    if shell and "20_draft" not in cmd:
        return []                                        # 셸 명령 대부분은 여기서 끝난다(훅 비용)
    fp = resp.get("filePath") or inp.get("file_path") or ""
    paths = [fp if isinstance(fp, str) else ""]
    if data.get("tool_name") == "apply_patch":
        paths += PATCH_FILE.findall(cmd)
    if shell:
        paths += DRAFT_IN_CMD.findall(cmd)
    out = []
    for p in paths:
        if p and not os.path.isabs(p) and isinstance(data.get("cwd"), str):
            p = os.path.join(data["cwd"], p)
        if os.path.basename(p) == DRAFT and os.path.isfile(p) and p not in out:
            out.append(os.path.abspath(p))
    if shell:
        if not out and scripts:
            out = recent_drafts(scripts)
        return changed(out)
    changed(out)                                         # 편집 도구로 쓴 것도 '본 것'으로 남긴다 — 뒤이은 읽기 명령이 다시 막지 않게
    return out


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
    if not isinstance(data, dict):
        return
    if isinstance(data.get("cwd"), str) and os.path.isdir(data["cwd"]):
        os.chdir(data["cwd"])                            # 설정 없는 기본 reports_dir(실행 위치 기준)을 세션 위치로 맞춘다
    scripts = find_scripts()
    paths = targets(data, scripts) if scripts else []
    if not paths:
        return
    blocks = []
    for path in paths:
        found = violations(scripts, path)
        if not found:
            continue
        lines = []
        for name, vs in found:
            rules = {}
            for v in vs:
                rules[v.get("rule", "?")] = rules.get(v.get("rule", "?"), 0) + 1
            where = ", ".join(str(v.get("line")) for v in vs[:8])
            lines.append(f"- {name}: {len(vs)}건 — " + ", ".join(f"{k} {n}건" for k, n in rules.items()) + f" (줄 {where})")
        blocks.append(f"초안 규칙 위반({os.path.basename(os.path.dirname(path))}/{DRAFT}) — md-profile.md와 rules.md의 [draft] "
                      "항목을 보고 0건이 될 때까지 고친다.\n" + "\n".join(lines))
    if blocks:
        print(json.dumps({"decision": "block", "reason": "\n".join(blocks)}, ensure_ascii=False))


if __name__ == "__main__":
    # 안전망이 실패를 만들면 안 된다 — 예상 밖 페이로드로 예외가 나도 0으로 끝낸다(종전 exit 1 → Codex 'hook exited with code 1')
    try:
        main()
    except Exception as e:                                    # noqa: BLE001 — 훅 경계
        print(f"lint_draft_hook: 예외로 린트를 건너뜀 — {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(0)
