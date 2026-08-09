#!/usr/bin/env python3
"""audio/SN.wav 실측 길이 → 덱·대본 타임코드 동기화 (stdlib-only).

tts_render.py 가 만든 슬라이드별 wav 의 실제 길이를 재서
  1. deck.html 의 data-time (각 장의 누적 시작 시각)
  2. 대본 md 의 `## SN · 제목 — a:bb~c:dd` 구간 표기
  3. 대본 md 머리의 낭독 자수·총 소요 표기
를 실측값으로 바꿔 쓴다. 추정 타임코드가 실측과 어긋난 채 남는 것을 막는
장치다 — 자동 발표(deck.html 의 A 키)는 wav 길이 그대로 진행되므로,
여기서 쓴 값이 곧 실제 진행표가 된다.

장 사이 쉼(GAP)은 deck.html 의 SLIDE_GAP_MS 와 같은 값을 쓴다.

usage: sync_timecodes.py [--limit 240]
  exit 0 총 소요가 한도 이내 / 1 한도 초과 / 2 실행 오류
"""
import argparse
import json
import pathlib
import re
import sys
import wave

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "2026-08-09-4min-script.md"
DECK = HERE / "deck.html"
AUDIO = HERE / "audio"
GAP_S = 0.6  # deck.html SLIDE_GAP_MS 와 동일해야 한다

SLIDE = re.compile(r"^## (S\d+) · ([^—]+?)\s*—\s*(\S+)\s*$", re.M)


def mmss(sec):
    m, s = divmod(round(sec), 60)
    return f"{m}:{s:02d}"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=float, default=240.0,
                    help="총 소요 한도(초). 기본 240 = 4분")
    a = ap.parse_args(argv)

    md = SCRIPT.read_text(encoding="utf-8")
    marks = list(SLIDE.finditer(md))
    if not marks:
        print("대본에서 슬라이드 헤딩을 찾지 못했습니다", file=sys.stderr)
        return 2

    durs = {}
    for m in marks:
        sid = m.group(1)
        path = AUDIO / f"{sid}.wav"
        if not path.exists():
            print(f"{path} 없음 — tts_render.py 를 먼저 실행", file=sys.stderr)
            return 2
        with wave.open(str(path)) as w:
            durs[sid] = w.getnframes() / w.getframerate()

    # 누적 시작 시각 (장 사이 GAP 포함)
    starts, t = {}, 0.0
    for m in marks:
        sid = m.group(1)
        starts[sid] = t
        t += durs[sid] + GAP_S
    total = t - GAP_S  # 마지막 장 뒤 쉼은 없다

    deck = DECK.read_text(encoding="utf-8")
    print(f"{'슬라이드':<6} {'음성':>7} {'시작':>6}")
    print("─" * 26)
    for i, m in enumerate(marks):
        sid, title = m.group(1), m.group(2).strip()
        start = mmss(starts[sid])
        end = "끝" if i == len(marks) - 1 else mmss(starts[marks[i + 1].group(1)])
        deck, n = re.subn(
            rf'(data-id="{sid}" data-time=")[^"]*(")', rf"\g<1>{start}\g<2>", deck)
        if n != 1:
            print(f"deck.html 에서 {sid} data-time 을 못 찾음", file=sys.stderr)
            return 2
        md = md.replace(m.group(0), f"## {sid} · {title} — {start}~{end}")
        print(f"{sid:<6} {durs[sid]:>6.1f}초 {start:>6}")
    print("─" * 26)

    # 문장 큐 주입 — 자동 발표 하이라이트(data-cue)가 이 값으로 동기화한다
    cues_path = AUDIO / "cues.json"
    if cues_path.exists():
        cues = json.loads(cues_path.read_text())
        deck, n = re.subn(
            r"const CUES = .*?; // cues:auto",
            "const CUES = " + json.dumps(cues, separators=(",", ":")) + "; // cues:auto",
            deck, count=1)
        if n != 1:
            print("deck.html 에 cues:auto 마커가 없습니다 — 큐 주입 생략", file=sys.stderr)

    chars = sum(len(re.sub(r"\s", "", s))
                for b in re.findall(r"\*\*대본\*\*\n(.*?)(?=\n---|\Z)", md, re.S)
                for s in b.strip().splitlines())
    md = re.sub(r"낭독 \d+자 · 도식 포함 \*\*약? ?[^*]+\*\*",
                f"낭독 {chars}자 · 음성 실측 **{mmss(total)}**", md, count=1)

    DECK.write_text(deck, encoding="utf-8")
    SCRIPT.write_text(md, encoding="utf-8")

    over = total > a.limit
    verdict = "한도 초과 — 대본을 줄일 것" if over else "한도 이내"
    print(f"총 {mmss(total)} (장 사이 쉼 {GAP_S}초 포함) / 한도 {mmss(a.limit)} → {verdict}")
    return 1 if over else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
