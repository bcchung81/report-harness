#!/usr/bin/env python3
"""PostToolUse 훅 — hwpx를 만들고 검증을 건너뛴 경우를 차단한다 (stdlib-only).

## 왜 필요한가

`hwpx-recipe.md`는 변환 뒤에 `postprocess_hwpx.py --all` →
`validate_hwpx.py structural` 순서를 요구한다. 그런데 postprocess는 **대상이 0건이어도
exit 0**을 내고, 검증을 아예 부르지 않아도 파일은 멀쩡히 만들어진다. 즉 절차를 건너뛴 산출물이
조용히 인도된다 — '26.8.7에 실제로 그렇게 배포된 건이 있었다.

린트·검증 스크립트는 "모델이 부를 때"만 돕는다. 이 훅은 모델의 협조 없이 걸린다.

## 감시 대상은 두 계통이다

파이프라인의 주 생성 경로는 Bash가 아니라 kordoc **MCP**(`generate_document`)다. 훅이 Bash만
보던 동안 그 경로는 사각지대였다 — 정작 사고가 난 경로가 안 잡히고, 후처리를 이미 부른(즉
안전한) 경우에만 훅이 돌았다.

두 계통은 검사 강도가 다르다. 이건 편의가 아니라 사실 관계다('26.8.11 실측):

- **생성 단계**(`generate_document`·`patch_document`): 산출물에 `version.xml`이 없고 디렉터리
  엔트리가 남아 있다 — 그걸 채우는 게 뒤따르는 `postprocess_hwpx.py`(R043 `canonicalize_package`)다.
  따라서 이 시점에 `structural`을 걸면 **정상 흐름마다 실패**한다. 여기서는 zip·XML 무결성만
  보고, 남은 §3.5·§4-1을 비차단 리마인더로 모델에 되돌린다.
- **정합 단계**(`postprocess_hwpx.py`·`md2hwpx.py`): 산출물이 그 자체로 패키지 정합이어야 한다.
  `structural` 전량 + 필수 멤버 검사를 걸고, 실패하면 `decision: block`.

검증 스크립트를 찾지 못하면 아무 것도 하지 않는다 — 훅이 파이프라인을 막는 원인이 되면 안 된다.
"""
import sys, os, re, json, zipfile, subprocess
import xml.etree.ElementTree as ET

# 산출물이 그 자체로 패키지 정합이어야 하는 도구 — 여기서 version.xml이 없으면 후처리 누락이다.
FINALIZER = re.compile(r"md2hwpx\.py|postprocess_hwpx\.py")
# 정합화 이전 단계의 생성기. 도구명(mcp__kordoc__generate_document)과 Bash 명령 양쪽에서 찾는다.
GENERATOR = re.compile(r"generate_document|patch_document")
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


def strings(v):
    """tool_input 안의 모든 문자열. MCP 도구는 경로 인자 이름이 제각각이라 값 전체를 훑는다."""
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from strings(x)


def targets(data):
    """(생산자인가, 정합까지 볼 단계인가, hwpx 후보 경로)."""
    tool = data.get("tool_name") or ""
    ti = data.get("tool_input") or {}
    if tool.startswith("mcp__"):
        if not GENERATOR.search(tool):
            return False, False, []
        return True, False, [m for s in strings(ti) for m in HWPX.findall(s)]
    cmd = ti.get("command") or ""
    if FINALIZER.search(cmd):
        return True, True, HWPX.findall(cmd)
    if GENERATOR.search(cmd):
        return True, False, HWPX.findall(cmd)
    return False, False, []


def integrity(path):
    """생성 직후 단계에서 판정 가능한 것 — zip·XML 무결성뿐이다(패키지 정합은 아직 미완)."""
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad:
                return [f"zip 손상 — {bad}"]
            for n in z.namelist():
                if n.endswith(".xml"):
                    try:
                        ET.fromstring(z.read(n))
                    except ET.ParseError as e:
                        return [f"{n} 파싱 실패 — {e}"]
    except (zipfile.BadZipFile, OSError) as e:
        return [f"패키지를 열 수 없음 — {e}"]
    return []


def missing_canonical(path):
    try:
        names = set(zipfile.ZipFile(path).namelist())
    except (zipfile.BadZipFile, OSError):
        return []
    return [m for m in CANONICAL_MEMBERS if m not in names]


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
    is_producer, canonical, candidates = targets(data)
    if not is_producer:
        return
    paths, seen = [], set()
    for p in candidates:
        p = p.strip("'\"")
        if p not in seen and os.path.isfile(p):
            seen.add(p)
            paths.append(p)
    if not paths:
        return
    report, pending = [], []
    if canonical:
        validator = find_validator()
        if validator is None:
            # hwpx 생성은 감지했는데 검증기가 없다 — 무음 통과는 안전망 부재와 같다
            print("verify_hwpx_hook: validate_hwpx.py 미발견 — hwpx 검증 없이 통과함", file=sys.stderr)
            return
        for p in paths:
            fails = check(p, validator)
            if fails:
                report.append(f"[{os.path.basename(p)}] " + " / ".join(fails))
    else:
        for p in paths:
            fails = integrity(p)
            if fails:
                report.append(f"[{os.path.basename(p)}] " + " / ".join(fails))
            elif missing_canonical(p):
                pending.append(os.path.basename(p))
    if report:
        print(json.dumps({
            "decision": "block",
            "reason": "hwpx 인도 전 검증이 통과하지 못했습니다. 아래를 고친 뒤 다시 만드세요.\n"
                      + "\n".join(f"- {r}" for r in report),
        }, ensure_ascii=False))
    elif pending:
        # 차단이 아니라 리마인더다 — 이 시점의 미정합은 정상이고, 매번 막으면 훅이 소음이 된다
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext":
                f"생성 단계까지만 끝난 hwpx입니다({', '.join(pending)}). hwpx-recipe.md §3.5 "
                "`postprocess_hwpx.py <파일> --all`과 §4-1 `validate_hwpx.py structural`이 "
                "아직 실행되지 않았습니다(R043 필수 멤버 미보강). 이 상태로 인도하면 양식 미정합본입니다.",
        }}, ensure_ascii=False))


if __name__ == "__main__":
    main()
