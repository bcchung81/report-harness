#!/usr/bin/env python3
"""발표 대본 → 슬라이드별 음성 (reach-mini qwen3-TTS, stdlib-only).

대본 마크다운의 `**대본**` 블록을 슬라이드 단위로 잘라 각각 wav 로 뽑는다.
통짜 한 파일이 아니라 포인트별로 나누는 이유는 리허설 때 특정 대목만 반복해서
듣기 위해서다 — 그리고 슬라이드별 실제 소요 시간이 그대로 측정된다.

전제: reach-mini 의 TTS 서버가 :8099 에 떠 있어야 한다.
  ~/.local/share/reachy-mini-tts/crispasr-bin/crispasr --server --port 8099 \
    --backend qwen3-tts-1.7b-customvoice \
    -m .../qwen3-tts-12hz-1.7b-customvoice-q8_0.gguf \
    --codec-model .../qwen3-tts-tokenizer-12hz.gguf --voice serena

usage: tts_render.py [--speed 1.0] [--voice serena] [--only S6]
"""
import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request
import wave

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "2026-08-09-5min-script.md"
OUT = HERE / "audio"
URL = "http://127.0.0.1:8099/v1/audio/speech"

# `## S3 · 쉬웠던 절반 — 0:35~1:20` 다음의 `**대본**` 블록을 다음 `---` 까지 집는다
SLIDE = re.compile(r"^## (S\d+) · ([^—]+?)\s*—\s*(\S+)\s*$", re.M)


def blocks(text):
    """[(id, 제목, 타임코드, 대본)] — 파일 순서 그대로."""
    out = []
    marks = list(SLIDE.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        section = text[m.start():end]
        body = re.search(r"\*\*대본\*\*\n(.*?)(?=\n---|\Z)", section, re.S)
        if not body:
            continue
        # 빈 줄로 나뉜 문단을 하나로 합치되 문단 사이는 공백 한 칸
        spoken = " ".join(p.strip() for p in body.group(1).strip().split("\n\n"))
        out.append((m.group(1), m.group(2).strip(), m.group(3), spoken))
    return out


def synth(text, speed, voice):
    req = urllib.request.Request(
        URL,
        data=json.dumps({"input": text, "model": "tts",
                         "voice": voice, "speed": speed}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def duration(path):
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=1.0,
                    help="1.0 = 발표 속도에 가깝다. reach-mini 대화 기본값은 1.2")
    ap.add_argument("--voice", default="serena")
    ap.add_argument("--only", help="특정 슬라이드만 (예: S6)")
    a = ap.parse_args(argv)

    text = SCRIPT.read_text(encoding="utf-8")
    items = blocks(text)
    if a.only:
        items = [b for b in items if b[0] == a.only]
    if not items:
        print("대본 블록을 찾지 못했습니다", file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    total = 0.0
    print(f"{'슬라이드':<6} {'제목':<16} {'대본':>5} {'음성':>7}  {'배정':<12}")
    print("─" * 58)
    for sid, title, timecode, spoken in items:
        try:
            wav = synth(spoken, a.speed, a.voice)
        except urllib.error.URLError as e:
            print(f"{sid}: 합성 실패 — {e}. TTS 서버(:8099)가 떠 있는지 확인하세요",
                  file=sys.stderr)
            return 1
        path = OUT / f"{sid}.wav"
        path.write_bytes(wav)
        sec = duration(path)
        total += sec
        chars = len(re.sub(r"\s", "", spoken))
        print(f"{sid:<6} {title:<16} {chars:>4}자 {sec:>6.1f}초  {timecode}")

    print("─" * 58)
    m, s = divmod(round(total), 60)
    print(f"합계 {m}분 {s:02d}초 (순수 낭독, 쉼·전환 제외) → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
