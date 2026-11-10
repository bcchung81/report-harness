#!/usr/bin/env python3
"""research 그림 후보 목록 — 외부 자료의 도식을 본문에 쓸지(차용), 우리 양식으로 다시 그릴지(재작도)
판단하는 재료. stdlib-only.

배경('26.9.24 사용자 요청): research에는 외부 자료에서 뽑은 도식 그림(가이드라인 그림 13·14·17 등)이
쌓이지만 어떤 것이 인쇄에 쓸 만한지, 어디서 왔는지 한눈에 볼 방법이 없었다. 원본 그대로 넣으면
색·글꼴·캡션('그림 13')이 우리 양식과 달라 튀고, 흐린 사본(96dpi)은 인쇄에서 뭉개진다.

그림마다 출처(`_manifest.jsonl`의 title·source_url), 픽셀, 본문 폭 기준 표시 크기·유효 dpi(R088 계산
그대로), 판정과 권고를 낸다. 파일을 만들지 않고 표준출력(JSON)만 쓴다 — research 폴더의 산출 계약은
report-research가 책임진다.

    list_research_figures.py <work_dir> [--research-dir 폴더]

권고는 기계 판정(해상도)만 한다. 차용·재작도·표 재구성 중 무엇으로 쓸지는 도식의 성격을 보고 사람(LLM)이
정한다 — 기준은 references/diagram-pool.md '외부 도식 활용'.
"""
import sys
import json
import argparse
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from check_image_size import judge, MAX_W_MM                         # noqa: E402  (R088 판정 단독 출처)
from postprocess_hwpx import FIGURE_MAX_H_MM                         # noqa: E402

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}
SOURCE_EXT = {".pdf", ".hwp", ".hwpx", ".pptx", ".docx"}


def manifest(research):
    out = {}
    p = research / "_manifest.jsonl"
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            out.setdefault(e.get("file", ""), e)
    return out


def advice(j):
    if not j["sharp"]:
        return ("해상도 부족 — 우리 양식으로 재작도(도식 명세·표)하거나, 원문 PDF에서 고해상도로 다시 뽑는다"
                f"(표시 {j['mm'][0]}mm에서 {j['effective_dpi']}dpi, 기준 150dpi)")
    return "인쇄 가능 — 차용하거나, 양식 통일이 필요하면 재작도"


def collect(work_dir, research=None):
    research = pathlib.Path(research) if research else pathlib.Path(work_dir) / "research"
    man = manifest(research)
    figs, sources = [], []
    for p in sorted(research.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(research).as_posix()
        meta = man.get(p.name) or man.get(rel) or {}
        if p.suffix.lower() in SOURCE_EXT:
            sources.append({"file": rel, "title": meta.get("title")})
            continue
        if p.suffix.lower() not in IMAGE_EXT:
            continue
        try:
            j = judge(p.read_bytes(), MAX_W_MM, FIGURE_MAX_H_MM)
        except (OSError, ValueError, KeyError) as e:
            figs.append({"file": rel, "error": str(e)})
            continue
        figs.append({"file": rel, "spec_src": f"research/{rel}", "title": meta.get("title"),
                     "source_url": meta.get("source_url"), "px": j["px"], "mm": j["mm"],
                     "effective_dpi": j["effective_dpi"], "sharp": j["sharp"], "advice": advice(j)})
    return {"figures": figs, "sources": sources,
            "sharp": sum(1 for f in figs if f.get("sharp")), "blurry": sum(1 for f in figs if f.get("sharp") is False)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="research 그림 후보 목록(출처·해상도·권고)")
    ap.add_argument("work_dir")
    ap.add_argument("--research-dir", help="research 폴더(기본: {work_dir}/research)")
    a = ap.parse_args(argv)
    r = collect(a.work_dir, a.research_dir)
    print(json.dumps(r, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
