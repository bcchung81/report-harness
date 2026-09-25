"""research 그림 후보 목록 — 출처·해상도 판정·권고 (list_research_figures.py)."""
import sys, json, struct, zlib, pathlib, subprocess
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import list_research_figures as lrf

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts/list_research_figures.py"


def _png(w, h, dpi=None):
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    if dpi:
        ppm = int(round(dpi / 0.0254))
        out += chunk(b"pHYs", struct.pack(">IIB", ppm, ppm, 1))
    return out + chunk(b"IDAT", b"") + chunk(b"IEND", b"")


def test_lists_images_with_source_and_sharpness(tmp_path):
    r = tmp_path / "research"
    r.mkdir()
    (r / "a-그림13.png").write_bytes(_png(1257, 780))           # 96dpi 가정 → 145×90mm에서 220dpi
    (r / "b-scaled.png").write_bytes(_png(556, 340))            # 축소본 → 96dpi
    (r / "원문.pdf").write_bytes(b"%PDF-1.4")
    (r / "_manifest.jsonl").write_text(json.dumps({"file": "a-그림13.png", "title": "그림 13 성과지표 프레임워크",
                                                    "source_url": "vault:x.png"}, ensure_ascii=False) + "\n", encoding="utf-8")
    out = lrf.collect(tmp_path)
    figs = {f["file"]: f for f in out["figures"]}
    assert figs["a-그림13.png"]["sharp"] is True and figs["a-그림13.png"]["title"] == "그림 13 성과지표 프레임워크"
    assert figs["a-그림13.png"]["spec_src"] == "research/a-그림13.png"
    assert figs["b-scaled.png"]["sharp"] is False and "재작도" in figs["b-scaled.png"]["advice"]
    assert out["sources"] == [{"file": "원문.pdf", "title": None}] and (out["sharp"], out["blurry"]) == (1, 1)
    assert not (r / "_figures.json").exists()                  # research에 파일을 만들지 않는다


def test_cli_prints_json(tmp_path):
    (tmp_path / "research").mkdir()
    r = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 0 and json.loads(r.stdout) == {"figures": [], "sources": [], "sharp": 0, "blurry": 0}
