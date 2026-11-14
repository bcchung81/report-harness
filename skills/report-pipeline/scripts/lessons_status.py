#!/usr/bin/env python3
"""교훈(lessons.jsonl) 처리 현황과 규칙 승격 후보 — 복리축적의 '2회 반복 → R0NN' 흐름을 눈에 보이게 한다. stdlib-only.

배경('26.11.14 하네스 검토, Fable F3): kind가 붙은 교훈 101줄 중 promoted:true가 0건이었다. 승격 표시가
`promoted`·`rule`·`resolved_by`(R번호) 세 갈래로 섞였고, '같은 지적 2회'를 세는 도구가 없어 반복 지적이 규칙으로
올라가지 않았다. 자가진단(doctor)은 결함·기능만 세어 열린 내용·선호 교훈이 드러나지도 않았다.

이 스크립트가 하는 일은 셋뿐이다 — 판단(승격 여부)은 사람이 한다.
1. 상태 정규화: promoted(규칙으로 올라감) · resolved(코드·문서로 고침) · open
2. kind × 상태 집계
3. 열린 content 교훈 중 반복 후보 묶음 — 같은 `topic`, 핵심어가 3개 이상 겹치는 쌍, 기록자가 '재발'로 적은 줄.
   낱말 겹침은 의미상 재발을 잘 못 잡는다 — 같은 지적이면 기록 때 `topic`(짧은 영문·한글 슬러그)을 같게 단다.

    python3 lessons_status.py [--path lessons.jsonl] [--json]
"""
import sys
import re
import json
import argparse
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

KINDS = ("content", "defect", "feature", "preference")
TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")
# 반복 판정에서 뺄 흔한 낱말 — 어느 교훈에나 나오는 절차어·조사 붙은 형태
STOP = {"사용자", "지적", "초안", "보고서", "게이트", "리뷰", "코멘트", "문구", "내용", "항목", "본문", "표를", "표에",
        "있음", "없음", "하지", "않아", "않음", "했다", "한다", "에서", "으로", "그대로", "때문", "경우", "대한",
        "관련", "위해", "통해", "다시", "같은", "이번", "종전", "실제", "기준", "적용", "필요", "확인", "the"}
MIN_SHARED = 3
MIN_OVERLAP = 0.3
# 기록자가 스스로 반복이라고 적은 교훈 — 낱말 겹침으로는 못 잡는 의미상 재발('여섯 질문' → '5개 안건' 등)
SELF_REPEAT = re.compile(r"재발|같은 지적|반복 지적|또 지적|다시 지적")


def state(row):
    """promoted(규칙 승격) · resolved(코드·문서 조치) · open."""
    rb = str(row.get("resolved_by") or "")
    if row.get("promoted") is True or row.get("rule") or rb.startswith("R"):
        return "promoted"
    if rb or row.get("harness_defect") is False:
        return "resolved"
    return "open"


def kind_of(row):
    k = row.get("kind")
    if k in KINDS:
        return k
    return "defect" if row.get("harness_defect") else "unknown"


def tokens(text):
    return {t for t in TOKEN.findall(text or "") if t not in STOP}


def repeat_groups(rows):
    """열린 content 교훈의 반복 후보 묶음 — topic이 같거나 핵심어가 MIN_SHARED개 이상·겹침 비율 MIN_OVERLAP 이상."""
    items = [r for r in rows if kind_of(r) == "content" and state(r) == "open"]
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    toks = [tokens(r.get("feedback", "") + " " + r.get("fix", "")) for r in items]
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            ti, tj = items[i].get("topic"), items[j].get("topic")
            shared = toks[i] & toks[j]
            same_topic = ti and ti == tj
            similar = len(shared) >= MIN_SHARED and len(shared) / max(1, min(len(toks[i]), len(toks[j]))) >= MIN_OVERLAP
            if same_topic or similar:
                parent[find(i)] = find(j)
    groups = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(i)
    out = []
    for idx in groups.values():
        if len(idx) < 2:
            continue
        shared = set.intersection(*(toks[i] for i in idx))
        out.append({"count": len(idx), "why": "topic·핵심어",
                    "dates": [items[i].get("date") for i in idx],
                    "shared": sorted(shared)[:8],
                    "feedback": [items[i].get("feedback", "")[:80] for i in idx]})
    grouped = {i for g in groups.values() if len(g) >= 2 for i in g}
    for i, r in enumerate(items):
        if i not in grouped and SELF_REPEAT.search(r.get("feedback", "") + " " + r.get("fix", "")):
            out.append({"count": 2, "why": "기록자 표시(재발)", "dates": [r.get("date")],
                        "shared": [], "feedback": [r.get("feedback", "")[:80]]})
    return sorted(out, key=lambda g: -g["count"])


def summarize(rows):
    table = {k: {"open": 0, "resolved": 0, "promoted": 0} for k in KINDS + ("unknown",)}
    for r in rows:
        table[kind_of(r)][state(r)] += 1
    return {"total": len(rows), "by_kind": {k: v for k, v in table.items() if sum(v.values())},
            "repeat_candidates": repeat_groups(rows)}


def load(path):
    rows = []
    for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def default_path():
    from harness_config import load_config                 # noqa: E402  (경로 규약 단독 출처)
    return pathlib.Path(load_config()["state_dir"]) / "lessons.jsonl"


def main(argv=None):
    ap = argparse.ArgumentParser(description="교훈 처리 현황과 규칙 승격 후보")
    ap.add_argument("--path", help="lessons.jsonl 경로(기본: 설정의 state_dir)")
    ap.add_argument("--json", action="store_true", help="JSON으로 출력")
    a = ap.parse_args(argv)
    path = pathlib.Path(a.path) if a.path else default_path()
    if not path.is_file():
        print(json.dumps({"error": f"lessons.jsonl 없음: {path}"}, ensure_ascii=False))
        return 2
    s = summarize(load(path))
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
        return 0
    print(f"교훈 {s['total']}줄")
    for k, v in s["by_kind"].items():
        print(f"  {k:10s} 열림 {v['open']:3d} · 조치 {v['resolved']:3d} · 승격 {v['promoted']:3d}")
    groups = s["repeat_candidates"]
    print(f"\n열린 content 반복 후보 {len(groups)}묶음 — 사람이 보고 승격(R번호: sync_rules.py --next-id)·통합·기각을 정한다")
    for g in groups:
        print(f"  [{g['count']}회·{g['why']}] {', '.join(g['dates'])}" + (f" · 공통어 {', '.join(g['shared'])}" if g['shared'] else ""))
        for f in g["feedback"]:
            print(f"     - {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
