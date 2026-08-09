#!/usr/bin/env python3
"""바이너리 자산 복원 — 바이너리 업로드를 막는 플랫폼(Gemini Spark) 대응.

Gemini Apps/Spark는 스킬 패키지에 **바이너리 파일을 넣을 수 없다**(공식 문서: 지원하지 않는
형식 = 바이너리·PDF·이미지·docx·xlsx). 머리말 배너 자산(png·bmp)이 여기 걸리므로,
gemini 타깃 빌드는 이들을 `.b64` 텍스트로 바꿔 싣는다. 이 스크립트가 변환 직전에 원본으로
되돌린다.

멱등이다 — 원본이 이미 있거나 `.b64`가 없으면 아무 것도 하지 않는다. 그래서
Claude·ChatGPT 패키지에서도 그대로 호출할 수 있고, SKILL.md 절차가 플랫폼별로 갈라지지
않는다.

usage: decode_assets.py [--assets DIR]
exit 0 항상 (복원 건수를 JSON으로 보고)
"""
import sys, json, base64, pathlib, argparse

DEFAULT = pathlib.Path(__file__).resolve().parent.parent / "assets"


def decode(assets_dir):
    restored, skipped = [], []
    for b64 in sorted(assets_dir.rglob("*.b64")):
        target = b64.with_suffix("")          # foo.png.b64 → foo.png
        if target.exists():
            skipped.append(str(target.relative_to(assets_dir)))
            continue
        target.write_bytes(base64.b64decode(b64.read_text(encoding="ascii")))
        restored.append(str(target.relative_to(assets_dir)))
    return restored, skipped


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets", default=str(DEFAULT))
    a = ap.parse_args(argv)
    d = pathlib.Path(a.assets)
    if not d.is_dir():
        print(json.dumps({"restored": [], "skipped": [], "note": f"자산 폴더 없음: {d}"},
                         ensure_ascii=False))
        return 0
    restored, skipped = decode(d)
    print(json.dumps({"restored": restored, "skipped": skipped}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
