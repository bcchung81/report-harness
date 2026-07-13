#!/usr/bin/env python3
"""PostToolUse(Bash) 훅 — KCA 하네스가 생산한 HWPX를 결정론적으로 구조 검증한다.

hwpx-qa 에이전트가 validate_hwpx.py 실행을 잊거나 건너뛰어도, build_from_template.py·
inject_image.py를 부른 Bash 명령이 만든 .hwpx는 이 훅이 무조건 검증한다(안전망).

동작:
  1) Bash 명령이 하네스 HWPX 생산 스크립트를 부른 경우에만 작동(그 외 즉시 통과).
  2) 명령에서 .hwpx 경로를 추출해 실존 파일마다 validate_hwpx.py 실행.
  3) 하나라도 실패하면 decision:block + reason으로 모델에 재빌드를 알린다.
검증 실패 외에는 조용히 통과(exit 0, 출력 없음).
"""
import sys, json, re, os, subprocess

def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    cmd = (data.get("tool_input") or {}).get("command", "") or ""
    # 하네스 HWPX 생산 스크립트를 부른 명령만 대상 (validate 자체 호출은 제외)
    if not re.search(r'build_from_template\.py|inject_image\.py', cmd):
        return
    val = os.path.expanduser("~/.claude/skills/kca-report-style/scripts/validate_hwpx.py")
    if not os.path.isfile(val):
        return
    paths, seen, failures = re.findall(r'[^\s"\']+\.hwpx', cmd), set(), []
    for p in paths:
        if p in seen:
            continue
        seen.add(p)
        if not os.path.isfile(p):
            continue
        r = subprocess.run(["python3", val, p], capture_output=True, text=True)
        if r.returncode != 0:
            err = (r.stdout + r.stderr).strip()
            # 트레이스백이면 마지막 의미줄만 (피드백 간결화)
            if "Traceback" in err:
                lines = [l for l in err.splitlines() if l.strip()]
                err = lines[-1] if lines else err
            failures.append(f"[{p}] {err}")
    if failures:
        reason = ("HWPX 구조 검증 실패 (validate_hwpx.py 자동 훅) — 스타일ID 연속성·"
                  "IDRef 범위·zip/xml 무결성 문제. hwpx-qa 판정과 무관하게 재빌드 필요:\n"
                  + "\n".join(failures))
        print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))

if __name__ == "__main__":
    main()
