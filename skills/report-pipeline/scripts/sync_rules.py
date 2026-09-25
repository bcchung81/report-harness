#!/usr/bin/env python3
"""규칙 시드 동기화 — 플러그인이 갱신한 규칙이 설치자의 운영 규칙(state_dir/rules.md)에 도달하게 한다.

배경('26.9.25 프로덕션 분석): 운영 규칙은 첫 실행 때 `references/rules-seed.md`를 한 번 복사한 뒤로 시드와
따로 논다. 그래서 플러그인을 갱신해도 새 규칙(R088~R094)이나 정정(R008 bullet 표기)이 기존 설치자에게는
영영 들어가지 않았다. 저자 환경은 운영본이 곧 시드의 원본이라(test_value_drift 양방향 검사) 이 스크립트가
아무것도 바꾸지 않는다.

  - 시드에만 있는 규칙 → 운영본 끝에 시드 순서대로 덧붙인다(--apply). 새 규칙이 들어가는 유일한 경로.
  - 운영본 줄이 배포한 적 있는 옛 시드 줄 그대로면(계보 `rules-seed.lineage.json`에 지문이 있으면) 설치자가 손대지
    않은 것이다 → 새 시드 줄로 바꾸고(updated), 시드에서 폐지된 번호면 지운다(retired). 계보가 없던 때는 0.4.0
    설치자의 옛 시드 줄 7건을 '번호 충돌'로 오판해 새 값이 들어가지 않았고, 폐지된 R053이 운영본에 살아 있었다
    ('26.9.25 격리 설치 재현).
  - 시드가 '대체됨·정정됨·폐지' 표기를 단 규칙인데 설치자가 고친 줄 → 본문은 두고 그 표기만 줄 앞머리에 붙인다
    (superseded, --apply). 대체 표기가 설치자에게 닿지 않으면 틀린 값이 계속 살아 움직이고, 줄을 통째로 바꾸면 설치자가
    덧붙인 내용이 사라진다('26.9.25 코드 리뷰 #3).
  - 번호만 같고 내용이 전혀 다른 규칙 → 설치자 로컬 규칙이 시드 번호를 선점한 것이다(collision). 바꾸지 않고
    알린다 — 로컬 규칙을 R9NN 대역으로 옮긴 뒤 다시 --apply하면 시드 규칙이 들어간다.
  - 그 밖에 양쪽 본문이 다른 규칙 → 바꾸지 않고 보고만 한다(changed). 설치자가 고친 것인지 시드가 정정된 것인지는
    사람이 판단한다 — 자동으로 덮으면 설치자의 축적을 지운다.
  - 운영본에만 있고 옛 시드 줄도 아닌 규칙 → 설치자가 쌓은 것이다. 그대로 둔다(local_only).
  - 경위 로그(rules-history.md)도 맞춘다 — 없으면 시드를 복사하고, 있으면 시드에만 있는 `## R0NN` 절을 덧붙인다
    (history_added). 결번(폐지·흡수) 기록이 없으면 규칙 점검이 흡수된 번호를 '죽은 참조'로 본다('26.9.25 격리 설치
    재현: 새 설치의 자가진단이 R050·R053·R081~R083·R086을 죽은 참조로 경고).
  - --apply 없이는 아무것도 쓰지 않는다(운영본이 없어도 — 첫 실행 시드 복사도 --apply 때만).

    sync_rules.py [--apply] [--state <rules.md>] [--seed <rules-seed.md>]
    sync_rules.py --next-id [--state <rules.md>]     # 새 규칙 번호 — 저자 환경은 시드 대역, 설치자는 R9NN

exit 0: 처리 완료(JSON 보고) | exit 2: 인자·파일 오류
"""
import argparse
import base64
import difflib
import hashlib
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
SEED = HERE.parent / "references" / "rules-seed.md"
LINEAGE = HERE.parent / "references" / "rules-seed.lineage.json"   # 배포한 시드 줄 지문 — scripts/build_seed_lineage.py
HISTORY = "rules-history.md"         # 시드 옆(references/)과 운영 규칙 옆(state_dir/)에 같은 이름으로 둔다
HIST_SECTION = re.compile(r"^## (R\d+)\b.*?(?=^## |\Z)", re.M | re.S)
RULE = re.compile(r"^- (R\d+) (?:\[[a-z]+\])+ .*$", re.M)     # consolidate_rules.RULE과 같은 폭
MARKER = re.compile(r"<!--\s*consolidated-at:\s*R(\d+)\s*-->")    # consolidate_rules.MARKER와 같은 꼴
SUPERSEDED = re.compile(r"\*\*\[[^\]]*(?:대체됨|정정됨|폐지)[^\]]*\]\*\*")
SAME_RULE = 0.5          # 본문 유사도 이 미만이면 번호만 같은 다른 규칙(설치자 로컬 규칙의 번호 선점)으로 본다


def rules(text):
    """{R번호: 규칙 한 줄} — 파일 순서 유지."""
    return {m.group(1): m.group(0) for m in RULE.finditer(text)}


def _body(line):
    return re.sub(r"^- R\d+ (?:\[[a-z]+\])+ ", "", line.strip())


def fingerprint(line):
    """규칙 줄 지문 — sha1 앞 10바이트를 base32(16자)로. 16진수는 숫자열이 전화번호 꼴로 나와 배포 PII 가드에
    걸렸다('26.9.25). base32 글자에는 0·1이 없어 그런 꼴이 생기지 않는다."""
    return base64.b32encode(hashlib.sha1(line.strip().encode("utf-8")).digest()[:10]).decode("ascii").lower()


def load_lineage(path=None):
    """{R번호: 배포한 적 있는 줄 지문 집합} — 파일이 없거나 깨졌으면 빈 계보(옛 동작: 고친 줄로 본다)."""
    try:
        data = json.loads(pathlib.Path(path or LINEAGE).read_text(encoding="utf-8"))
        return {k: set(v) for k, v in data["rules"].items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {}


def plan(state_text, seed_text, lineage=None):
    state, seed = rules(state_text), rules(seed_text)
    lineage = load_lineage() if lineage is None else lineage
    pristine = lambda k: fingerprint(state[k]) in lineage.get(k, ())   # noqa: E731 — 손대지 않은 옛 시드 줄
    out = {"added": [], "updated": [], "superseded": [], "collision": [], "changed": [], "retired": [],
           "local_only": [], "marker": None}
    # 통합 마커도 시드를 따른다 — 옛 마커(R068)에 머물면 설치자가 손쓸 수 없는 '통합 요구' 경고가 영구히 뜬다
    sm, tm = MARKER.search(seed_text), MARKER.search(state_text)
    if sm and (not tm or int(tm.group(1)) < int(sm.group(1))):
        out["marker"] = f"R{sm.group(1)}"
    for k in state:
        if k not in seed:
            out["retired" if pristine(k) else "local_only"].append(k)
    for k in seed:
        if k not in state:
            out["added"].append(k)
        elif seed[k].strip() == state[k].strip():
            continue
        elif pristine(k):
            out["updated"].append(k)
        else:
            # 설치자가 고친 줄 — 번호 선점부터 본다. 대체 표기가 붙은 시드 번호를 설치자 로컬 규칙이 쓰고 있으면 덮지
            # 않는다(종전에는 대체 표기를 먼저 봐 로컬 규칙이 --apply에 지워졌다 — '26.9.25 코드 리뷰 #2). 표기는 빼고 견준다
            if difflib.SequenceMatcher(None, _body(SUPERSEDED.sub("", seed[k])), _body(state[k])).ratio() < SAME_RULE:
                out["collision"].append(k)
            elif SUPERSEDED.search(seed[k]) and not SUPERSEDED.search(state[k]):
                out["superseded"].append(k)
            else:
                out["changed"].append(k)
    return out


def apply(state_path, seed_text, added, replaced=(), retired=(), marker=None, marked=()):
    """시드에만 있는 규칙은 끝에 덧붙이고, replaced(손대지 않은 옛 시드 줄) 번호는 그 줄을 시드 줄로 바꾸고, retired
    (시드에서 폐지된 옛 시드 줄) 번호는 그 줄을 지운다. marked(설치자가 고친 줄인데 시드가 대체·정정 표기를 단 번호)는
    본문을 두고 표기만 태그 뒤에 붙인다. marker가 오면 통합 마커를 그 번호로 맞춘다. 나머지 줄은 한 글자도 건드리지 않는다."""
    if not added and not replaced and not retired and not marker and not marked:
        return
    seed = rules(seed_text)
    text = state_path.read_text(encoding="utf-8")
    if marker:
        tag = f"<!-- consolidated-at: {marker} -->"
        text = MARKER.sub(tag, text, count=1) if MARKER.search(text) else text.replace("\n", "\n" + tag + "\n", 1)
    for k in replaced:
        text = re.sub(rf"^- {k} (?:\[[a-z]+\])+ .*$", lambda m, k=k: seed[k], text, count=1, flags=re.M)
    for k in retired:
        text = re.sub(rf"^- {k} (?:\[[a-z]+\])+ .*\n?", "", text, count=1, flags=re.M)
    for k in marked:
        tag = SUPERSEDED.search(seed[k]).group(0)
        text = re.sub(rf"^(- {k} (?:\[[a-z]+\])+ )", lambda m, tag=tag: m.group(1) + tag + " ", text, count=1, flags=re.M)
    if not text.endswith("\n"):
        text += "\n"
    if added:
        text += "\n".join(seed[k] for k in added) + "\n"
    state_path.write_text(text, encoding="utf-8")


def history_sections(text):
    """{R번호: 절 전문} — 같은 번호가 두 번 나오면 첫 절."""
    out = {}
    for m in HIST_SECTION.finditer(text):
        out.setdefault(m.group(1), m.group(0))
    return out


def sync_history(state_path, seed_path, write):
    """경위 로그 동기화 → (없었나, 덧붙인 절 번호). write가 거짓이면 쓰지 않고 셈만 한다."""
    src, dst = seed_path.parent / HISTORY, state_path.parent / HISTORY
    if not src.is_file():
        return False, []
    seed_text = src.read_text(encoding="utf-8")
    if not dst.exists():
        if write:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(seed_text, encoding="utf-8")
        return True, sorted(history_sections(seed_text))
    have = history_sections(dst.read_text(encoding="utf-8"))
    new = {k: v for k, v in history_sections(seed_text).items() if k not in have}
    if new and write:
        text = dst.read_text(encoding="utf-8")
        text = (text if text.endswith("\n") else text + "\n") + "\n" + "\n".join(v.rstrip() + "\n" for v in new.values())
        dst.write_text(text, encoding="utf-8")
    return False, sorted(new)


LOCAL_BAND = 900     # consolidate_rules.LOCAL_BAND와 같은 값 — R9NN은 설치자 로컬 규칙


def _numbers(text, pattern):
    return {int(m.group(1)) for m in re.finditer(pattern, text, re.M)}


def next_id(state_path, seed_path=SEED):
    """새로 승격할 규칙 번호 → {"next", "band"}.

    운영 규칙이 시드를 배포하는 저장소 안에 있으면(저자 환경 — report/_harness) 시드 대역에서 다음 번호를 준다.
    결번(경위 로그의 `## R0NN`)도 건너뛴다 — 폐지 번호는 재사용하지 않는다. 그 밖(설치자)은 R9NN 대역 — 시드 번호를
    쓰면 다음 판의 같은 번호 시드 규칙과 충돌해 그 규칙이 들어가지 못한다('26.9.25 코드 리뷰 #3)."""
    state_path = pathlib.Path(state_path)
    text = state_path.read_text(encoding="utf-8") if state_path.exists() else ""
    author = any((d / "skills/report-pipeline/references/rules-seed.md").is_file() for d in state_path.resolve().parents)
    if author:
        used = _numbers(text, r"^- R(\d+) ") | _numbers(seed_path.read_text(encoding="utf-8"), r"^- R(\d+) ")
        for hist in (state_path.parent / HISTORY, seed_path.parent / HISTORY):
            if hist.is_file():
                used |= _numbers(hist.read_text(encoding="utf-8"), r"^## R(\d+)\b")
        n = max((u for u in used if u < LOCAL_BAND), default=0) + 1
        return {"next": f"R{n:03d}", "band": "seed"}
    n = max((u for u in _numbers(text, r"^- R(\d+) ") if u >= LOCAL_BAND), default=LOCAL_BAND) + 1
    return {"next": f"R{n:03d}", "band": "local"}


def default_state():
    cfg = json.loads(subprocess.run([sys.executable, str(HERE / "harness_config.py")],
                                    capture_output=True, text=True, timeout=20).stdout)
    return pathlib.Path(cfg["state_dir"]) / "rules.md"


def main(argv=None):
    ap = argparse.ArgumentParser(description="규칙 시드 → 운영 규칙 동기화(새 규칙 추가·대체 표기 반영·경위 로그)")
    ap.add_argument("--apply", action="store_true", help="시드에만 있는 규칙을 운영본에 덧붙인다")
    ap.add_argument("--next-id", action="store_true", help="새로 승격할 규칙 번호만 알려 준다(쓰지 않음)")
    ap.add_argument("--state", type=pathlib.Path, help="운영 규칙 파일(기본: 설정의 state_dir/rules.md)")
    ap.add_argument("--seed", type=pathlib.Path, default=SEED, help="시드 파일(기본: references/rules-seed.md)")
    a = ap.parse_args(argv)
    try:
        state_path = a.state or default_state()
        if a.next_id:
            print(json.dumps(next_id(state_path, a.seed), ensure_ascii=False))
            return 0
        seed_text = a.seed.read_text(encoding="utf-8")
        if not state_path.exists():
            # 첫 실행 — 시드를 그대로 복사하는 것이 SKILL.md §0-4 절차다. 점검(--apply 없음)은 아무것도 쓰지 않는다
            if a.apply:
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(seed_text, encoding="utf-8")
            hist_missing, hist_added = sync_history(state_path, a.seed, a.apply)
            print(json.dumps({"state": str(state_path), "missing": True, "seeded": a.apply, "added": [], "updated": [],
                              "superseded": [], "collision": [], "changed": [], "retired": [], "local_only": [], "marker": None,
                              "history_missing": hist_missing, "history_added": hist_added},
                             ensure_ascii=False, indent=1))
            return 0
        result = plan(state_path.read_text(encoding="utf-8"), seed_text)
        if a.apply:
            apply(state_path, seed_text, result["added"], result["updated"], result["retired"], result["marker"],
                  result["superseded"])
        result["history_missing"], result["history_added"] = sync_history(state_path, a.seed, a.apply)
    except (OSError, ValueError, KeyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(dict({"state": str(state_path), "applied": a.apply}, **result), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
