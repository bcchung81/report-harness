#!/usr/bin/env python3
"""기관 양식(hwp·hwpx)의 표·도식 틀을 구조로 뽑아 유형별로 묶는다. stdlib-only(+ kordoc CLI).

배경('26.9.24 사용자 요청): 경영관리 프레임워크 12개 문서('24.12.3, 약 225쪽·표 약 1,130개)는
내용이 빈 작성 양식이다 — 경영실적 지표별로 기관이 정해 둔 표·도식 틀. 이것을 table-pool.md·
diagram-pool.md·render_diagram의 재료로 쓰려면 먼저 "어떤 틀이 몇 번, 어느 지표에서 나오는가"를
결정론으로 세야 한다. 원본 조각을 그대로 이식하지 않고 **구조(행·열·병합·머리글·라벨 칸)**만
뽑는다 — 양식 문구가 아니라 틀의 문법이 재사용 대상이다.

  · 파싱은 kordoc CLI(`npx kordoc --format json`) — hwp·hwpx를 같은 표 구조(셀 글자·colSpan·
    rowSpan·쪽 번호)로 준다. 이 스크립트는 그 JSON만 읽는다(`--json-dir`로 미리 만든 JSON도 받는다).
  · 서명(signature) = 정규화한 머리글 + 병합 모양. 연도('23·'24)·숫자는 자리표시로 바꿔 지표가
    달라도 같은 틀이면 한 유형으로 묶인다.
  · 특징 태그: label-grid(왼쪽 라벨 칸 + 내용), header-2level(연도·구분 2단 머리행),
    asis-tobe(기존·개선), yearly(연도 열), pdca(P·D·C·A 칸), merged-rows(세로 병합 구분 열),
    blank-template(머리글 외 빈 칸), banner(1~2칸 제목 띠).

    extract_form_patterns.py <원본 폴더> [-o 결과.json] [--json-dir 폴더] [--min-count N]
"""
import sys
import re
import json
import argparse
import pathlib
import subprocess
import collections

YEAR = re.compile(r"[‘'’]?\d{2}년?|20\d{2}년?")
NUM = re.compile(r"\d+")
SPACE = re.compile(r"\s+")
ASIS = re.compile(r"(기존|개선|As-?is|To-?be|현행|변경)", re.I)
PDCA = {"P", "D", "C", "A"}


def kordoc_json(src, out_dir):
    """원본 1개 → kordoc JSON(이미 있으면 재사용)."""
    out = pathlib.Path(out_dir) / (src.stem + ".json")
    if not out.is_file():
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["npx", "-y", "kordoc", str(src), "--format", "json", "--no-images", "-o", str(out)],
                       check=True, capture_output=True, text=True, timeout=300)
    return json.loads(out.read_text(encoding="utf-8"))


def norm(text):
    t = SPACE.sub("", text or "")
    t = YEAR.sub("'YY", t)
    return NUM.sub("0", t)


IMG = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def trim(cells):
    """장식용 빈 행·열(여백 칸·색 띠)을 걷어낸다 — 이 양식은 라벨 앞뒤에 빈 칸을 두어 틀을 그린다.
    셀 속 그림(화살표·아이콘)은 '[그림]'으로 바꾼다. 병합 정보는 남은 칸에 그대로 둔다."""
    grid = [[dict(c, text=IMG.sub("[그림]", (c.get("text") or "")).strip()) for c in r] for r in cells]
    grid = [r for r in grid if any(c["text"] for c in r)]
    if not grid:
        return []
    width = max(len(r) for r in grid)
    keep = [j for j in range(width) if any(j < len(r) and r[j]["text"] for r in grid)]
    return [[r[j] for j in keep if j < len(r)] for r in grid]


def table_features(tbl):
    cells = trim(tbl.get("cells") or [])
    rows, cols = len(cells), max((len(r) for r in cells), default=0)
    texts = [[c["text"] for c in r] for r in cells]
    head = texts[0] if texts else []
    merges = [(i, j, c.get("rowSpan", 1), c.get("colSpan", 1))
              for i, r in enumerate(cells) for j, c in enumerate(r)
              if c.get("rowSpan", 1) > 1 or c.get("colSpan", 1) > 1]
    body = texts[1:]
    tags = set()
    if rows <= 1 and cols <= 3:
        tags.add("banner")
    # 왼쪽 라벨 칸: 1열이 글자가 있고 나머지가 대부분 빈 칸인 행이 과반
    lab = [r for r in texts if r and r[0] and sum(1 for x in r[1:] if x) <= max(0, len(r) - 2)]
    if cols >= 2 and len(lab) >= max(2, len(texts) * 0.6):
        tags.add("label-grid")
    if any(c.get("colSpan", 1) > 1 for c in (cells[0] if cells else [])) and rows >= 2 and any(texts[1]):
        tags.add("header-2level")
    if any(ASIS.search(x) for r in texts[:2] for x in r):
        tags.add("asis-tobe")
    if any(YEAR.fullmatch(SPACE.sub("", x) or "-") for r in texts[:2] for x in r):
        tags.add("yearly")
    flat = {SPACE.sub("", x) for r in texts for x in r}
    if PDCA <= flat:
        tags.add("pdca")
    if any(rs > 1 and j == 0 for i, j, rs, cs in merges):
        tags.add("merged-rows")
    if body and not any(x for r in body for x in r):
        tags.add("blank-template")
    head_sig = tuple(norm(x) for x in head)
    shape = (rows if rows <= 3 else "n", cols, tuple(sorted((str(i) if i < 2 else "b", j, rs, cs) for i, j, rs, cs in merges
                                                            if i < 2 or j == 0)))
    return {"rows": rows, "cols": cols, "head": head, "sub_head": texts[1] if len(texts) > 1 else [],
            "merges": len(merges), "tags": sorted(tags), "sig": json.dumps([head_sig, shape], ensure_ascii=False)}


def analyze(src_dir, json_dir, min_count=1):
    src_dir = pathlib.Path(src_dir)
    files = sorted(p for p in src_dir.iterdir() if p.suffix.lower() in (".hwp", ".hwpx"))
    clusters = collections.OrderedDict()
    per_doc = {}
    for f in files:
        d = kordoc_json(f, json_dir)
        blocks = d.get("blocks") or []
        n_tbl = n_img = 0
        for b in blocks:
            if b.get("type") == "image":
                n_img += 1
            if b.get("type") != "table":
                continue
            n_tbl += 1
            feat = table_features(b.get("table") or {})
            if not feat["rows"]:
                continue                          # 전부 빈 칸 — 여백·구분선용 표
            c = clusters.setdefault(feat["sig"], {"count": 0, "docs": collections.Counter(), "example": None,
                                                  "tags": feat["tags"], "rows": feat["rows"], "cols": feat["cols"]})
            c["count"] += 1
            c["docs"][f.stem.split("_")[-1]] += 1
            if c["example"] is None:
                c["example"] = {"doc": f.name, "page": b.get("pageNumber"), "head": feat["head"],
                                "sub_head": feat["sub_head"], "merges": feat["merges"]}
        per_doc[f.name] = {"pages": d.get("pageCount"), "tables": n_tbl, "images": n_img}
    out = []
    for sig, c in clusters.items():
        if c["count"] < min_count:
            continue
        out.append({"signature": sig, "count": c["count"], "n_docs": len(c["docs"]), "docs": dict(c["docs"]),
                    "tags": c["tags"], "rows": c["rows"], "cols": c["cols"], "example": c["example"]})
    out.sort(key=lambda x: (-x["n_docs"], -x["count"]))
    tag_count = collections.Counter(t for x in out for t in x["tags"] for _ in range(x["count"]))
    return {"documents": per_doc, "tables": sum(v["tables"] for v in per_doc.values()),
            "clusters": len(out), "tag_count": dict(tag_count), "patterns": out}


def main(argv=None):
    ap = argparse.ArgumentParser(description="기관 양식 표·도식 틀 구조 추출·유형 묶음")
    ap.add_argument("src", help="원본 hwp·hwpx 폴더")
    ap.add_argument("-o", "--out", help="결과 JSON(미지정 시 표준출력)")
    ap.add_argument("--json-dir", help="kordoc JSON 보관 폴더(기본: 결과 옆 _kordoc/)")
    ap.add_argument("--min-count", type=int, default=1, help="이 횟수 미만 유형은 빼고 보고")
    a = ap.parse_args(argv)
    json_dir = a.json_dir or (pathlib.Path(a.out).parent / "_kordoc" if a.out else pathlib.Path("_kordoc"))
    r = analyze(a.src, json_dir, a.min_count)
    text = json.dumps(r, ensure_ascii=False, indent=1)
    if a.out:
        pathlib.Path(a.out).write_text(text, encoding="utf-8")
        print(json.dumps({"tables": r["tables"], "clusters": r["clusters"], "tag_count": r["tag_count"]},
                         ensure_ascii=False))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(2)
