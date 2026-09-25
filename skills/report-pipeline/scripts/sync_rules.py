#!/usr/bin/env python3
"""규칙 시드 동기화 — 플러그인이 갱신한 규칙이 설치자의 운영 규칙(state_dir/rules.md)에 도달하게 한다.

배경('26.9.25 프로덕션 분석): 운영 규칙은 첫 실행 때 `references/rules-seed.md`를 한 번 복사한 뒤로 시드와
따로 논다. 그래서 플러그인을 갱신해도 새 규칙(R088~R094)이나 정정(R008 bullet 표기)이 기존 설치자에게는
영영 들어가지 않았다. 저자 환경은 운영본이 곧 시드의 원본이라(test_value_drift 양방향 검사) 이 스크립트가
아무것도 바꾸지 않는다.

  - 시드에만 있는 규칙 → 운영본 끝에 시드 순서대로 덧붙인다(--apply). 새 규칙이 들어가는 유일한 경로.
  - 시드가 '대체됨·정정됨·폐지' 표기를 단 규칙 → 운영본의 같은 번호 줄을 시드 줄로 바꾼다(superseded, --apply).
    대체 표기가 설치자에게 닿지 않으면 틀린 값이 계속 살아 움직인다(CLAUDE.md 규칙 복리축적).
  - 번호만 같고 내용이 전혀 다른 규칙 → 설치자 로컬 규칙이 시드 번호를 선점한 것이다(collision). 바꾸지 않고
    알린다 — 로컬 규칙을 R9NN 대역으로 옮긴 뒤 다시 --apply하면 시드 규칙이 들어간다.
  - 그 밖에 양쪽 본문이 다른 규칙 → 바꾸지 않고 보고만 한다(changed). 설치자가 고친 것인지 시드가 정정된 것인지는
    사람이 판단한다 — 자동으로 덮으면 설치자의 축적을 지운다.
  - 운영본에만 있는 규칙 → 설치자가 쌓은 것이다. 그대로 둔다(local_only).
  - --apply 없이는 아무것도 쓰지 않는다(운영본이 없어도 — 첫 실행 시드 복사도 --apply 때만).

    sync_rules.py [--apply] [--state <rules.md>] [--seed <rules-seed.md>]

exit 0: 처리 완료(JSON 보고) | exit 2: 인자·파일 오류
"""
import argparse
import difflib
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
SEED = HERE.parent / "references" / "rules-seed.md"
RULE = re.compile(r"^- (R\d+) (?:\[[a-z]+\])+ .*$", re.M)     # consolidate_rules.RULE과 같은 폭
SUPERSEDED = re.compile(r"\*\*\[[^\]]*(?:대체됨|정정됨|폐지)[^\]]*\]\*\*")
SAME_RULE = 0.5          # 본문 유사도 이 미만이면 번호만 같은 다른 규칙(설치자 로컬 규칙의 번호 선점)으로 본다


def rules(text):
    """{R번호: 규칙 한 줄} — 파일 순서 유지."""
    return {m.group(1): m.group(0) for m in RULE.finditer(text)}


def _body(line):
    return re.sub(r"^- R\d+ (?:\[[a-z]+\])+ ", "", line.strip())


def plan(state_text, seed_text):
    state, seed = rules(state_text), rules(seed_text)
    out = {"added": [], "superseded": [], "collision": [], "changed": [],
           "local_only": [k for k in state if k not in seed]}
    for k in seed:
        if k not in state:
            out["added"].append(k)
        elif seed[k].strip() != state[k].strip():
            # 번호 선점부터 본다 — 대체 표기가 붙은 시드 번호를 설치자 로컬 규칙이 쓰고 있으면 덮지 않는다
            # (종전에는 대체 표기를 먼저 봐 로컬 규칙이 --apply에 지워졌다 — '26.9.25 코드 리뷰 #2). 표기는 빼고 견준다
            if difflib.SequenceMatcher(None, _body(SUPERSEDED.sub("", seed[k])), _body(state[k])).ratio() < SAME_RULE:
                out["collision"].append(k)
            elif SUPERSEDED.search(seed[k]) and not SUPERSEDED.search(state[k]):
                out["superseded"].append(k)
            else:
                out["changed"].append(k)
    return out


def apply(state_path, seed_text, added, superseded=()):
    """시드에만 있는 규칙은 끝에 덧붙이고, 시드가 대체·정정 표기를 단 규칙은 그 줄만 시드 줄로 바꾼다.
    나머지 줄은 한 글자도 건드리지 않는다."""
    if not added and not superseded:
        return
    seed = rules(seed_text)
    text = state_path.read_text(encoding="utf-8")
    for k in superseded:
        text = re.sub(rf"^- {k} (?:\[[a-z]+\])+ .*$", lambda m, k=k: seed[k], text, count=1, flags=re.M)
    if not text.endswith("\n"):
        text += "\n"
    if added:
        text += "\n".join(seed[k] for k in added) + "\n"
    state_path.write_text(text, encoding="utf-8")


def default_state():
    cfg = json.loads(subprocess.run([sys.executable, str(HERE / "harness_config.py")],
                                    capture_output=True, text=True, timeout=20).stdout)
    return pathlib.Path(cfg["state_dir"]) / "rules.md"


def main(argv=None):
    ap = argparse.ArgumentParser(description="규칙 시드 → 운영 규칙 동기화(시드에만 있는 규칙 추가)")
    ap.add_argument("--apply", action="store_true", help="시드에만 있는 규칙을 운영본에 덧붙인다")
    ap.add_argument("--state", type=pathlib.Path, help="운영 규칙 파일(기본: 설정의 state_dir/rules.md)")
    ap.add_argument("--seed", type=pathlib.Path, default=SEED, help="시드 파일(기본: references/rules-seed.md)")
    a = ap.parse_args(argv)
    try:
        state_path = a.state or default_state()
        seed_text = a.seed.read_text(encoding="utf-8")
        if not state_path.exists():
            # 첫 실행 — 시드를 그대로 복사하는 것이 SKILL.md §0-4 절차다. 점검(--apply 없음)은 아무것도 쓰지 않는다
            if a.apply:
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(seed_text, encoding="utf-8")
            print(json.dumps({"state": str(state_path), "missing": True, "seeded": a.apply, "added": [],
                              "superseded": [], "collision": [], "changed": [], "local_only": []},
                             ensure_ascii=False, indent=1))
            return 0
        result = plan(state_path.read_text(encoding="utf-8"), seed_text)
    except (OSError, ValueError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if a.apply:
        apply(state_path, seed_text, result["added"], result["superseded"])
    print(json.dumps(dict({"state": str(state_path), "applied": a.apply}, **result), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
