#!/usr/bin/env python3
"""postprocess 결과 JSON의 기대 하한을 검사한다 — 침묵 실패 차단 (설계문서 §8-1).

postprocess_hwpx.py는 처리 대상이 0건이어도 exit 0을 낸다. 생성기가 어긋나면
룰이 조용히 무효화되고 사용자는 hwpx를 열기 전까지 모른다(실측: 타 생성기에서
title_box found:false·body_justify changed:0·line_fit fitted:0이 전부 무오류 통과).
여기서 md 실측 기대값과 대조해 어긋나면 변환을 중단시킨다.

hwpx 경로를 함께 주면 post.json이 표현하지 못하는 **기하 불변식**도 검사한다 — 이 둘은
정적 검증을 전부 통과하고 한글로 열어야만 드러나는 유형이라 실제 배포본에서 재발했다
('26.8.7 Reachy_Mini 건).

  · 제목 박스 앞 빈 문단 금지 — secPr 문단을 쪼개면 본문 15pt·줄간격 160% 빈 줄이
    제목표 위에 약 8.5mm 여백으로 렌더된다.
  · 열 폭 역전 금지 — 요구 표시폭이 큰 열이 더 좁으면 안 된다(옛 40% 상한 결함).

usage: assert_postprocess.py <post.json> <prepared.md> [result.hwpx]
exit 0 통과 / 1 기대 불일치 / 2 인자·파일 오류
"""
import sys, json, re, pathlib, zipfile
import xml.etree.ElementTree as ET

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

DAE, STAR, CHAM = "□", "＊", "※"
YO_CHARS = ("ㅇ", "○")
BANNER_RE = re.compile(r"^\|\s*(붙\s*임|붙임\s*\d+|참고\s*\d*)\s*\|")
YO_LEAD_RE = re.compile(r"^[ㅇ○]\s*\*\*\(")


def expectations(md):
    lines = [l.strip() for l in md.splitlines()]
    return {
        "dae": sum(l.startswith(DAE) for l in lines),
        "yo_lead": sum(bool(YO_LEAD_RE.match(l)) for l in lines),
        "banner": sum(bool(BANNER_RE.match(l)) for l in lines),
        "star": sum(l.startswith(STAR) for l in lines),
    }


def check(post, exp):
    fails = []

    def eq(path, got, want):
        if got != want:
            fails.append({"check": path, "got": got, "expected": want})

    def truthy(path, got):
        if not got:
            fails.append({"check": path, "got": got, "expected": "truthy"})

    truthy("title_box.found", post.get("title_box", {}).get("found"))
    if exp["star"]:   # ＊ 각주가 없으면 참고 charPr을 찾을 이유도 없다(단계가 스킵된다)
        truthy("star_footnote.ref_charpr_id", post.get("star_footnote", {}).get("ref_charpr_id"))
    eq("sender_size.runs_changed", post.get("sender_size", {}).get("runs_changed"), 1)
    eq("dae_bold.runs_changed", post.get("dae_bold", {}).get("runs_changed"), exp["dae"])
    eq("annex_banner.title_justified",
       post.get("annex_banner", {}).get("title_justified"), exp["banner"])
    eq("paren_small.lead_skipped", post.get("paren_small", {}).get("lead_skipped"), exp["yo_lead"])
    eq("star_footnote.stars_found", post.get("star_footnote", {}).get("stars_found"), exp["star"])
    if not post.get("body_justify", {}).get("changed", 0) > 0:
        fails.append({"check": "body_justify.changed", "got": post.get("body_justify", {}).get("changed"),
                      "expected": "> 0"})
    if post.get("paren_small", {}).get("cross_run_skipped", 0):
        fails.append({"check": "paren_small.cross_run_skipped",
                      "got": post["paren_small"]["cross_run_skipped"], "expected": 0})
    return fails


def wlen(s):
    return sum(2 if ord(c) > 0x1100 else 1 for c in s)


def check_geometry(path):
    """post.json이 표현하지 못하는 기하 불변식 — 렌더로만 드러나는 결함을 잡는다."""
    fails = []
    sec = ET.fromstring(zipfile.ZipFile(path).read("Contents/section0.xml"))
    paras = sec.findall(f"{HP}p")

    # ① 제목 박스는 secPr와 같은 첫 문단에 있어야 한다 (선행 빈 문단 = 제목표 상단 여백)
    if paras:
        first = paras[0]
        has_secpr = first.find(f".//{HP}secPr") is not None
        has_tbl = any(r.find(f"{HP}tbl") is not None for r in first.findall(f"{HP}run"))
        if has_secpr and not has_tbl:
            fails.append({"check": "title_box.no_leading_blank",
                          "got": "secPr 문단이 제목 박스와 분리됨",
                          "expected": "secPr와 제목 박스가 같은 첫 문단"})

    # ② 열 폭이 요구 표시폭과 역전되면 안 된다 + 셀 폭 합 == 표 sz (R036)
    for tbl in sec.iter(f"{HP}tbl"):
        trs = tbl.findall(f"{HP}tr")
        if not trs:
            continue
        widths = [int(tc.find(f"{HP}cellSz").get("width")) for tc in trs[0].findall(f"{HP}tc")]
        sz = int(tbl.find(f"{HP}sz").get("width"))
        if sum(widths) != sz:
            fails.append({"check": "table.cell_width_sum", "table": tbl.get("id"),
                          "got": sum(widths), "expected": sz})
        rows = [["".join(t.text or "" for t in tc.iter(f"{HP}t"))
                 for tc in tr.findall(f"{HP}tc")] for tr in trs]
        ncol = len(widths)
        if ncol < 2 or not any(any(c.strip() for c in r) for r in rows):
            continue
        demand = [max((wlen(r[j]) if j < len(r) else 0) for r in rows) for j in range(ncol)]
        wide, narrow = max(range(ncol), key=lambda j: demand[j]), min(range(ncol), key=lambda j: demand[j])
        if demand[wide] > demand[narrow] * 2 and widths[wide] < widths[narrow]:
            fails.append({"check": "table.column_width_inverted", "table": tbl.get("id"),
                          "got": f"요구 {demand[wide]}폭 열이 {widths[wide]}hu, "
                                 f"요구 {demand[narrow]}폭 열이 {widths[narrow]}hu",
                          "expected": "요구가 큰 열이 더 넓을 것"})
    return fails


def main(argv):
    if len(argv) < 2:
        print("usage: assert_postprocess.py <post.json> <prepared.md> [result.hwpx]",
              file=sys.stderr)
        return 2
    try:
        post = json.loads(pathlib.Path(argv[0]).read_text(encoding="utf-8"))
        md = pathlib.Path(argv[1]).read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    exp = expectations(md)
    fails = check(post, exp)
    if len(argv) >= 3:
        try:
            fails += check_geometry(pathlib.Path(argv[2]))
        except (OSError, zipfile.BadZipFile, ET.ParseError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    print(json.dumps({"expected": exp, "failures": fails}, ensure_ascii=False, indent=1))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
