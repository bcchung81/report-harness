#!/usr/bin/env python3
"""prep 정규화본 → kordoc `generate_document` 입력 마크다운 (R087). stdlib-only.

배경('26.9.10 실측): 이 변환은 종전에 **모델이 손으로** 하고 그 결과를 `43_convert_input.md`로
저장했다. 그런데 인도 10건의 `40_prepared → 43_convert_input`을 30줄짜리 규칙으로 재현해 보니
9건이 100%·1건이 99.8% 일치했다 — 결정론 변환인데 스크립트가 없어 모델 편차에 맡겨져 있었고,
그래서 결과를 파일로 남겨야 했다. 남은 0.2%는 도식 마커 치환뿐이고 그것만 Pool 조회가 필요하다.

변환 내용(개조식 → kordoc이 기대하는 마크다운 위계, hwpx-recipe §2):
  · 첫 줄 제목 → `# 제목` (평문 첫 줄은 제목으로 인식되지 않아 제목 박스·20pt가 안 붙는다, R010)
  · 발신 줄 `< '26. 9. 6.(일), … >` → `<right>…</right>` (미래핑 시 좌측 정렬로 떨어진다, R012)
  · `□ ` → `- ` / `ㅇ ` → `  - ` / `- ` → `    - ` (리터럴 기호를 그대로 두면 하위 대시가
    상위 부호로 평탄화된다)
  · `도해: {슬러그}` → `![{캡션}]({파일})` — `--figure`로 받은 매핑만 치환하고, 매핑 없는
    마커는 **그대로 두고 보고**한다(조용히 지우면 도식이 사라진 채 인도된다)

표·※·＊ 줄은 손대지 않는다.
"""
import re
import sys
import json
import argparse
import pathlib

SENDING = re.compile(r"^<\s*'?\d.*>$")          # 발신 줄 `< '26. 9. 6.(일), 본부 팀 >`
FIGURE = re.compile(r"^도해:\s*(?P<slug>\S+)\s*$")
TABLE = re.compile(r"^\s*\|")
DEPTH = (("□ ", "- "), ("ㅇ ", "  - "), ("○ ", "  - "))
DASH = re.compile(r"^-\s+")


def convert(text, figures=None):
    """(변환본, 리포트) — figures는 {슬러그: (파일명, 캡션)}."""
    figures = figures or {}
    out, used, missing = [], [], []
    title_done = False
    for raw in text.splitlines():
        line = raw.rstrip()
        body = line.strip()

        if not title_done and body:
            out.append("# " + body)
            title_done = True
            continue
        if TABLE.match(line):            # 표는 그대로 (GFM)
            out.append(line)
            continue
        if SENDING.match(body):
            out.append(f"<right>{body}</right>")
            continue
        m = FIGURE.match(body)
        if m:
            slug = m.group("slug")
            if slug in figures:
                name, caption = figures[slug]
                out.append(f"![{caption}]({name})")
                used.append(slug)
            else:
                out.append(line)          # 지우지 않는다 — 사라진 도식은 검출되지 않는다
                missing.append(slug)
            continue
        for mark, repl in DEPTH:
            if body.startswith(mark):
                out.append(repl + body[len(mark):])
                break
        else:
            if DASH.match(body) and not set(body) <= set("- "):
                out.append("    - " + DASH.sub("", body))
            else:
                out.append(line)
    return "\n".join(out) + "\n", {"figures_substituted": used, "figures_missing": missing}


def parse_figure(spec):
    """`슬러그=파일명|캡션` 하나를 (슬러그, (파일명, 캡션))으로."""
    if "=" not in spec:
        raise ValueError(f"--figure 형식은 슬러그=파일명|캡션 이다: {spec}")
    slug, rest = spec.split("=", 1)
    name, _, caption = rest.partition("|")
    return slug.strip(), (name.strip(), (caption.strip() or slug.strip()))


def main(argv=None):
    ap = argparse.ArgumentParser(description="prep 정규화본 → kordoc 입력 마크다운")
    ap.add_argument("src", help="40_prepared.md 또는 prep 정규화본 경로")
    ap.add_argument("-o", "--out", help="출력 경로(미지정 시 표준출력)")
    ap.add_argument("--figure", action="append", default=[],
                    help="도식 마커 치환 `슬러그=파일명|캡션` (반복 지정)")
    ap.add_argument("--report", action="store_true", help="치환 결과를 JSON으로 함께 보고")
    args = ap.parse_args(argv)

    figures = dict(parse_figure(s) for s in args.figure)
    text = pathlib.Path(args.src).read_text(encoding="utf-8")
    converted, report = convert(text, figures)
    if args.out:
        pathlib.Path(args.out).write_text(converted, encoding="utf-8")
    else:
        sys.stdout.write(converted)
    if args.report:
        print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
    # 매핑 없는 도식 마커가 남으면 exit 1 — 마커째 변환되면 본문에 '도해: …'가 찍힌다
    return 1 if report["figures_missing"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
