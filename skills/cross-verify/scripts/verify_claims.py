#!/usr/bin/env python3
"""패널 주장의 수치 근거를 원문과 대조한다 (교차검증 3단계). stdlib-only.

배경: '26.8.27 요약본 교차검증에서 패널 하나가 원문에 없는 수치 4건을 만들어냈다
(14.2배·N=30·3,500h, 그리고 '#4가 분모 2,000h를 독식' — 2,000h는 원문에 있으나 #4와
무관하고 실제 독식 과제는 #5였다). 범용 다중모델 도구는 패널 답변을 그대로 통과시키므로
이 대조가 없으면 지어낸 근거가 보고서로 넘어간다.

두 가지를 본다:
  · 수치-미검출 — 패널이 쓴 수치가 원문 어디에도 없다
  · 귀속-불일치 — 수치는 원문에 있으나 패널이 붙인 과제 앵커(#N) 근처에 없다

판단이 필요한 것(단위 없는 과장·인과 주장·해석)은 잡지 않는다 — SKILL.md의 4단계가
사람·모델 판단으로 처리한다.

사용:
  verify_claims.py <원문.md> [원문2.md ...] --panel 이름=경로 [--panel ...]
종료: 0 = 미검증 주장 없음 / 1 = 미검증 주장 있음 / 2 = 인자·파일 오류
"""
import sys
import re
import json
import argparse
import pathlib

# 수치 토큰: 3자리 이상이거나, 콤마·소수점이 있거나, 단위가 붙은 것만 본다.
# 단위 없는 한두 자리 정수(표 열 번호·건수 1~2 등)까지 잡으면 오탐이 실제 검출을 덮는다.
UNIT = r"(?:h|시간|분|초|건|%|배|명|원|쪽|개|종|회|점|억|만원)"
# 경계는 ASCII로만 막는다 — 파이썬 `\w`는 한글도 포함해서, `총3,500h`(앞) ·
# `3,500회의`(뒤)처럼 한글에 붙은 수치가 통째로 추출을 빠져나갔다('26.9.10 실측).
# 지어낸 수치가 아예 주장 목록에 오르지 않으므로 검사가 조용히 비는 구멍이었다.
NUM = re.compile(rf"(?<![0-9A-Za-z_#.])(\d[\d,]*(?:\.\d+)?)\s*({UNIT})?(?![0-9A-Za-z_])")
ANCHOR = re.compile(r"#(\d{1,2})\b")
YEAR = re.compile(r"^(?:19|20)\d\d$")
SENTENCE = re.compile(r"(?<=[.!?。])\s+")
DEFAULT_WINDOW = 400


def normalize(text):
    """콤마·공백 차이로 같은 수치를 다른 값으로 읽지 않게 한다."""
    return text.replace(",", "").replace(" ", "")


def number_tokens(text):
    """텍스트에 **실재하는** 수치 토큰 집합(정규화).

    근거 대조를 부분문자열 포함으로 하면 안 된다 — 원문의 `3,500h`가 정규화되어
    `3500`이 되고, 패널이 지어낸 `500h`의 `500`이 그 안에 들어 있어 '근거 있음'으로
    통과한다('26.9.10 실측. `2,000h`가 `200`·`000`을 통과시키는 것도 같은 구멍).
    이 도구의 유일한 탐지 수단이라 여기가 새면 검사 전체가 무의미해진다."""
    return {normalize(m.group(1)) for m in NUM.finditer(text)}


def is_significant(raw, unit):
    """대조할 값어치가 있는 수치인가.

    연도 제외는 단위·자릿점이 없을 때만 적용한다 — '2,000h'를 연도로 걸러 목표 총량
    주장이 통째로 검사에서 빠지는 사고가 있었다('26.8.27 최초 구현)."""
    digits = raw.replace(",", "")
    if not unit and "," not in raw and YEAR.match(digits):
        return False
    if unit or "," in raw or "." in raw:
        return True
    return len(digits) >= 3


def units(line):
    """귀속 판정의 맥락 단위로 끊는다.

    표 행(`|` 포함)은 통째로 둔다 — 셀 하나가 곧 한 과제의 서술이다. 서술문은 문장으로
    쪼갠다: 여러 문장이 한 문단에 붙어 있으면 앞 문장의 과제 번호가 뒤 문장의 무관한
    수치에 달라붙어 오탐이 난다(패널이 '#2·#3·#5 불승인' 다음 문장에서 전사 목표
    1,000h를 언급한 사례)."""
    if "|" in line:
        return [line]
    return [s for s in SENTENCE.split(line) if s.strip()]


def extract_claims(text):
    """패널 출력에서 (수치, 단위, 앵커, 줄번호, 줄내용)을 뽑는다."""
    claims = []
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        for line in units(raw_line):
            anchors = [(m.start(), m.group(1)) for m in ANCHOR.finditer(line)]
            for m in NUM.finditer(line):
                raw, unit = m.group(1), m.group(2)
                if not is_significant(raw, unit):
                    continue
                # 가장 가까운 앵커 하나만 귀속 대상으로 본다 — 한 문장이 여러 과제를
                # 열거하면 '아무 앵커나 맞으면 통과'가 되어 실제 오귀속이 빠져나간다
                near = min(anchors, key=lambda a: abs(a[0] - m.start()))[1] if anchors else None
                claims.append({
                    "value": raw,
                    "unit": unit or None,
                    "anchor": near,
                    "line": lineno,
                    "text": line.strip()[:160],
                })
    return claims


def anchor_windows(source, anchor, window):
    """원문에서 해당 과제 앵커가 등장하는 구간들.

    본문은 `#11`로 쓰지만 붙임 대장은 표 No 열에 `| 11 |`로 쓴다 — 한 형식만 보면
    대장에만 있는 값이 전부 '귀속 불일치'로 오탐된다(#11 SafeVision 95% 사례).

    표 형식은 **행 첫 칸(No 열)으로 한정**한다. 아무 칸이나 받으면 배정표의 '과제 수' 열
    (`| 4 |` = 4건)까지 과제 #4로 읽어, 정작 오귀속이 '근거 있음'으로 통과한다."""
    spans = []
    for pat in (rf"#{anchor}\b", rf"^\|\s*{anchor}\s*\|"):
        for m in re.finditer(pat, source, re.M):
            spans.append(source[max(0, m.start() - window):m.end() + window])
    return spans


def audit(source, claims, window):
    """근거 없는 주장만 골라 돌려준다."""
    flat = number_tokens(source)
    findings = []
    for c in claims:
        needle = normalize(c["value"])
        if needle not in flat:
            findings.append({**c, "kind": "수치-미검출"})
            continue
        if not c["anchor"]:
            continue
        windows = anchor_windows(source, c["anchor"], window)
        if not any(needle in number_tokens(w) for w in windows):
            findings.append({**c, "kind": "귀속-불일치"})
    return findings


def render(report):
    """터미널 요약 — 미검증 주장만 보여준다."""
    lines = []
    for name, r in report["panels"].items():
        head = f"[{name}] 수치 주장 {r['claims']}건 · 미검증 {len(r['ungrounded'])}건"
        lines.append(head)
        for f in r["ungrounded"]:
            anchor = f"#{f['anchor']} " if f["anchor"] else ""
            lines.append(f"  · {f['kind']} {anchor}{f['value']}{f['unit'] or ''}"
                         f" (L{f['line']}) {f['text']}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="패널 주장 수치 근거 대조")
    ap.add_argument("source", nargs="+", help="원문 파일(들)")
    ap.add_argument("--panel", action="append", required=True, metavar="이름=경로",
                    help="패널 출력 (반복 지정)")
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW,
                    help=f"앵커 근접 판정 반경(문자), 기본 {DEFAULT_WINDOW}")
    ap.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = ap.parse_args(argv)

    try:
        source = "\n".join(pathlib.Path(p).read_text(encoding="utf-8") for p in args.source)
    except OSError as e:
        print(f"원문을 읽을 수 없다: {e}", file=sys.stderr)
        return 2

    report = {"source_chars": len(source), "panels": {}}
    for spec in args.panel:
        if "=" not in spec:
            print(f"--panel 형식은 이름=경로 이다: {spec}", file=sys.stderr)
            return 2
        name, _, path = spec.partition("=")
        try:
            text = pathlib.Path(path).read_text(encoding="utf-8")
        except OSError as e:
            print(f"패널 출력을 읽을 수 없다: {e}", file=sys.stderr)
            return 2
        claims = extract_claims(text)
        report["panels"][name] = {
            "claims": len(claims),
            "ungrounded": audit(source, claims, args.window),
        }

    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report))
    return 1 if any(p["ungrounded"] for p in report["panels"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())
