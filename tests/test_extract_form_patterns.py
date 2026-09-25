"""기관 양식 표 틀 추출 (extract_form_patterns.py) — 장식 빈 칸 제거·특징 태그·유형 묶음."""
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import extract_form_patterns as ef


def cell(t, rs=1, cs=1):
    return {"text": t, "rowSpan": rs, "colSpan": cs}


def test_trim_drops_decorative_empty_rows_and_columns():
    cells = [[cell(""), cell(""), cell("")], [cell(""), cell("추진성과"), cell("")], [cell(""), cell("![image](a.png)"), cell("")]]
    out = ef.trim(cells)
    assert [[c["text"] for c in r] for r in out] == [["추진성과"], ["[그림]"]]


def test_features_tag_two_level_yearly_header():
    t = {"cells": [[cell("성과지표", rs=2), cell("'23년", cs=2), cell(""), cell("추진실적", rs=2)],
                   [cell(""), cell("목표"), cell("실적"), cell("")], [cell(""), cell(""), cell(""), cell("")]]}
    f = ef.table_features(t)
    assert {"header-2level", "yearly"} <= set(f["tags"])
    assert f["rows"] == 2 and f["cols"] == 4                  # 빈 셋째 행은 걷어낸다


def test_signature_groups_same_frame_across_years(tmp_path):
    """연도만 다른 같은 틀은 한 유형 — 지표가 달라도 틀의 문법으로 묶는다."""
    src = tmp_path / "src"; src.mkdir(); js = tmp_path / "js"; js.mkdir()
    for name, year in (("a_1-(1) 가.hwpx", "'23년"), ("b_2-(1) 나.hwpx", "'24년")):
        (src / name).write_bytes(b"")
        blocks = [{"type": "table", "pageNumber": 1, "table": {"cells": [[cell("성과지표"), cell(year), cell("추진실적")],
                                                                          [cell(""), cell(""), cell("")]]}},
                  {"type": "image"}]
        (js / (pathlib.Path(name).stem + ".json")).write_text(json.dumps({"blocks": blocks, "pageCount": 1}), encoding="utf-8")
    r = ef.analyze(src, js)
    assert r["tables"] == 2 and r["clusters"] == 1
    p = r["patterns"][0]
    assert p["count"] == 2 and p["n_docs"] == 2 and "yearly" in p["tags"]
    assert r["documents"]["a_1-(1) 가.hwpx"]["images"] == 1
