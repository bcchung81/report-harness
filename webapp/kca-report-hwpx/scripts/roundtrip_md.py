#!/usr/bin/env python3
"""hwpx → 마크다운 되읽기 (kordoc parse_document 대체).

`validate_hwpx.py compare`의 입력을 만든다. compare는 변환기가 마크다운 기호를
문자 그대로 박아버리는 사고의 최종 검출선(markdown-leftover)이라, 되읽기가 없으면
그 방어선이 통째로 빠진다 — 그래서 python-hwpx가 없어도 동작하는 stdlib 폴백을 둔다.

  1순위: python-hwpx (설치돼 있으면 사용)
  폴백 : section0.xml 직접 파싱 (stdlib)

두 경로 모두 compare의 집계 대상(□ 절·ㅇ 요지·대시 상세·＊ 각주·표 수·최대 열 수·
수치)을 같은 방식으로 재현한다.

usage: roundtrip_md.py <file.hwpx> -o <out.md> [--stdlib]
"""
import sys, argparse, pathlib, warnings, zipfile, re
import xml.etree.ElementTree as ET

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
SECTION_RE = re.compile(r"^Contents/section\d+\.xml$")


def _runs_text(p):
    """문단 직속 run들의 hp:t 텍스트 — 표 셀 내부는 별도 문단이라 섞이지 않는다."""
    out = []
    for run in p.findall(f"{HP}run"):
        for t in run.findall(f"{HP}t"):
            out.append("".join(t.itertext()))
    return "".join(out)


def _cell_text(tc):
    parts = []
    for p in tc.iter(f"{HP}p"):
        s = _runs_text(p).strip()
        if s:
            parts.append(s)
    return " ".join(parts)


def _emit_table(tbl, out):
    # R034로 표 안에 내장된 캡션은 표 위 별도 줄로 되돌린다(원본 md와 같은 형태)
    cap = tbl.find(f"{HP}caption")
    if cap is not None:
        text = " ".join(_runs_text(p).strip() for p in cap.iter(f"{HP}p")).strip()
        if text:
            out.extend([text, ""])
    rows = []
    for tr in tbl.findall(f"{HP}tr"):
        rows.append([_cell_text(tc) for tc in tr.findall(f"{HP}tc")])
    if not rows:
        return
    ncol = max(len(r) for r in rows)
    for i, row in enumerate(rows):
        row = row + [""] * (ncol - len(row))
        out.append("| " + " | ".join(row) + " |")
        if i == 0:
            out.append("| " + " | ".join(["---"] * ncol) + " |")
    out.append("")


def _emit(el, out):
    """문서 순서로 훑는다. 표 셀 문단은 _emit_table이 처리하므로 여기서 내려가지 않는다."""
    for child in el:
        if child.tag == f"{HP}p":
            text = _runs_text(child).strip()
            if text:
                out.extend([text, ""])
            for run in child.findall(f"{HP}run"):
                for node in run:
                    if node.tag == f"{HP}tbl":
                        _emit_table(node, out)
                    elif node.tag != f"{HP}t":
                        _emit(node, out)      # hp:ctrl → hp:header → subList → p
        elif child.tag != f"{HP}tbl":
            _emit(child, out)


def read_stdlib(path):
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if SECTION_RE.match(n))
        if not names:
            raise ValueError("Contents/sectionN.xml 없음")
        out = []
        for n in names:
            _emit(ET.fromstring(z.read(n)), out)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def read_pyhwpx(path):
    warnings.filterwarnings("ignore")
    from hwpx.document import HwpxDocument
    doc = HwpxDocument.open(path)
    if hasattr(doc, "text") and hasattr(doc.text, "markdown"):
        return doc.text.markdown()
    return doc.export_markdown()


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--stdlib", action="store_true",
                    help="python-hwpx가 있어도 stdlib 폴백을 쓴다(대조 검증용)")
    a = ap.parse_args(argv)
    if a.stdlib:
        md, backend = read_stdlib(a.src), "stdlib"
    else:
        try:
            md, backend = read_pyhwpx(a.src), "python-hwpx"
        except ImportError:
            md, backend = read_stdlib(a.src), "stdlib(fallback)"
    pathlib.Path(a.output).write_text(md, encoding="utf-8")
    print(f"OK {a.output} (backend={backend})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
