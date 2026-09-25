"""근거 이미지 규격·해상도 판정 (R006·R088). stdlib-only.

픽셀을 줄여 규격에 맞추지 않는다. 표시 크기는 `postprocess_hwpx.py` `apply_figure_fit`이 hwpx에
직접 쓴다(R088) — 이 스크립트는 같은 계산으로 그 크기를 미리 알려 주고, 그 크기에서 인쇄
해상도가 충분한지만 판정한다. 종전 판정(96dpi 고정·170×90mm 초과 시 축소 권고)은 1257px 원본을
'초과'로 판정해 556px 축소를 유도했고, 인도본 그림이 96dpi로 뭉개졌다('26.8.24 1814건).

exit 0: 실효 해상도 FIGURE_MIN_DPI 이상 | 1: 미만(원본을 더 큰 해상도로 구하거나, 쓰면 인도 시 고지)
| 2: 파일·형식 오류
"""
import sys, json, argparse, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from postprocess_hwpx import (                                      # noqa: E402  (크기 계산 단독 출처)
    image_pixels, figure_display, FIGURE_MAX_H_MM, FIT_PAGE_SLACK, HU_PER_MM)

BODY_WIDTH_HU = 48190     # KCA 본문 폭 170mm (A4 59528 − 좌우 여백 5669×2, format-profile.kca.md)
MAX_W_MM = round((BODY_WIDTH_HU - FIT_PAGE_SLACK) / HU_PER_MM, 1)    # 169.0 — R042 여유 1mm


def judge(blob, max_w_mm=MAX_W_MM, max_h_mm=FIGURE_MAX_H_MM):
    w, h, dpi = image_pixels(blob)
    d = figure_display(w, h, dpi, max_w_mm, max_h_mm)
    return {"px": [w, h], "src_dpi": round(dpi) if dpi else None, "mm": [d["w_mm"], d["h_mm"]],
            "effective_dpi": d["effective_dpi"], "sharp": d["sharp"]}


if __name__ == "__main__":
    try:
        ap = argparse.ArgumentParser(description="근거 이미지 표시 크기·실효 해상도 판정")
        ap.add_argument("img")
        ap.add_argument("--max-w-mm", type=float, default=MAX_W_MM, help="표시 폭 상한(기본: 본문 폭 − 1mm)")
        ap.add_argument("--max-h-mm", type=float, default=FIGURE_MAX_H_MM, help="표시 높이 상한(R006 1/3쪽)")
        a = ap.parse_args()
        r = judge(pathlib.Path(a.img).read_bytes(), a.max_w_mm, a.max_h_mm)
        print(json.dumps(r, ensure_ascii=False))
        sys.exit(0 if r["sharp"] else 1)
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(2)
