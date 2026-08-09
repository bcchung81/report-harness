#!/usr/bin/env python3
"""합성 음성 → STT 받아쓰기 → 대본 대조 (환각·오독 검출).

LLM 기반 TTS(Qwen3-TTS)는 입력이 길면 **없는 말을 지어내거나 문장을 건너뛴다.**
귀로 듣기 전에는 안 보이므로, 만든 음성을 다시 받아써서 원본과 대조한다.
소리를 못 듣는 상태에서 품질을 주장하지 않기 위한 장치다.

reach-mini 의 mlx-whisper 를 쓴다. ffmpeg 이 없어도 되도록 wav 를 직접 읽어
16 kHz float32 로 넘긴다(mlx_whisper 가 기대하는 형식).

usage: tts_verify.py [--only S2] [--threshold 0.88]
  exit 0 전부 임계 이상 / 1 의심 구간 있음 / 2 실행 오류
"""
import argparse
import difflib
import pathlib
import re
import subprocess
import sys
import wave

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "2026-08-09-5min-script.md"
AUDIO = HERE / "audio"
REACH = pathlib.Path.home() / "workspace" / "reach-mini"
VENV_PY = REACH / ".venv" / "bin" / "python"
MODEL = "mlx-community/whisper-large-v3-turbo"

SLIDE = re.compile(r"^## (S\d+) · ([^—]+?)\s*—\s*(\S+)\s*$", re.M)

# STT 는 수사를 숫자로 받아쓴다('일흔다섯'→'75'). 그대로 비교하면 정상 낭독이
# 오탐으로 잡히므로(S7 이 0.416 으로 나왔다) 양쪽을 숫자로 모아 놓고 비교한다.
# 범용 한국어 수사 파서가 아니라 이 대본에 실제로 나오는 것만 다룬다.
NUMERALS = [
    ("일흔다섯", "75"), ("서른다섯", "35"), ("마흔세", "43"), ("일흔", "70"),
    ("예순", "60"), ("여덟", "8"), ("열", "10"), ("두 배", "2배"),
    ("세 개", "3개"), ("세 번", "3번"), ("네 단계", "4단계"), ("두 번", "2번"),
    ("두 달", "2달"), ("넉 달", "4달"), ("두 가지", "2가지"), ("한 줄", "1줄"),
]


def norm(s):
    for ko, digit in NUMERALS:
        s = s.replace(ko, digit)
    return re.sub(r"[^가-힣0-9a-zA-Z]", "", s)


def blocks():
    text = SCRIPT.read_text(encoding="utf-8")
    out, marks = [], list(SLIDE.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = re.search(r"\*\*대본\*\*\n(.*?)(?=\n---|\Z)", text[m.start():end], re.S)
        if body:
            spoken = " ".join(p.strip() for p in body.group(1).strip().split("\n\n"))
            out.append((m.group(1), m.group(2).strip(), spoken))
    return out


TRANSCRIBE = '''
import sys, wave, numpy as np, mlx_whisper
p = sys.argv[1]
with wave.open(p) as w:
    sr, n = w.getframerate(), w.getnframes()
    pcm = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32) / 32768.0
# whisper 는 16 kHz 를 기대한다. STT 용도라 선형 보간으로 충분하다.
if sr != 16000:
    tgt = int(len(pcm) * 16000 / sr)
    pcm = np.interp(np.linspace(0, len(pcm) - 1, tgt), np.arange(len(pcm)), pcm).astype(np.float32)
r = mlx_whisper.transcribe(pcm, path_or_hf_repo=sys.argv[2], language="ko")
print(r["text"].strip())
'''


def transcribe(path):
    r = subprocess.run([str(VENV_PY), "-c", TRANSCRIBE, str(path), MODEL],
                       capture_output=True, text=True, cwd=str(REACH))
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "").strip()[-400:])
    return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--threshold", type=float, default=0.88,
                    help="유사도 하한. STT 자체 오차가 있어 1.0 은 나오지 않는다")
    a = ap.parse_args(argv)

    if not VENV_PY.is_file():
        print(f"reach-mini venv 없음 — {VENV_PY}", file=sys.stderr)
        return 2

    items = [b for b in blocks() if not a.only or b[0] == a.only]
    bad = []
    print(f"{'슬라이드':<6} {'유사도':>6}  판정")
    print("─" * 70)
    for sid, title, spoken in items:
        wav = AUDIO / f"{sid}.wav"
        if not wav.is_file():
            print(f"{sid:<6}      —  음성 없음 — tts_render.py 먼저 실행")
            bad.append(sid)
            continue
        try:
            heard = transcribe(wav)
        except RuntimeError as e:
            print(f"{sid}: 받아쓰기 실패 — {e}", file=sys.stderr)
            return 2
        ratio = difflib.SequenceMatcher(None, norm(spoken), norm(heard)).ratio()
        ok = ratio >= a.threshold
        print(f"{sid:<6} {ratio:>6.3f}  {'정상' if ok else '★ 의심'}  {title}")
        if not ok:
            bad.append(sid)
            # 어긋난 구간만 뽑아 보여준다 — 어느 낱말이 지어졌는지 바로 보이게
            sm = difflib.SequenceMatcher(None, spoken.split(), heard.split())
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    continue
                src = " ".join(spoken.split()[i1:i2]) or "(없음)"
                got = " ".join(heard.split()[j1:j2]) or "(빠짐)"
                print(f"         대본: {src[:60]}")
                print(f"         음성: {got[:60]}")
    print("─" * 70)
    print("의심 구간 없음" if not bad else f"의심 {len(bad)}건: {', '.join(bad)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
