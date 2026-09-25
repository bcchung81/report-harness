"""근거 이미지 규격·해상도 판정 (R006·R088).

픽셀을 줄여 규격에 맞추던 종전 판정(96dpi 고정)은 1257px 원본을 '초과'로 판정해 556px 축소를
유도했고, 인도본 인쇄 해상도가 96dpi로 떨어졌다. 지금은 표시 크기를 계산해 해상도만 판정한다.
"""
import sys, pathlib, struct, zlib, subprocess, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
from check_image_size import judge, MAX_W_MM
import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts/check_image_size.py"


def png(w, h, dpi=None):
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    if dpi:
        ppm = int(round(dpi / 0.0254))
        out += chunk(b"pHYs", struct.pack(">IIB", ppm, ppm, 1))
    return out + chunk(b"IEND", b"")


def test_max_width_is_body_minus_slack():
    assert MAX_W_MM == 169.0          # 본문 170mm − R042 여유 1mm


def test_large_original_is_sharp_not_oversize():
    """1257×768px 원본은 상자에 맞춰 147.3×90mm로 표시되고 217dpi — 줄일 필요가 없다."""
    r = judge(png(1257, 768))
    assert r["mm"] == [147.3, 90.0] and r["effective_dpi"] == 217 and r["sharp"] is True


def test_downsampled_copy_is_low_res():
    r = judge(png(556, 340))
    assert r["effective_dpi"] == 96 and r["sharp"] is False


def test_embedded_dpi_sets_natural_size():
    r = judge(png(1417, 600, 300))
    assert r["mm"] == [120.0, 50.8] and r["src_dpi"] == 300


def test_cli_exit_codes(tmp_path):
    hi, lo, bad = tmp_path / "hi.png", tmp_path / "lo.png", tmp_path / "fake.bin"
    hi.write_bytes(png(2000, 1000, 300))
    lo.write_bytes(png(556, 340))
    bad.write_bytes(b"\x00\x01" + bytes(100))
    run = lambda p: subprocess.run([sys.executable, str(SCRIPT), str(p)], capture_output=True, text=True)
    assert run(hi).returncode == 0
    r = run(lo)
    assert r.returncode == 1 and json.loads(r.stdout)["sharp"] is False
    r = run(bad)
    assert r.returncode == 2 and "error" in json.loads(r.stdout)
    r = run("/nonexistent/x.png")
    assert r.returncode == 2 and "error" in json.loads(r.stdout)


def test_narrower_box_option(tmp_path):
    p = tmp_path / "hi.png"
    p.write_bytes(png(2000, 1000, 300))
    r = subprocess.run([sys.executable, str(SCRIPT), str(p), "--max-w-mm", "80"], capture_output=True, text=True)
    assert json.loads(r.stdout)["mm"][0] == 80.0
