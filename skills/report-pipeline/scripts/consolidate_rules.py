#!/usr/bin/env python3
"""rules 통합 lint (R068) — 규칙 축적을 정기 통폐합으로 되돌린다.

배경: 규칙은 "결과 보고 → 박제"로만 늘고 통폐합이 없어 두 달에 43건이 쌓였다.
길어지면 읽히지 않고, 안 읽히면 지켜지지 않고, 안 지켜지니 같은 실수가 다시 나
또 박제된다. 이 순환을 끊으려면 **증가에 통합을 강제로 맞물려야** 한다.

설계 원칙 — 자동 통합은 하지 않는다:
  · "대체됨 표기가 있으면 통합"은 위험하다. 실측 결과 표기된 5건 중 넷은
    base ← 확장/정정 관계였고(R015←R035, R019←R025, R033←R039, R036←R041·R042),
    지웠다면 base 규칙이 사라져 체계가 무너졌다.
  · 기계가 판정할 수 있는 것은 **피참조 0건**까지다. 고유 내용이 신 규칙에
    흡수됐는지는 사람이 읽어야 안다. 그래서 이 스크립트는 **후보를 제시**하고
    임계 초과 시 실패시킬 뿐, 스스로 병합하지 않는다.

사용:
  consolidate_rules.py --check [rules.md]     현황 점검 (exit 1 = 통합 필요)
  consolidate_rules.py --mark  [rules.md]     통합 완료 마커를 현재 최대 규칙로 갱신
"""
import sys
import re
import pathlib

RULE = re.compile(r"^- (R\d+) ((?:\[[a-z]+\])+) (.*)$", re.M)
HEAD = re.compile(r"^- (R\d+) (?:\[[a-z]+\])+", re.M)
MARKER = re.compile(r"<!--\s*consolidated-at:\s*(R\d+)\s*-->")
GROWTH_LIMIT = 10          # 마지막 통합 이후 이만큼 늘면 통합 요구
ROOT = pathlib.Path(__file__).resolve().parents[3]
DEFAULT = ROOT / "report/_harness/rules.md"


def analyze(path):
    text = pathlib.Path(path).read_text(encoding="utf-8")
    hist_p = pathlib.Path(path).parent / "rules-history.md"
    hist = hist_p.read_text(encoding="utf-8") if hist_p.exists() else ""

    rules = RULE.findall(text)
    heads = HEAD.findall(text)
    body = {r: b for r, _, b in rules}
    hist_ids = set(re.findall(r"^## (R\d+)", hist, re.M))

    # ① 파서 정합 — 선두 매칭과 본문 매칭이 어긋나면 이후 판정이 전부 무효
    parse_gap = sorted(set(heads) - set(body))

    # ② 피참조 0건 + 폐지·대체 표기 → 통합 후보 (기계가 판정 가능한 최대치)
    refs = {}
    for r, b in body.items():
        for m in set(re.findall(r"R0\d\d", b)):
            if m != r:
                refs.setdefault(m, []).append(r)
    candidates = [r for r, b in body.items()
                  if not refs.get(r) and re.match(r"\s*\*\*\[[^\]]*(폐지|흡수|대체)", b)]

    # ③ 죽은 참조 — rules에도 history에도 없는 번호를 가리킴
    known = set(body) | hist_ids
    dead = sorted({m for b in body.values() for m in re.findall(r"R0\d\d", b)} - known)

    # ④ 근거 등급 누락 (규약: 등급 없이 승격 금지)
    ungraded = sorted(r for r, b in body.items() if "(근거" in b and "근거[" not in b)

    # ④-1 본문 비대 (규약: 1,000자 초과분은 경위를 rules-history로 내리고 포인터만 남긴다
    #      — 길면 안 읽히고, 안 읽히면 안 지켜진다)
    oversized = sorted(f"{r}({len(b)}자)" for r, b in body.items() if len(b) > 1000)

    # ⑤ 증가분 — 마지막 통합 마커 대비
    mk = MARKER.search(text)
    marked = int(mk.group(1)[1:]) if mk else 0
    latest = max((int(r[1:]) for r in body), default=0)
    growth = latest - marked

    return {"path": str(path), "count": len(body), "parse_gap": parse_gap,
            "candidates": sorted(candidates), "dead_refs": dead, "ungraded": ungraded,
            "oversized": oversized,
            "marked_at": f"R{marked:03d}" if marked else "없음",
            "latest": f"R{latest:03d}", "growth": growth, "limit": GROWTH_LIMIT,
            "chars": sum(len(b) for b in body.values())}


def check(path):
    a = analyze(path)
    fail = []
    print(f"규칙 {a['count']}개 · {a['chars']:,}자 · 마지막 통합 {a['marked_at']} → 현재 {a['latest']} (+{a['growth']})")

    if a["parse_gap"]:
        fail.append(f"파서 정합 깨짐 — 본문 파싱 실패: {a['parse_gap']}")
    if a["dead_refs"]:
        fail.append(f"죽은 참조 — rules·history 어디에도 없음: {a['dead_refs']}")
    if a["ungraded"]:
        fail.append(f"근거 등급 누락: {a['ungraded']}")
    if a["oversized"]:
        fail.append(f"본문 1,000자 초과 — 경위를 rules-history.md로 이관: {a['oversized']}")
    if a["growth"] >= GROWTH_LIMIT:
        fail.append(f"마지막 통합 이후 {a['growth']}건 증가 (임계 {GROWTH_LIMIT}) — 통폐합 후 --mark")

    if a["candidates"]:
        print(f"  통합 후보(피참조 0 + 폐지·흡수 표기): {a['candidates']}")
    for f in fail:
        print(f"  ✗ {f}")
    if not fail:
        print("  ✓ 통합 요구 없음")
    return 1 if fail else 0


def mark(path):
    p = pathlib.Path(path)
    text = p.read_text(encoding="utf-8")
    latest = analyze(path)["latest"]
    tag = f"<!-- consolidated-at: {latest} -->"
    text = MARKER.sub(tag, text) if MARKER.search(text) else text.replace("\n", "\n" + tag + "\n", 1)
    p.write_text(text, encoding="utf-8")
    print(f"통합 완료 마커 갱신 → {latest}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    mode = args[0] if args else "--check"
    target = args[1] if len(args) > 1 else DEFAULT
    sys.exit(mark(target) if mode == "--mark" else check(target))
