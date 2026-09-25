"""도식 명세 → HTML·300dpi PNG (render_diagram.py) — 슬롯 검증·연결선 좌표·해상도 기록·서체 탐지."""
import sys, json, struct, zlib, pathlib, re
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import render_diagram as rd
import postprocess_hwpx as ph

FLOW = {"type": "flow", "steps": [{"head": "과제 배정", "body": ["13분류"]}, {"head": "성과 유형", "body": "4개 유형"}],
        "result": {"head": "기관 보고", "body": ["업무량"]}}


def png(w, h):
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", b"") + chunk(b"IEND", b""))


def test_every_type_builds_and_escapes():
    specs = [FLOW,
             {"type": "compare", "arrow": "착시 차단", "left": {"head": "종전", "body": ["<속도>"]}, "right": {"head": "이번", "body": ["검수 포함"]}},
             {"type": "structure", "levels": [[{"head": "표준 로그"}], [{"head": "추출"}, {"head": "기록지"}, {"head": "대장"}]]},
             {"type": "timeline", "periods": ["9월", "10월"], "rows": [{"task": "착수", "span": [0, 1], "note": "1차"}]}]
    for spec in specs:
        frag = rd.fragment(spec)
        assert frag.startswith('<div class="dg">')
    assert "&lt;속도&gt;" in rd.fragment(specs[1])


def test_flow_steps_numbered_by_default():
    assert "① 과제 배정" in rd.fragment(FLOW) and "② 성과 유형" in rd.fragment(FLOW)
    assert "①" not in rd.fragment(dict(FLOW, numbered=False))


@pytest.mark.parametrize("bad", [
    {"type": "flow", "steps": [{"head": "하나"}]},
    {"type": "structure", "levels": [[{"head": "a"}]] * 5},
    {"type": "timeline", "periods": ["9월"], "rows": [{"task": "x", "span": [0, 1]}]},
    {"type": "compare", "left": {"head": "a"}},
    {"type": "flow", "steps": [{"head": "a", "body": ["1", "2"]}, {"head": "b", "body": ["1"]}]},
    {"type": "compare", "left": {"head": "a", "body": ["1", "2"]}, "right": {"head": "b", "body": ["1"]}},
    {"type": "structure", "levels": [[{"head": "a"}], [{"head": "b", "body": ["1"]}, {"head": "c"}]]},
    {"type": "radar"},
    {"type": "pdca", "phases": [{"head": "계획"}] * 3},
    {"type": "pdca", "phases": [{"head": "a", "body": ["1", "2"]}, {"head": "b", "body": ["1"]}, {"head": "c"}, {"head": "d"}]},
    {"type": "strategy", "vision": "v", "pillars": [{"head": "1", "items": ["a"]}]},
    {"type": "strategy", "pillars": [{"head": "1"}, {"head": "2"}]},
    {"type": "stack", "blocks": [{"label": "a"}] * 7},
    {"type": "stack", "blocks": [{"label": "a"}, {"label": "b", "cols": [{"head": str(i)} for i in range(5)]}]},
    dict(FLOW, width_mm=200),
])
def test_invalid_specs_rejected(bad):
    with pytest.raises(ValueError):
        rd.page(bad)


def test_link_centers_equal_width_cells():
    """1층 1개 → 2층 3개: 버스는 하위 양 끝 중심(1/6·5/6)까지, 상위 중심 50%에서 내려온다."""
    html = rd._link(1, 3)
    assert 'class="up" style="left:50.000%"' in html
    assert re.search(r'class="bus" style="left:16\.667%;right:16\.667%"', html)


def test_canvas_matches_body_width_at_300dpi():
    """캔버스 CSS px × 300/96 = 169mm @300dpi — 후처리가 그 폭 그대로 넣는다(R088)."""
    w = rd.width_px({"type": "flow"})
    assert w == 639 and round(w * rd.OUT_DPI / rd.CSS_DPI) == 1997
    d = ph.figure_display(1997, 600, 300, rd.DEFAULT_WIDTH_MM)
    assert d["w_mm"] == 169.0 and d["effective_dpi"] == 300


def test_page_has_no_external_url_and_probe_only_when_asked():
    doc = rd.page(FLOW)
    assert "http" not in doc and "<script" not in doc
    assert "<script" in rd.page(FLOW, probe=True)


def test_set_png_dpi_roundtrip():
    blob = rd.set_png_dpi(rd.set_png_dpi(png(100, 50), 72), 300)     # 기존 pHYs는 교체
    assert blob.count(b"pHYs") == 1
    assert round(ph.image_pixels(blob)[2]) == 300


def _ttf_with_name(name):
    raw = name.encode("utf-16-be")
    rec = struct.pack(">HHHHHH", 3, 1, 0x0412, 1, len(raw), 0)
    table = struct.pack(">HHH", 0, 1, 6 + 12) + rec + raw
    head = struct.pack(">IHHHH", 0x00010000, 1, 16, 0, 0)
    entry = struct.pack(">4sIII", b"name", 0, 12 + 16, len(table))
    return head + entry + table


def test_font_detection_by_name_table(tmp_path):
    (tmp_path / "x.ttf").write_bytes(_ttf_with_name("Malgun Gothic"))
    (tmp_path / "y.ttf").write_bytes(_ttf_with_name("Other Sans"))
    assert rd.font_names(_ttf_with_name("맑은 고딕")) == {"맑은 고딕"}
    assert rd.find_font(extra=[tmp_path]).name == "x.ttf"


def test_build_all_copies_images_with_ascii_names(tmp_path):
    """research 그림은 픽셀 그대로 복사, 파일명은 fig{NN} — kordoc은 한글 파일명을 넣지 않는다."""
    (tmp_path / "figures").mkdir()
    (tmp_path / "research").mkdir()
    src = tmp_path / "research" / "20260101-0000_원문-그림.png"
    src.write_bytes(png(1257, 768))
    (tmp_path / "figures" / "기능분류.json").write_text(
        json.dumps({"type": "image", "src": "research/20260101-0000_원문-그림.png", "caption": "기능 분류"}), encoding="utf-8")
    figs = rd.build_all(tmp_path, tmp_path / "out")
    assert figs[0]["file"] == "fig01.png" and figs[0]["sharp"] is True
    assert (tmp_path / "out" / "fig01.png").read_bytes() == src.read_bytes()
    assert f"{figs[0]['slug']}={figs[0]['file']}|{figs[0]['caption']}" == "기능분류=fig01.png|기능 분류"


def _browser():
    try:
        return rd.find_browser()
    except FileNotFoundError:
        return None


@pytest.mark.skipif(_browser() is None, reason="Chrome·Edge·Chromium 없음")
def test_capture_writes_300dpi_png(tmp_path):
    out = tmp_path / "flow.png"
    blob = rd.capture(FLOW, out, tmp_path / "flow.html")
    w, h, dpi = ph.image_pixels(blob)
    assert w == 1997 and h > 100 and round(dpi) == 300
    assert (tmp_path / "flow.html").is_file()


def test_result_box_is_emphasized_key_lines():
    frag = rd.fragment(FLOW)
    assert '<div class="b keys"><div class="key">업무량</div></div>' in frag and "<li>업무량" not in frag


def test_emphasis_node_uses_key_lines():
    spec = {"type": "structure", "levels": [[{"head": "표준 로그", "body": ["양식"]}],
                                            [{"head": "인정·검증", "emphasis": True, "body": ["T1·T2만 인정", "① 재계산 → ② 심의"]}]]}
    frag = rd.fragment(spec)
    assert '<div class="key">① 재계산 → ② 심의</div>' in frag and "<li>T1·T2만 인정" not in frag


def test_framework_types_build():
    """경영관리 프레임워크 틀 — pdca·strategy·stack('26.9.24)."""
    pdca = rd.fragment({"type": "pdca", "feedback": "차년도 반영",
                        "phases": [{"head": h, "body": ["x"]} for h in ("계획", "실행", "점검", "환류")]})
    assert pdca.count('class="chev"') == 4 and "<b>P</b>계획" in pdca and "↻ 차년도 반영" in pdca
    st = rd.fragment({"type": "strategy", "vision": "비전 문구", "goals": ["목표1"], "base": "가치",
                      "pillars": [{"head": f"전략목표 {i}", "items": ["과제"]} for i in (1, 2, 3)]})
    assert "repeat(3,1fr)" in st and st.count('class="phead"') == 3 and "핵심가치" in st
    sk = rd.fragment({"type": "stack", "blocks": [{"label": "설립목적", "body": ["목적"]},
                                                  {"label": "진단", "cols": [{"head": "공익", "body": ["a"]}, {"head": "미래", "body": ["b"]}]},
                                                  {"label": "개선", "emphasis": True, "body": ["결과"]}]})
    assert sk.count('class="sdown"') == 2 and '<div class="key">결과</div>' in sk and rd.LABEL_FILL in rd.css()


def test_build_all_records_redraw_source(tmp_path, monkeypatch):
    """외부 도식을 재작도한 명세의 source는 결과에 source·source_ok로 남는다 — 출처 ※ 줄 확인 재료."""
    (tmp_path / "figures").mkdir()
    (tmp_path / "research").mkdir()
    (tmp_path / "research" / "그림13.png").write_bytes(png(10, 10))
    spec = dict(FLOW, source="research/그림13.png")
    (tmp_path / "figures" / "a.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "figures" / "b.json").write_text(json.dumps(dict(FLOW, source="research/없음.png"), ensure_ascii=False), encoding="utf-8")
    def fake_capture(spec, out, html, font, browser):
        blob = png(1997, 700)
        pathlib.Path(out).write_bytes(blob)
        return blob
    monkeypatch.setattr(rd, "capture", fake_capture)
    figs = rd.build_all(tmp_path, tmp_path / "out")
    assert (figs[0]["source"], figs[0]["source_ok"]) == ("research/그림13.png", True)
    assert figs[1]["source_ok"] is False


def test_chart_needs_source_and_writes_values():
    """인용 차트(R092) — 출처 없으면 거부, 값은 막대마다 숫자로(색만으로 읽히지 않게, R090)."""
    import pytest
    spec = {"type": "chart", "kind": "bar", "unit": "%", "source": "research/a.md",
            "categories": ["'24", "'25"], "series": [{"name": "단축률", "values": [61.2, 75.1]}], "highlight": 1}
    h = rd.fragment(spec)
    assert "75.1" in h and "61.2" in h and rd.ACCENT in h
    with pytest.raises(ValueError):
        rd.fragment(dict(spec, source=""))
    with pytest.raises(ValueError):
        rd.fragment(dict(spec, series=[{"name": "x", "values": [1]}]))


def test_numbers_check_reads_figure_specs(tmp_path):
    """도식·차트 명세 안 수치도 경량 팩트체크 대상 — 배치값(span·width_mm)은 빼고."""
    import json, validate_hwpx as vh
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "c.json").write_text(json.dumps(
        {"type": "chart", "width_mm": 169, "categories": ["a", "b"], "series": [{"name": "x", "values": [123.4, 5]}]}),
        encoding="utf-8")
    text = vh.figure_numbers_text(tmp_path / "figures")
    assert "123.4" in text and "169" not in text
