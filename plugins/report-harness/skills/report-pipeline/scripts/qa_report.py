#!/usr/bin/env python3
"""변환 QA 기록 생성 — 스크립트 출력에서 40_qa.md를 찍는다 (R087). stdlib-only.

배경('26.9.10 실측): `40_qa.md`는 모델이 손으로 쓰고 있었다. 결과가 건마다 1.7~12KB로
들쭉날쭉했고 3기관 건은 **0바이트**(아예 비어 있음)였는데 아무도 눈치채지 못했다. 검증
기록이 손글씨면 빠뜨려도 드러나지 않는다 — 파이프라인이 이미 JSON으로 뱉는 것을 모아 찍는다.

입력은 각 단계가 남긴 JSON이다(경로 또는 `-` 로 표준입력):
    qa_report.py --postprocess post.json --structural st.json --compare cmp.json \\
                 --numbers num.json --title "보고서 제목" --hwpx final/r01_….hwpx -o 40_qa.md
없는 단계는 생략하면 '실행 안 함'으로 기록된다 — 빠진 것이 기록에 드러나야 한다.

**인도 판정**(exit 코드): 후처리·구조 검증·내용 대조 결과가 모두 있고, 구조 오류·내용 불일치·근거 없는 수치가
없으며, 인도본 hwpx가 실제로 있을 때만 exit 0이다. 종전에는 구조 오류만 exit 1이라 내용 대조 실패나 단계 누락이
'성공'으로 읽혔다(astra 검토 A14). Codex에는 안전망 훅이 없으므로 이 판정이 실행기 공통 인도 게이트다.
줄 넘침(line_fit overflow)은 승인본을 임의로 줄이지 않는 원칙(SKILL ④-3)에 따라 막지 않고 기록·고지만 한다.
"""
import sys
import json
import argparse
import pathlib
import datetime

STAGES = (
    ("numbers", "수치 근거 대조", "validate_hwpx.py numbers"),
    ("postprocess", "양식 정합 후처리", "postprocess_hwpx.py --all"),
    ("structural", "구조 검증", "validate_hwpx.py structural"),
    ("compare", "내용 대조", "validate_hwpx.py compare"),
)


def _load(path):
    if not path:
        return None
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def _verdict(key, data):
    """단계별 한 줄 판정 — 숫자를 그대로 옮기고 해석은 붙이지 않는다."""
    if data is None:
        return "실행 안 함"
    if key == "numbers":
        n = len(data.get("issues", []))
        return "근거 없는 수치 없음" if not n else f"issues {n}건 — 출처 확인 필요"
    if key == "structural":
        errs = data.get("errors", [])
        return "errors: []" if not errs else f"**errors {len(errs)}건** — {errs[:2]}"
    if key == "compare":
        iss = data.get("issues", [])
        if not iss:
            return "불일치 없음"
        return " · ".join(f"{i.get('rule')}({i.get('count', len(i.get('values', [])) or 1)})"
                          for i in iss[:4])
    # postprocess — 실제로 **바꾼** 규칙만 센다. height·title_pt처럼 설정값을 되보고하는
    # 키까지 세면 무동작인 단계도 '적용'으로 잡혀 기록이 부풀려진다.
    applied = [k for k, v in data.items() if isinstance(v, dict) and _changed(v)]
    return (f"적용 {len(applied)}종: {', '.join(applied)}" if applied else "변경 없음")


# 값이 '몇 건을 바꿨나'를 뜻하는 키. 나머지(height·min_ratio·est_pages 등)는 설정·계측치다.
COUNT_KEYS = ("changed", "count", "found", "inserted", "modified", "fitted", "replaced",
              "restored", "removed", "added", "embedded", "boxed", "prefixed", "flattened",
              "highlights", "spans", "banners", "stars", "fills", "zeroed", "justified",
              "superscripted", "injected", "attrs_fixed", "tables_fitted", "paragraphs")


def _changed(stage):
    return {k: v for k, v in stage.items()
            if isinstance(v, int) and v > 0 and any(t in k for t in COUNT_KEYS)}


def render(title, hwpx, results, revision=None, now=None):
    now = now or datetime.datetime.now()
    day = now.strftime("'%y.%m.%d").replace(".0", ".")
    lines = [f"# 40_qa — hwpx 변환 QA ({day})", ""]
    lines.append(f"대상: `{hwpx}`" if hwpx else "대상: (미지정)")
    if title:
        lines.append(f"제목: {title}")
    if revision:
        lines.append(f"판본: {revision}")
    lines += ["", "## 1. 파이프라인 실행 결과", "",
              "| 단계 | 스크립트·도구 | 결과 |", "|---|---|---|"]
    for key, label, tool in STAGES:
        lines.append(f"| {label} | `{tool}` | {_verdict(key, results.get(key))} |")

    post = results.get("postprocess")
    if post:
        lines += ["", "## 2. 후처리 적용 내역", "", "| 규칙 | 값 |", "|---|---|"]
        for k, v in post.items():
            if isinstance(v, dict):
                hits = _changed(v)
                if hits:
                    lines.append(f"| `{k}` | {json.dumps(hits, ensure_ascii=False)} |")

    cmp_ = results.get("compare")
    if cmp_ and cmp_.get("issues"):
        lines += ["", "## 3. 내용 대조 미해결", "",
                  "> 아래 항목은 사람이 판정한다 — 표기 정규화·되읽기 아티팩트는 손실이 아니다.", ""]
        for i in cmp_["issues"]:
            lines.append(f"- `{i.get('rule')}` — {json.dumps({k: v for k, v in i.items() if k != 'rule'}, ensure_ascii=False)[:300]}")

    missing = [label for key, label, _ in STAGES if results.get(key) is None]
    if missing:
        lines += ["", "## 4. 실행하지 않은 단계", "",
                  "> 기록에 남겨 둔다 — 빠뜨린 검증이 조용히 사라지지 않게 한다.", ""]
        lines += [f"- {m}" for m in missing]

    over = ((post or {}).get("line_fit") or {}).get("overflow_detail") or []
    layout = (post or {}).get("layout") or {}
    if over or layout:
        lines += ["", "## 5. 인도 때 알릴 조판 사항", ""]
        if layout:
            lines.append(f"- 예상 쪽수: {layout.get('pages_by_part')} (추정 {layout.get('est_pt')}pt)")
        for o in over:
            lines.append(f"- 2줄 넘침(하한까지 조임): \"{o.get('text', '')}…\" — {o.get('lines')}줄 추정")

    ok, reasons = deliverable(results, hwpx)
    lines += ["", "## 인도 판정", "", "인도 가능" if ok else "**인도 보류** — " + " · ".join(reasons)]
    return "\n".join(lines) + "\n"


REQUIRED = ("postprocess", "structural", "compare")


def deliverable(results, hwpx):
    """인도 가능 여부와 보류 사유 — 필수 단계 결과 존재, 구조 오류·내용 불일치·근거 없는 수치 0, 인도본 존재."""
    reasons = [f"{label} 결과 없음" for key, label, _ in STAGES if key in REQUIRED and results.get(key) is None]
    if (results.get("structural") or {}).get("errors"):
        reasons.append("구조 오류")
    if (results.get("compare") or {}).get("issues"):
        reasons.append("내용 대조 불일치")
    if (results.get("numbers") or {}).get("issues"):
        reasons.append("근거 없는 수치")
    if not hwpx:
        reasons.append("인도본 경로 미지정")
    elif not pathlib.Path(hwpx).is_file():
        reasons.append("인도본 파일 없음")
    return not reasons, reasons


def main(argv=None):
    ap = argparse.ArgumentParser(description="변환 QA 기록 생성")
    for key, _, _ in STAGES:
        ap.add_argument(f"--{key}", help=f"{key} 단계 JSON 경로('-'는 표준입력)")
    ap.add_argument("--title")
    ap.add_argument("--hwpx")
    ap.add_argument("--revision")
    ap.add_argument("-o", "--out", help="출력 경로(미지정 시 표준출력)")
    args = ap.parse_args(argv)

    results = {key: _load(getattr(args, key)) for key, _, _ in STAGES}
    text = render(args.title, args.hwpx, results, args.revision)
    if args.out:
        pathlib.Path(args.out).write_text(text, encoding="utf-8")
        print(args.out)
    else:
        sys.stdout.write(text)
    ok, reasons = deliverable(results, args.hwpx)
    if not ok:
        print("인도 보류: " + " · ".join(reasons), file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
