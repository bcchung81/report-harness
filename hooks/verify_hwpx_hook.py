#!/usr/bin/env python3
"""PostToolUse(Bash) 훅 — hwpx를 만들고 검증을 건너뛴 경우를 차단한다 (stdlib-only).

## 왜 필요한가

`hwpx-recipe.md`는 변환 뒤에 `postprocess_hwpx.py --all` →
`validate_hwpx.py structural` 순서를 요구한다. 그런데 postprocess는 **대상이 0건이어도
exit 0**을 내고, 검증을 아예 부르지 않아도 파일은 멀쩡히 만들어진다. 즉 절차를 건너뛴 산출물이
조용히 인도된다 — '26.8.7에 실제로 그렇게 배포된 건이 있었다.

린트·검증 스크립트는 "모델이 부를 때"만 돕는다. 이 훅은 모델의 협조 없이 걸린다.

## 동작

1. Bash 명령이 hwpx를 만들거나 고쳤는지 본다(생성기·후처리 스크립트 호출 여부).
2. 그 명령이 언급한 `.hwpx` 실존 파일마다 검사한다.
   - `validate_hwpx.py structural` — zip·XML 무결성, OCF 시그니처, 필수 멤버
   - 후처리 흔적 — 후처리를 거치지 않은 산출물은 `version.xml`이 없다(R043)
3. 하나라도 실패하면 `decision: block` + 사유를 돌려준다. 그 외에는 조용히 통과한다.

검증 스크립트를 찾지 못하면 아무 것도 하지 않는다 — 훅이 파이프라인을 막는 원인이 되면 안 된다.
"""
import sys, os, re, json, zipfile, subprocess

# hwpx를 새로 만들거나 제자리에서 고치는 스크립트만 대상. validate 자체 호출은 제외한다.
PRODUCER = re.compile(r"md2hwpx\.py|postprocess_hwpx\.py|patch_document|generate_document")
HWPX = re.compile(r"[^\s\"']+\.hwpx")
# 후처리를 거친 산출물이면 반드시 있는 멤버 (canonicalize_package가 상시 보강, R043)
CANONICAL_MEMBERS = ("version.xml", "META-INF/container.xml", "Contents/content.hpf")


def find_validator():
    """플러그인 루트 우선, 없으면 저장소 상대 경로."""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (root, os.path.dirname(here)):
        if not base:
            continue
        p = os.path.join(base, "skills", "report-pipeline", "scripts", "validate_hwpx.py")
        if os.path.isfile(p):
            return p
    return None


def check(path, validator):
    """(실패 사유 목록)을 반환한다. 빈 목록이면 통과."""
    fails = []
    # 훅은 매 Bash 호출 경로에 있다 — validator가 걸리면 세션 전체가 멈추므로 상한 필수
    try:
        r = subprocess.run([sys.executable, validator, "structural", path],
                           capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return [f"구조 검증 30초 초과 — validate_hwpx.py structural을 수동 실행해 확인할 것"]
    if r.returncode != 0:
        detail = (r.stdout or r.stderr).strip().splitlines()
        fails.append(f"구조 검증 실패 — {detail[-1][:200] if detail else 'exit ' + str(r.returncode)}")
    try:
        names = set(zipfile.ZipFile(path).namelist())
    except (zipfile.BadZipFile, OSError) as e:
        fails.append(f"패키지를 열 수 없음 — {e}")
        return fails
    missing = [m for m in CANONICAL_MEMBERS if m not in names]
    if missing:
        fails.append(
            f"후처리 미실행으로 보임 — 필수 멤버 없음 {missing}. "
            "`postprocess_hwpx.py <파일> --all`을 실행해야 한다(R043)")
    return fails


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        # 페이로드 스키마 변화로 안전망이 죽으면 조용히 사라지지 않게 흔적은 남긴다
        print("verify_hwpx_hook: stdin 페이로드 파싱 실패 — 훅이 검증을 건너뜀", file=sys.stderr)
        return
    cmd = ((data.get("tool_input") or {}).get("command") or "")
    if not PRODUCER.search(cmd):
        return
    validator = find_validator()
    if validator is None:
        # hwpx 생성은 감지했는데 검증기가 없다 — 무음 통과는 안전망 부재와 같다
        print("verify_hwpx_hook: validate_hwpx.py 미발견 — hwpx 검증 없이 통과함", file=sys.stderr)
        return
    report, seen = [], set()
    for p in HWPX.findall(cmd):
        p = p.strip("'\"")
        if p in seen or not os.path.isfile(p):
            continue
        seen.add(p)
        fails = check(p, validator)
        if fails:
            report.append(f"[{os.path.basename(p)}] " + " / ".join(fails))
    if report:
        print(json.dumps({
            "decision": "block",
            "reason": "hwpx 인도 전 검증이 통과하지 못했습니다. 아래를 고친 뒤 다시 만드세요.\n"
                      + "\n".join(f"- {r}" for r in report),
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
