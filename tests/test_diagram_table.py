"""표 도식(R089) — 도식 명세를 한글 표로 조립하고, 후처리가 그 표를 일반 표 규칙으로 흐트러뜨리지 않는지."""
import sys, pathlib, zipfile, json
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import diagram_table as dt
import postprocess_hwpx as ph
import render_review_html as rr
import validate_hwpx as vh
from test_postprocess_hwpx import HEADER_XML, MIMETYPE

NS = ph.NS
W = 47906
SPECS = {
    "흐름": {"type": "flow", "caption": "흐름", "steps": [{"head": "배정", "body": ["가", "나"]},
                                                       {"head": "판정", "body": ["다", "라"]}],
             "result": {"head": "결과", "body": ["핵심 한 줄"]}},
    "비교": {"type": "compare", "caption": "비교", "arrow": "착시 차단",
             "left": {"head": "종전", "body": ["가", "나"]}, "right": {"head": "이번", "body": ["다", "라"]}},
    "체계": {"type": "structure", "caption": "체계",
             "levels": [[{"head": "상위", "body": ["가"]}],
                        [{"head": "하위1", "body": ["나"]}, {"head": "하위2", "body": ["다"]}, {"head": "하위3", "body": ["라"]}],
                        [{"head": "검증", "emphasis": True, "body": ["마"]}]]},
    "일정": {"type": "timeline", "caption": "일정", "periods": ["9월", "10월", "11월"],
             "rows": [{"task": "착수", "span": [0, 0]}, {"task": "산출", "span": [1, 2], "note": "1차"}]},
}


def _covered(g):
    seen = {}
    for x in g["cells"]:
        for r in range(x["r"], x["r"] + x["rs"]):
            for c in range(x["c"], x["c"] + x["cs"]):
                assert (r, c) not in seen, f"겹침 {(r, c)}"
                seen[(r, c)] = x
    return seen


def test_every_grid_cell_is_covered_exactly_once():
    """한글 표는 격자 칸마다 셀이 하나씩 있어야 한다 — 빈 곳은 빈 셀, 겹침 없음."""
    for name, spec in SPECS.items():
        g = dt.layout(spec, W)
        assert sum(g["widths"]) == W, name
        assert len(_covered(g)) == len(g["widths"]) * len(g["heights"]), name


def test_outer_edges_are_drawn_only_on_cards():
    """표 바깥 위·아래 선은 카드(글·음영이 있는 칸)에만 — 빈 칸(간격·화살표 열)은 선 없음('26.9.25 게이트② f10).
    일정은 칸 전체가 달력 격자라 빈 칸도 선이 맞다 — 카드형(흐름·비교·체계)만 본다."""
    for name, spec in SPECS.items():
        if spec["type"] == "timeline":
            continue
        g = dt.layout(spec, W)
        last = len(g["heights"])
        for x in g["cells"]:
            if x["fill"] or any(p[0] == "tri" or p[2] for p in x["paras"]):
                continue
            if x["r"] == 0:
                assert x["s"]["T"] is None, (name, x["r"], x["c"])
            if x["r"] + x["rs"] == last:
                assert x["s"]["B"] is None, (name, x["r"], x["c"])
    rule = next(r for r in dt.css().split("}") if r.strip().startswith(".dgt {"))
    assert "border:0" in rule                     # 리뷰의 일반 표 위·아래 굵은 선을 상속하지 않는다


def test_only_four_types_become_tables_and_render_image_opts_out():
    assert all(dt.wants_table(s) for s in SPECS.values())
    assert not dt.wants_table({"type": "pdca"})
    assert not dt.wants_table(dict(SPECS["흐름"], render="image"))


def test_compare_arrow_is_shaft_cell_plus_triangle_head():
    """비교형 가운데 = 파란 몸통 셀(라벨) + 머리 셀 안 삼각형 — 머리가 몸통보다 높아 블록 화살표로 보인다."""
    g = dt.layout(SPECS["비교"], W)
    shaft = [x for x in g["cells"] if x["fill"] == dt.rd.BLUE_FILL]
    heads = [p for x in g["cells"] for p in x["paras"] if p[0] == "tri"]
    assert len(shaft) == 1 and [q[2] for q in shaft[0]["paras"]] == ["착시", "차단"]    # 어절마다 세워 몸통을 좁힌다
    assert len(heads) == 1 and heads[0][1] == "right" and heads[0][5] == "L"
    shaft_h = sum(g["heights"][shaft[0]["r"]:shaft[0]["r"] + shaft[0]["rs"]])
    assert heads[0][3] > shaft_h


def test_flow_arrows_are_triangles_not_glyphs():
    g = dt.layout(SPECS["흐름"], W)
    tris = [p for x in g["cells"] for p in x["paras"] if p[0] == "tri"]
    assert [t[1] for t in tris].count("right") == 1 and [t[1] for t in tris].count("down") == 1
    assert not any("▶" in p[2] or "▼" in p[2] for x in g["cells"] for p in x["paras"] if p[0] != "tri")


def test_structure_connectors_are_cell_border_lines():
    g = dt.layout(SPECS["체계"], W)
    bus = [x for x in g["cells"] if dt.BUS in x["s"].values()]
    assert len(bus) >= 4                                  # 세로 내림선·가로 버스가 셀 변으로 그려진다


# ---------------------------------------------------------------- hwpx 치환 + 후처리
SECTION = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="{NS['hs']}" xmlns:hp="{NS['hp']}" xmlns:hc="{NS['hc']}">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:secPr><hp:pagePr landscape="WIDELY" width="59528" height="84188" gutterType="LEFT_ONLY"><hp:margin header="4251" footer="2835" gutter="0" left="5669" right="5669" top="2834" bottom="4252"/></hp:pagePr></hp:secPr><hp:t>&lt; '26. 1. 1.(목), 테스트팀 &gt;</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 개 요</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>[ 흐름 ]</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:pic id="9" zOrder="0"><hp:sz width="47906" height="17776"/><hc:img binaryItemIDRef="fig01" bright="0" contrast="0" effect="REAL_PIC" alpha="0"/></hp:pic></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 요지</hp:t></hp:run></hp:p>
</hs:sec>
"""


def _hwpx(tmp_path):
    path = tmp_path / "doc.hwpx"
    hpf = ('<opf:package xmlns:opf="http://www.idpf.org/2007/opf/"><opf:manifest>'
           '<opf:item id="fig01" href="BinData/fig01.png" media-type="image/png" isEmbeded="1"/>'
           '</opf:manifest></opf:package>')
    with zipfile.ZipFile(path, "w") as z:
        zi = zipfile.ZipInfo("mimetype")
        zi.compress_type = zipfile.ZIP_STORED
        z.writestr(zi, MIMETYPE)
        z.writestr("Contents/content.hpf", hpf)
        z.writestr("Contents/header.xml", HEADER_XML)
        z.writestr("Contents/section0.xml", SECTION)
        z.writestr("BinData/fig01.png", b"\x89PNG fake")
    work = tmp_path / "work"
    (work / "figures").mkdir(parents=True)
    (work / "figures" / "흐름.json").write_text(json.dumps(SPECS["흐름"], ensure_ascii=False), encoding="utf-8")
    figs = tmp_path / "41_figures.json"
    figs.write_text(json.dumps({"figures": [{"slug": "흐름", "file": "fig01.png", "type": "flow"}]}), encoding="utf-8")
    return path, work, figs


def _tables(path):
    with zipfile.ZipFile(path) as z:
        sec = ET.fromstring(z.read("Contents/section0.xml"))
        head = ET.fromstring(z.read("Contents/header.xml"))
        names = z.namelist()
        hpf = z.read("Contents/content.hpf").decode()
    return sec, head, names, hpf


def test_convert_swaps_picture_for_marked_table(tmp_path):
    path, work, figs = _hwpx(tmp_path)
    rep = dt.convert(path, work, figs)
    assert [r["slug"] for r in rep["replaced"]] == ["흐름"]
    sec, head, names, hpf = _tables(path)
    assert sec.find(f".//{ph.qn('hp', 'pic')}") is None
    tbl = sec.find(f".//{ph.qn('hp', 'tbl')}")
    assert ph.is_figure_table(tbl) and tbl.get("pageBreak") == "NONE"
    assert len(list(tbl.iter(ph.qn("hp", "polygon")))) == 2          # ▶ 1 + ▼ 1
    assert "BinData/fig01.png" not in names and "fig01" not in hpf  # 쓰지 않는 그림을 남기지 않는다


def test_postprocess_embeds_caption_but_leaves_figure_table_layout(tmp_path):
    """후처리: `[ 흐름 ]`은 표 캡션으로 들어가고, 열 폭·셀 글자 크기·쪽 나눔은 도식이 정한 그대로."""
    path, work, figs = _hwpx(tmp_path)
    dt.convert(path, work, figs)
    sec0, _, _, _ = _tables(path)
    before = [tc.find(ph.qn("hp", "cellSz")).get("width") for tc in sec0.iter(ph.qn("hp", "tc"))]
    ph.process_file(path, spacing=True)
    sec, head, _, _ = _tables(path)
    tbl = sec.find(f".//{ph.qn('hp', 'tbl')}")
    cap = tbl.find(ph.qn("hp", "caption"))
    assert cap is not None and "[ 흐름 ]" in "".join(t.text or "" for t in cap.iter(ph.qn("hp", "t")))
    assert tbl.get("pageBreak") == "NONE"
    assert [tc.find(ph.qn("hp", "cellSz")).get("width") for tc in tbl.iter(ph.qn("hp", "tc"))] == before
    heights = {cp.get("id"): cp.get("height") for cp in head.iter(ph.qn("hh", "charPr"))}
    cell_runs = [r.get("charPrIDRef") for tc in tbl.iter(ph.qn("hp", "tc")) for r in tc.iter(ph.qn("hp", "run"))
                 if r.find(ph.qn("hp", "t")) is not None]
    assert {heights[c] for c in cell_runs} >= {"1100", "1000"}          # 머리 11pt·본문 10pt 유지(12pt 일괄 아님)


def test_convert_keeps_image_when_spec_opts_out(tmp_path):
    path, work, figs = _hwpx(tmp_path)
    (work / "figures" / "흐름.json").write_text(json.dumps(dict(SPECS["흐름"], render="image")), encoding="utf-8")
    rep = dt.convert(path, work, figs)
    assert rep["replaced"] == [] and rep["kept_image"][0]["slug"] == "흐름"


def test_review_draws_the_same_table(tmp_path):
    """리뷰(게이트②)도 같은 격자로 — 표 도식은 <table class="dgt">, 그림 선택은 기존 도식 조각."""
    work = tmp_path / "w"
    (work / "figures").mkdir(parents=True)
    (work / "figures" / "a.json").write_text(json.dumps(SPECS["비교"], ensure_ascii=False), encoding="utf-8")
    out = rr.figure_html("a", work, [10 ** 6])
    assert '<table class="dgt"' in out and "<polygon" in out
    (work / "figures" / "a.json").write_text(json.dumps(dict(SPECS["비교"], render="image"), ensure_ascii=False),
                                              encoding="utf-8")
    assert '<table class="dgt"' not in rr.figure_html("a", work, [10 ** 6])


def test_compare_counts_figures_turned_into_tables():
    """도해 마커가 그림 대신 표로 되읽히면 합으로 대조한다(그림 감소분 = 표 증가분)."""
    src = "□ 개 요\n\n[ 흐름 ]\n\n도해: 흐름\n\nㅇ 요지\n"
    rt = "□ 개 요\n\n<table><tr><td>① 배정</td><td>② 판정</td><td>결과</td></tr></table>\n\nㅇ 요지\n"
    issues = [i["rule"] for i in vh.compare_texts(src, rt)]
    assert not any(r.startswith("count-mismatch") for r in issues), issues


# ---------------------------------------------------------------- 배색 역할 (R090)
import pytest
import render_diagram as rd


def test_accent_is_one_card_with_color_and_thick_border():
    spec = json.loads(json.dumps(SPECS["흐름"]))
    spec["steps"][1]["tone"] = "accent"
    g = dt.layout(spec, W)
    acc = [x for x in g["cells"] if x["fill"] == rd.ACCENT]
    assert len(acc) == 1 and dt.ACC in acc[0]["s"].values()              # 색 + 굵은 테두리(두 번째 채널)
    assert 'class="box acc"' in rd.fragment(spec)
    spec["steps"][0]["tone"] = "accent"
    with pytest.raises(ValueError):                                     # 강조는 도식당 1곳
        dt.layout(spec, W)


def test_timeline_status_is_shade_plus_label():
    spec = json.loads(json.dumps(SPECS["일정"]))
    spec["rows"][0]["status"] = "done"
    g = dt.layout(spec, W)
    bar = next(x for x in g["cells"] if x["fill"] == rd.STATUS["done"][0])
    assert bar["paras"][0][2] == "완료"                                  # 라벨이 없으면 상태 이름을 쓴다
    spec["rows"][0]["status"] = "unknown"
    with pytest.raises(ValueError):
        rd.fragment(spec)


def test_compare_old_side_is_dashed_and_new_side_strong():
    g = dt.layout(SPECS["비교"], W)
    heads = {x["paras"][0][2]: x for x in g["cells"] if x["paras"] and x["paras"][0][0] == "C" and x["fill"]}
    assert heads["종전"]["fill"] == rd.HEAD_OLD and dt.DASH in heads["종전"]["s"].values()
    assert heads["이번"]["fill"] == rd.HEAD_STRONG


# ---------------------------------------------------------------- 카드 문장 내어쓰기 (R093)
def test_card_items_hang_in_review_and_hwpx(tmp_path):
    """둘째 줄이 부호 아래가 아니라 첫 줄 글자 아래에서 시작한다('26.9.25 게이트② f12) — 리뷰는 고정 폭 부호 칸,
    한글은 본문 계층과 같은 left 0·intent -hang + 부호 뒤 탭(내어쓰기 자동 탭)."""
    hang = dt.CARD_HANG / 100
    html = dt.html(SPECS["비교"])
    assert f"padding-left:{hang:g}pt;text-indent:-{hang:g}pt" in html
    assert f'<span style="display:inline-block;width:{hang:g}pt;text-indent:0">{dt.CARD_MARK}</span>가' in html
    assert f"{dt.CARD_MARK} 가" not in html

    path, work, figs = _hwpx(tmp_path)
    dt.convert(path, work, figs)
    sec, head, _, _ = _tables(path)
    tab_path = f"{ph.qn('hp', 'run')}/{ph.qn('hp', 't')}/{ph.qn('hp', 'tab')}"      # 표를 품은 바깥 문단은 빼고
    paras = [p for p in sec.iter(ph.qn("hp", "p")) if p.find(tab_path) is not None]
    assert paras, "카드 항목 문단에 부호 뒤 탭이 없다"
    pprs = {pp.get("id"): pp for pp in head.iter(ph.qn("hh", "paraPr"))}
    tabs = {tp.get("id"): tp for tp in head.iter(ph.qn("hh", "tabPr"))}
    for p in paras:
        t = p.find(f".//{ph.qn('hp', 't')}")
        assert t.text == dt.CARD_MARK and t.find(ph.qn("hp", "tab")).tail in ("가", "나", "다", "라")
        pp = pprs[p.get("paraPrIDRef")]
        mg = {e.tag.split("}")[1]: e.get("value") for e in pp.find(ph.qn("hh", "margin"))}
        assert mg["intent"] == str(-dt.CARD_HANG) and mg["left"] == "0"
        assert tabs[pp.get("tabPrIDRef")].get("autoTabLeft") == "1"


def test_card_hang_narrows_every_line_in_height_estimate():
    """내어쓰기 항목은 모든 줄이 부호 칸만큼 좁다 — 같은 글이면 줄 수가 같거나 늘지, 줄지 않는다."""
    long = "운영 AI 여부부터 효과 성격까지 6개 질문으로 유형 판정"
    for w in range(6000, 20000, 500):
        assert dt.paras_height(dt.card_items([long]), w) >= dt.paras_height([("L", "body", long)], w)


def test_compare_arrow_follows_label_not_card_height():
    """화살표는 라벨 높이로 정한다 — 카드가 길어져도 머리 높이가 따라 커지지 않고, 줄인 폭만큼 카드가 넓다
    ('26.9.25 게이트② f15 — 머리가 도식 높이의 84%라 카드만큼 컸다)."""
    def head(spec):
        g = dt.layout(spec, W)
        return [p for x in g["cells"] for p in x["paras"] if p[0] == "tri"][0], g
    def spec(words):
        return dict(SPECS["비교"], left={"head": "종전", "body": ["가 " * words] * 3},
                    right={"head": "이번", "body": ["나 " * words] * 3})
    short, g1 = head(spec(20))
    long_, g2 = head(spec(60))
    assert long_[3] == short[3] and long_[2] == short[2]      # 카드가 세 배 길어져도 머리는 그대로
    assert sum(g2["heights"]) > 2 * long_[3]                  # 머리는 카드 높이의 절반도 안 된다
    assert g1["widths"][0] > (W - 5200 - 1800) // 2           # 종전 고정 폭(몸통 5200 + 머리 1800)보다 카드가 넓다


def test_short_compare_cards_grow_instead_of_clipping_the_arrow():
    """카드가 화살표보다 낮으면 카드 본문을 늘린다 — 자르면 머리 비율·칸 폭이 어긋나고 라벨 칸이 라벨보다 낮아진다
    ('26.9.25 코드 리뷰)."""
    spec = dict(SPECS["비교"], arrow="착시 차단", left={"head": "종전", "body": ["가"]}, right={"head": "이번", "body": ["나"]})
    g = dt.layout(spec, W)
    shaft_cell = [x for x in g["cells"] if x["fill"] == dt.rd.BLUE_FILL][0]
    shaft_h = sum(g["heights"][shaft_cell["r"]:shaft_cell["r"] + shaft_cell["rs"]])
    head = [p for x in g["cells"] for p in x["paras"] if p[0] == "tri"][0]
    label = dt.arrow_label(spec["arrow"])
    assert shaft_h >= dt.paras_height(label, g["widths"][1], (200, 200, 100, 100))     # 라벨이 칸에 다 들어간다
    assert sum(g["heights"]) >= head[3] + 200                                          # 머리가 카드 안에 온전히
    assert abs(head[2] / head[3] - dt.ARROW_HEAD_ASPECT) < 0.02 or head[2] == 700      # 머리 비율 유지
