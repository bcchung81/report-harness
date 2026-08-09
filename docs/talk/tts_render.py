#!/usr/bin/env python3
"""발표 대본 → 슬라이드별 음성 (reach-mini qwen3-TTS, stdlib-only).

대본 마크다운의 `**대본**` 블록을 슬라이드 단위로 잘라 각각 wav 로 뽑는다.
통짜 한 파일이 아니라 포인트별로 나누는 이유는 리허설 때 특정 대목만 반복해서
듣기 위해서다 — 그리고 슬라이드별 실제 소요 시간이 그대로 측정된다.

**문장 단위로 합성해 이어 붙인다.** 슬라이드 대본을 통째로 한 번에 보내면
Qwen3-TTS 가 환각을 일으킨다 — 실측: 113자짜리 S2 를 한 번에 보냈더니
"조사부터 초안, 한글 변환까지"가 "고다의 여사하, 연안, 하달 비어,
허도부도운 삼더블을"로 나왔다(STT 받아쓰기로 검출, 유사도 0.855).
reach-mini 의 대화 경로도 같은 이유로 절 단위로 보낸다(`tts.py` speak_all).
문장 사이 무음은 낭독 호흡도 만들어 준다.

전제: reach-mini 의 TTS 서버가 :8099 에 떠 있어야 한다.
  ~/.local/share/reachy-mini-tts/crispasr-bin/crispasr --server --port 8099 \
    --backend qwen3-tts-1.7b-customvoice \
    -m .../qwen3-tts-12hz-1.7b-customvoice-q8_0.gguf \
    --codec-model .../qwen3-tts-tokenizer-12hz.gguf --voice serena

합성 후에는 반드시 `tts_verify.py` 로 받아쓰기 대조를 돌린다 — 귀로 듣기 전에
환각을 잡는 유일한 방법이다.

usage: tts_render.py [--speed 1.0] [--voice serena] [--only S6]
"""
import argparse
import io
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request
import wave

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "2026-08-09-4min-script.md"
OUT = HERE / "audio"
URL = "http://127.0.0.1:8099/v1/audio/speech"

# `## S3 · 쉬웠던 절반 — 0:35~1:20` 다음의 `**대본**` 블록을 다음 `---` 까지 집는다
SLIDE = re.compile(r"^## (S\d+) · ([^—]+?)\s*—\s*(\S+)\s*$", re.M)


def blocks(text):
    """[(id, 제목, 타임코드, [문단[문장]])] — 파일 순서 그대로."""
    out = []
    marks = list(SLIDE.finditer(text))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        section = text[m.start():end]
        body = re.search(r"\*\*대본\*\*\n(.*?)(?=\n---|\Z)", section, re.S)
        if not body:
            continue
        paras = [sentences(p.strip()) for p in body.group(1).strip().split("\n\n") if p.strip()]
        out.append((m.group(1), m.group(2).strip(), m.group(3), paras))
    return out


def sentences(para):
    """문단을 문장으로 쪼갠다 — 종결부호 뒤에서만 끊고 부호는 문장에 남긴다.

    한 번에 긴 텍스트를 보내면 TTS 가 환각을 일으키므로 합성 단위를 문장으로 낮춘다."""
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", para) if s.strip()]
    return parts or [para]


def synth(text, speed, voice):
    req = urllib.request.Request(
        URL,
        data=json.dumps({"input": text, "model": "tts",
                         "voice": voice, "speed": speed}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def pcm_of(wav_bytes):
    """wav 바이트 → (프레임, 파라미터). 서버 출력은 24 kHz mono s16le 고정이다."""
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return w.readframes(w.getnframes()), w.getparams()


def render_slide(paras, speed, voice, gap_s=0.22, para_gap_s=0.5):
    """문장마다 따로 합성해 무음을 끼워 이어 붙인다.

    무음은 환각 방지의 부수효과가 아니라 낭독 호흡이기도 하다 — 문장 사이 0.22초,
    문단 사이 0.5초는 발표자가 실제로 쉬는 간격에 맞춘 값이다."""
    frames, params = [], None
    for pi, para in enumerate(paras):
        for si, sent in enumerate(para):
            data, p = pcm_of(synth(sent, speed, voice))
            params = params or p
            frames.append(data)
            last_sent = si == len(para) - 1
            if not last_sent:
                frames.append(silence(params, gap_s))
        if pi != len(paras) - 1:
            frames.append(silence(params, para_gap_s))
    return b"".join(frames), params


def silence(params, seconds):
    return b"\x00" * (int(params.framerate * seconds) * params.sampwidth * params.nchannels)


def write_wav(path, frames, params):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(params.nchannels)
        w.setsampwidth(params.sampwidth)
        w.setframerate(params.framerate)
        w.writeframes(frames)


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
    print(f"{'슬라이드':<6} {'제목':<16} {'문장':>4} {'대본':>5} {'음성':>7}  {'배정':<12}")
    print("─" * 64)
    for sid, title, timecode, paras in items:
        try:
            frames, params = render_slide(paras, a.speed, a.voice)
        except urllib.error.URLError as e:
            print(f"{sid}: 합성 실패 — {e}. TTS 서버(:8099)가 떠 있는지 확인하세요",
                  file=sys.stderr)
            return 1
        path = OUT / f"{sid}.wav"
        write_wav(path, frames, params)
        sec = duration(path)
        total += sec
        nsent = sum(len(p) for p in paras)
        chars = sum(len(re.sub(r"\s", "", s)) for p in paras for s in p)
        print(f"{sid:<6} {title:<16} {nsent:>3}개 {chars:>4}자 {sec:>6.1f}초  {timecode}")

    print("─" * 64)
    m, s = divmod(round(total), 60)
    print(f"합계 {m}분 {s:02d}초 (순수 낭독, 슬라이드 간 쉼 제외) → {OUT}")
    print("이어서 `tts_verify.py` 로 받아쓰기 대조를 돌릴 것 — 환각은 귀로만 잡힌다")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
