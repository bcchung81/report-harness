#!/usr/bin/env python3
"""KCA 개조식 보고서 MD 기계 린트.

kca-style-lint 체크리스트 중 결정론 판정이 가능한 규칙을 스크립트로 검사한다.
- 반려(violations): L1 명사형 종결, L4 □ 표제, L7 제목·발신, L11 □당 ㅇ≤3,
  L12 본문 예산(ㅇ≤18·표≤2), L13 각주 마커↔정의 정합, L13b ㅇ당 각주 총량,
  L16 향후계획 시점, L19 붙임 요약 구조, L22 BLUF(임원·기관장)
- 확인 요망(warnings): L2/L3 2줄 길이 휴리스틱, L5 가운뎃점 나열, L6 괄호 리드,
  L15 붙임 분량 휴리스틱, L17 중복 문구, L18 구문 단조, L22 BLUF(그 외 대상)
의미 판단이 필요한 규칙(L10 날조 수치·L14 통합·L20 표 전환·L21 프로파일·30초 테스트)은
kca-style-auditor(LLM)가 담당한다. 임계값 근거는 kca-report-layout(SSOT) §1~§9.
"""
import argparse
import json
import re
import sys
import unicodedata

# 2줄 규칙 휴리스틱(표시폭: 한글 2·영숫자 1, 15pt 본문 한 줄 ≈ 폭 90 가정)
ITEM_WIDTH_MIN = 60    # 미만이면 앙상한 한 줄 의심 (L2)
ITEM_WIDTH_MAX = 200   # 초과면 2줄 초과 의심 (L3)
SECTION_TITLE_WIDTH_MAX = 40   # □ 표제 폭 상한 (L4)
BODY_ITEM_MAX = 18     # 본문 총 ㅇ 상한 (L12, layout §1)
BODY_TABLE_MAX = 2     # 본문 표 상한 (L12, layout §1)
SECTION_ITEM_MAX = 3   # □당 ㅇ 상한 (L11, layout §2)
APPENDIX_WIDTH_MIN = 2400  # 붙임 합산 최소 분량 휴리스틱 ≈ 1페이지 (L15, layout §5)
BODY_TABLE_ROWS_MAX = 8    # 본문 표 데이터 행 상한 ≈ 반 페이지 (L23, layout §8)

DATE_RE = re.compile(r"'\d{2}\.\s*(?:\d{1,2}|__)\s*월")
MARKER_RE = re.compile(r"(?<![*(])([A-Za-z가-힣0-9]+(?:\([A-Za-z0-9가-힣·\- ]+\))?)\*(?!\*)")
FOOTNOTE_DEF_RE = re.compile(r"^[*＊]\s*(.+?)\s*[::]")
SENDER_RE = re.compile(r"^<.+>$")
ENUM_RE = re.compile(r"\S+[와과]\s+\S+[와과]\s|,\s*그리고\b")
LEAD_RE = re.compile(r"^\([^)]{1,12}\)")
CONNECTORS = ("해,", "로,", "하여 ", "통해 ")
# L24 — 법령 조항호목 한국식 표기 위반 (독일식 §·원문자 항·조항 띄어쓰기)
LEGAL_BAD_RES = (
    (re.compile(r"§"), "독일식 '§' 기호", "「법령명」 제N조제N항제N호 한글 표기로"),
    (re.compile(r"제\d+조(?:의\d+)?[①-⑮㉑-㉟]"), "조 뒤 원문자 항",
     "원문자 대신 '제N항' — 예: 제45조③ → 제45조제3항"),
    (re.compile(r"제\d+조(?:의\d+)?\s+제\d+항"), "조·항 띄어쓰기",
     "조항호목은 붙여쓰기 — 예: 제66조 제1항 → 제66조제1항"),
)


def display_width(text):
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def _base_term(term):
    return re.sub(r"\(.*?\)", "", term).strip()


def _ends_verbal(text):
    t = text.rstrip()
    while t and t[-1] in ".·…)]』」\"'":
        t = t[:-1].rstrip()
    return bool(t) and t[-1] in "다까"


def parse(md):
    doc = {"title": None, "sender": None, "gist": [], "sections": [], "footnote_defs": [],
           "table_blocks": []}
    body_ended = False
    section = None
    last_item = None
    in_table = False
    pending_caption = None
    for line in md.splitlines():
        if line.startswith("# ") and doc["title"] is None:
            doc["title"] = line[2:].strip()
            continue
        stripped = line.strip()
        if SENDER_RE.match(stripped) and doc["sender"] is None and section is None:
            doc["sender"] = stripped
            continue
        if stripped.startswith("◇"):
            doc["gist"].append(stripped.lstrip("◇").strip())
            continue
        if re.match(r"^─{4,}", stripped) or "(본문 끝)" in stripped:
            body_ended = True
            continue
        m = FOOTNOTE_DEF_RE.match(stripped)
        if m and not line.startswith(" "):
            doc["footnote_defs"].append(_base_term(m.group(1)))
            continue
        if stripped.startswith("※"):
            if last_item is not None:
                last_item["notes"] += 1
            continue
        if re.match(r"^\[ .+ \]$", stripped):
            pending_caption = stripped.strip("[] ").strip()
            continue
        if stripped.startswith("|"):
            if not in_table:
                in_table = True
                is_appendix = body_ended or (section is not None and section["is_appendix"])
                doc["table_blocks"].append(
                    {"lines": 0, "is_appendix": is_appendix, "caption": pending_caption}
                )
                pending_caption = None
                if section is not None:
                    section["tables"] += 1
                else:
                    doc.setdefault("orphan_tables", 0)
                    doc["orphan_tables"] = doc.get("orphan_tables", 0) + 1
            doc["table_blocks"][-1]["lines"] += 1
            if section is not None:
                section["extra_width"] = section.get("extra_width", 0) + display_width(stripped)
            continue
        in_table = False
        if stripped:
            pending_caption = None
        m = re.match(r"^- (.+)$", line)
        if m:
            title = m.group(1).strip()
            section = {
                "title": title,
                "is_appendix": body_ended or bool(re.match(r"^붙임\s*\d", title)),
                "items": [],
                "tables": 0,
                "extra_width": 0,
            }
            doc["sections"].append(section)
            last_item = None
            continue
        m = re.match(r"^  - (.+)$", line)
        if m and section is not None:
            last_item = {"text": m.group(1).strip(), "children": [], "notes": 0}
            section["items"].append(last_item)
            continue
        m = re.match(r"^ {4,}- (.+)$", line)
        if m and last_item is not None:
            last_item["children"].append(m.group(1).strip())
            continue
    return doc


def lint(md, target=None):
    doc = parse(md)
    violations, warnings = [], []
    body = [s for s in doc["sections"] if not s["is_appendix"]]
    appendix = [s for s in doc["sections"] if s["is_appendix"]]

    def flag(bucket, rule, where, text, fix):
        bucket.append({"rule": rule, "where": where, "text": text, "fix": fix})

    # L7 — 제목·발신
    if not doc["title"]:
        flag(violations, "L7", "문서 머리", "(제목 없음)", "`# 제목` 헤딩 추가")
    if not doc["sender"]:
        flag(violations, "L7", "문서 머리", "(발신정보 없음)", "`< '26. M. D.(요일), 부서 >` 발신 줄 추가")

    all_marker_terms = set()
    for g in doc["gist"]:
        all_marker_terms.update(_base_term(t) for t in MARKER_RE.findall(g))

    body_items = 0
    for sec in body:
        # L4 — □ 표제 한 줄
        if display_width(sec["title"]) > SECTION_TITLE_WIDTH_MAX or _ends_verbal(sec["title"]):
            flag(violations, "L4", f"□ {sec['title'][:20]}…", sec["title"],
                 "표제를 짧은 명사구로, 설명은 ㅇ으로 내림")
        # L11 — □당 ㅇ ≤ 3
        if len(sec["items"]) > SECTION_ITEM_MAX:
            flag(violations, "L11", f"□ {sec['title']}", f"ㅇ {len(sec['items'])}개",
                 "핵심 3개로 통합하거나 붙임 이관")
        is_plan = "향후계획" in sec["title"].replace(" ", "") or "추진일정" in sec["title"].replace(" ", "")
        prev_connectors, run = None, 1
        for item in sec["items"]:
            body_items += 1
            texts = [item["text"]] + item["children"]
            for t in texts:
                # L1 — 명사형 종결
                if _ends_verbal(t):
                    flag(violations, "L1", f"□ {sec['title']}", t[-30:], "체언(명사형)으로 마감")
                # L5 — 가운뎃점 나열
                if ENUM_RE.search(t):
                    flag(warnings, "L5", f"□ {sec['title']}", t[:40], "나열은 가운뎃점(A·B·C)으로")
            # L2/L3 — 2줄 규칙 휴리스틱
            w = display_width(item["text"])
            if w < ITEM_WIDTH_MIN:
                flag(warnings, "L2", f"□ {sec['title']}", item["text"],
                     "주체·방법·근거·수치를 담아 2줄로 보강(앙상한 한 줄 의심)")
            elif w > ITEM_WIDTH_MAX:
                flag(warnings, "L3", f"□ {sec['title']}", item["text"][:40] + "…",
                     "2줄 초과 의심 — 세부는 `-`로 내림")
            # L6 — 괄호 리드
            if not LEAD_RE.match(item["text"]):
                flag(warnings, "L6", f"□ {sec['title']}", item["text"][:40], "`(소제목)` 리드 추가")
            # L13b — ㅇ당 각주 총량 (* ≤1 + ※ ≤1)
            stars = [t2 for t in texts for t2 in MARKER_RE.findall(t)]
            all_marker_terms.update(_base_term(t) for t in stars)
            if len(stars) > 1:
                flag(violations, "L13b", f"□ {sec['title']}", item["text"][:40],
                     f"ㅇ당 `*` 1개 초과({len(stars)}개) — 핵심 1개만 남기고 본문 흡수·※ 이관")
            if item["notes"] > 1:
                flag(violations, "L13b", f"□ {sec['title']}", item["text"][:40],
                     f"ㅇ당 `※` 1개 초과({item['notes']}개)")
            # L16 — 향후계획 시점
            if is_plan and not DATE_RE.search(" ".join(texts)):
                flag(violations, "L16", f"□ {sec['title']}", item["text"][:40],
                     "`'26. M월` 시점 병기(미확정은 `['26.__월]`+\"(안)\")")
            # L18 — 구문 단조 (연속 동일 연결)
            conns = {c for c in CONNECTORS if c in item["text"]}
            if prev_connectors is not None and conns & prev_connectors:
                run += 1
                if run == 3:
                    flag(warnings, "L18", f"□ {sec['title']}", item["text"][:40],
                         "같은 연결 패턴 연속 3항목 — 골격(단문·인과·대비) 순환")
            else:
                run = 1
            prev_connectors = conns

    # 붙임 ㅇ의 각주 마커도 정합 검사에 포함
    for sec in appendix:
        for item in sec["items"]:
            for t in [item["text"]] + item["children"]:
                all_marker_terms.update(_base_term(m) for m in MARKER_RE.findall(t))

    # L12 — 본문 분량 예산
    body_tables = sum(s["tables"] for s in body) + doc.get("orphan_tables", 0)
    if body_items > BODY_ITEM_MAX:
        flag(violations, "L12", "본문 전체", f"총 ㅇ {body_items}개",
             f"본문 ㅇ ≤ {BODY_ITEM_MAX} — 통합·붙임 이관")
    if body_tables > BODY_TABLE_MAX:
        flag(violations, "L12", "본문 전체", f"표 {body_tables}개",
             f"본문 표 ≤ {BODY_TABLE_MAX} — 상세 표는 붙임으로")

    # L23 — 본문 표 크기 (헤더·구분선 제외 데이터 행 ≤ 반 페이지 어림)
    for tb in doc["table_blocks"]:
        data_rows = max(tb["lines"] - 2, 0)
        if not tb["is_appendix"] and data_rows > BODY_TABLE_ROWS_MAX:
            flag(violations, "L23", f"표 [{tb['caption'] or '캡션 없음'}]",
                 f"데이터 {data_rows}행 (본문 상한 {BODY_TABLE_ROWS_MAX})",
                 "핵심 행만 선별 또는 통계 가공(집계·상위 N + '외 N건'), 전량은 붙임으로")

    # L13 — 각주 마커 ↔ 정의 정합
    defs = set(doc["footnote_defs"])
    for term in sorted(all_marker_terms - defs):
        flag(violations, "L13", "각주", f"{term}*", "하단에 `* 용어: 1줄 정의` 추가")
    # 고아 정의: 용어가 문서 본문·표 어디에도 등장하지 않는 정의만 반려
    #           (표 셀 용어는 마커 없이 하단 정의만 두는 관행 허용)
    non_def_text = "\n".join(
        line for line in md.splitlines() if not FOOTNOTE_DEF_RE.match(line.strip())
    )
    for term in sorted(defs - all_marker_terms):
        if term not in non_def_text:
            flag(violations, "L13", "각주", f"* {term}:",
                 "문서에 없는 용어의 고아 정의 — 마커 추가 또는 정의 삭제")

    # L19 — 붙임 요약 구조 / L15 — 붙임 분량
    for sec in appendix:
        if sec["tables"] and not sec["items"]:
            flag(violations, "L19", sec["title"], f"표 {sec['tables']}개·요약 ㅇ 0개",
                 "표 앞에 ㅇ 요약 설명(2줄 이내) 추가")
    if appendix:
        appendix_width = sum(
            s["extra_width"] + sum(display_width(i["text"]) for i in s["items"]) for s in appendix
        )
        if appendix_width < APPENDIX_WIDTH_MIN:
            flag(warnings, "L15", "붙임 전체", f"합산 분량 부족 의심(폭 {appendix_width})",
                 "상세 보강 또는 본문 흡수(붙임 최소 1페이지)")

    # L17 — 중복 문구 (단어 4-gram 4회 이상)
    words = []
    for sec in doc["sections"]:
        for item in sec["items"]:
            words.extend(re.findall(r"[가-힣A-Za-z0-9]+", item["text"]))
    grams = {}
    for i in range(len(words) - 3):
        g = " ".join(words[i:i + 4])
        grams[g] = grams.get(g, 0) + 1
    for g, n in grams.items():
        if n >= 4:
            flag(warnings, "L17", "본문+붙임", f'"{g}" {n}회', "중복 상한 3회 — 심화(수치·사례)로 교체")
            break

    # L24 — 법령 조항호목 한국식 표기 (표 셀 포함 전문 스캔)
    for lineno, line in enumerate(md.splitlines(), 1):
        for pat, what, fix in LEGAL_BAD_RES:
            m = pat.search(line)
            if m:
                ctx_start = max(m.start() - 15, 0)
                flag(violations, "L24", f"{lineno}행",
                     f"{what}: …{line[ctx_start:m.end() + 10]}…", fix)

    # L22 — BLUF
    has_bluf = bool(doc["gist"]) or any(
        ("보고요지" in s["title"].replace(" ", "")) or ("건의요지" in s["title"].replace(" ", ""))
        for s in body
    )
    if not has_bluf:
        is_exec = bool(target) and ("임원" in target or "기관장" in target)
        flag(violations if is_exec else warnings, "L22", "본문 선두", "(보고 요지 블록 없음)",
             "`□ 보고 요지` 선두 블록(또는 ◇ 요지) 추가")

    body_text = " ".join(i["text"] for s in body for i in s["items"])
    total_chars = max(len(body_text), 1)
    stats = {
        "body_sections": len(body),
        "body_items": body_items,
        "body_tables": body_tables,
        "appendix_sections": len(appendix),
        "items_per_section": {s["title"]: len(s["items"]) for s in body},
        "numeric_density_per_1000": round(len(re.findall(r"\d", body_text)) / total_chars * 1000, 1),
    }
    if violations:
        verdict = "반려"
    elif warnings:
        verdict = f"통과 (경고 {len(warnings)}건)"
    else:
        verdict = "통과"
    return {"verdict": verdict, "violations": violations, "warnings": warnings, "stats": stats}


def main():
    ap = argparse.ArgumentParser(description="KCA 개조식 MD 기계 린트")
    ap.add_argument("draft", help="검사할 개조식 MD 파일")
    ap.add_argument("--target", help="보고 대상(임원/기관장/경영진/부서장·실무) — L22 판정 수위")
    ap.add_argument("--context", help="00_context.md 경로(보고 대상 자동 추출)")
    ap.add_argument("--json", action="store_true", help="JSON 출력")
    args = ap.parse_args()

    target = args.target
    if not target and args.context:
        try:
            ctx = open(args.context, encoding="utf-8").read()
            m = re.search(r"보고\s*대상.*?(기관장|임원|경영진|부서장)", ctx)
            target = m.group(1) if m else None
        except OSError:
            pass

    md = open(args.draft, encoding="utf-8").read()
    result = lint(md, target=target)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"판정: {result['verdict']}")
        for kind, label in (("violations", "반려"), ("warnings", "확인 요망")):
            for f in result[kind]:
                print(f"  [{label}] {f['rule']} {f['where']} — {f['text']} → {f['fix']}")
        print(f"통계: {json.dumps(result['stats'], ensure_ascii=False)}")
    sys.exit(1 if result["violations"] else 0)


if __name__ == "__main__":
    main()
