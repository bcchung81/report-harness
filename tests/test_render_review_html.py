"""초안 리뷰 HTML — 게이트② 절 주소·양식 값 단독 출처·정적 페이지 (render_review_html.py)."""
import sys, json, pathlib, subprocess, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import render_review_html as rr
import postprocess_hwpx as ph

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts/render_review_html.py"

DRAFT = """시험 보고

< '26. 9. 24.(목), 경영기획본부 AI디지털심화팀 >

□ 개 요

ㅇ **(측정 기준)** 과제 18건을 ==4개 유형==으로 나눔

  - 검수 시간을 넣어 착시를 차단

[ 측정 체계 흐름 ]

| 단 계 | 결 과 |
| --- | --- |
| 과제 배정 | 18건 <배정> |

※ 금액 환산은 하지 않음

□ 주요 내용

[1] 과제 배정

ㅇ **(판정)** 여섯 질문으로 판정

| 처리시간 개선율 = (전 - 후) ÷ 전 × 100 |
| --- |

도해: 기능분류

| 붙임 1 | | 과제 대장 |
| --- | --- | --- |

| No | 과제명 |
| --- | --- |
| 1 | 방송 심사자료 |

끝.
"""


def kinds(text=DRAFT):
    return [b["kind"] for b in rr.parse(text)]


def test_parse_classifies_every_line_kind():
    assert kinds() == ["title", "sending", "dae", "yo", "dash", "caption", "table", "cham",
                       "dae", "sub", "yo", "formula", "marker", "banner", "table", "end"]


def test_addresses_follow_gate2_convention():
    addr = {b["line"]: b["addr"] for b in rr.address(rr.parse(DRAFT))}
    lines = DRAFT.splitlines()
    at = lambda s: addr[next(i for i, l in enumerate(lines, 1) if l.strip().startswith(s))]
    assert at("□ 개 요") == "□1" and at("ㅇ **(측정") == "□1-ㅇ1" and at("- 검수") == "□1-ㅇ1-1"
    assert at("| 단 계") == "□1-표1" and at("※ 금액") == "□1-※1"
    assert at("ㅇ **(판정") == "□2-ㅇ1" and at("| 처리시간") == "□2-표1"
    assert at("| 붙임 1") == "붙임1" and at("| No") == "붙임1-표1"
    assert at("도해: 기능분류") == "□2-그림1"                       # 그림은 □ 줄과 다른 고유 주소


def test_title_and_sender_are_selectable_blocks():
    """제목표·발신 줄도 코멘트 대상 — 라이브 패널은 `.blk[data-addr]`만 고른다('26.9.24 지적)."""
    doc, _ = rr.render(DRAFT)
    for addr in ("제목", "발신"):
        assert re.search(rf'<div class="blk [a-z]+" id="L\d+" data-line="\d+" data-addr="{addr}"', doc), addr
    assert re.search(r'data-addr="제목"><span class="addr">제목</span><div class="titlebox">', doc)


def test_gaps_come_from_postprocess_spacers():
    assert rr.gap_pt("dae", "yo") == ph.TRANSITIONS[("dae", "yo")][1] / 100
    assert rr.gap_pt("yo", "dash") == ph.TRANSITIONS[("yo", "dash")][1] / 100
    assert rr.gap_pt("cham", "dae") == ph.BLOCK_BOUNDARY_HEIGHT / 100
    assert rr.gap_pt("sending", "dae") == ph.TRANSITIONS[("sending", "dae")][1] / 100


def test_page_is_static_and_escaped():
    """스크립트·외부 URL 없음(리뷰 도구가 페이지 스크립트의 외부 요청을 막지 않는다), 본문은 이스케이프."""
    doc, counts = rr.render(DRAFT)
    assert "<script" not in doc and not re.search(r"(?:src|href)=\"https?://", doc) and "@import" not in doc
    assert "&lt;배정&gt;" in doc and "<mark>4개 유형</mark>" in doc and "<b>(측정 기준)</b>" in doc
    assert counts["dae"] == 2 and counts["banner"] == 1
    assert doc.count('<section class="page">') == 2          # 붙임은 새 쪽에서 시작한다


def test_cli_writes_into_history_drafts(tmp_path):
    d = tmp_path / "0900_건"
    d.mkdir()
    (d / "20_draft.md").write_text(DRAFT, encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), str(d / "20_draft.md")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert pathlib.Path(out["html"]) == d / "history" / "drafts" / "25_review.html"
    assert pathlib.Path(out["html"]).is_file()
    assert re.fullmatch(r"26_review\.\d{8}-\d{6}\.json", pathlib.Path(out["result"]).name)
    assert not pathlib.Path(out["result"]).exists()     # 리뷰 도구가 새로 만든다(덮어쓰기 금지 규약)
    assert sorted(p.name for p in d.iterdir()) == ["20_draft.md", "history"]   # 루트에 파생물 없음(R087)


def test_marker_renders_diagram_and_image(tmp_path):
    """`도해:` 자리에 figures 명세로 도식 조각을, research 그림은 data URI를 싣는다."""
    import base64, struct, zlib
    (tmp_path / "figures").mkdir()
    (tmp_path / "research").mkdir()
    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body))
    img = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1257, 768, 8, 2, 0, 0, 0)) + chunk(b"IEND", b"")
    (tmp_path / "research" / "a.png").write_bytes(img)
    (tmp_path / "figures" / "흐름.json").write_text(json.dumps(
        {"type": "flow", "steps": [{"head": "가"}, {"head": "나"}]}), encoding="utf-8")
    (tmp_path / "figures" / "원문.json").write_text(json.dumps({"type": "image", "src": "research/a.png"}), encoding="utf-8")
    text = DRAFT.replace("도해: 기능분류", "도해: 흐름\n\n도해: 원문\n\n도해: 없는것")
    doc, counts = rr.render(text, work_dir=tmp_path)
    assert counts["figure"] == 2
    assert '<table class="dgt"' in doc                       # 흐름도는 변환과 같은 표 도식으로(R089)
    assert "data:image/png;base64," + base64.b64encode(img).decode() in doc
    assert "그림 자리 — 도해: 없는것" in doc


def test_line_fit_matches_postprocess():
    """계층 문단은 한글 산출물과 같은 장평·자간으로 그린다 — 후처리 fit_line과 같은 값(R062)."""
    short = rr.fit_style("yo", "짧은 문장")
    assert "transform:scaleX(0.95)" in short[0] and "letter-spacing:-0.08em" in short[0] and short[1] is False
    assert "letter-spacing:-0.08em" in rr.fit_style("yo", ("가 " * 44).strip())[0]   # 2줄 — 그대로
    style, over, _ = rr.fit_style("yo", ("가 " * 45).strip())   # 3줄(어절 단위·여유 3%) — 자간부터 조인다
    assert over is False and "letter-spacing:-0.1em" in style and "scaleX(0.95)" in style
    style, over, _ = rr.fit_style("yo", ("가나 " * 28 + "가").strip())   # 자간 하한으로도 3줄 — 장평까지(95 → 91)
    assert over is False and "letter-spacing:-0.1em" in style and "scaleX(0.91)" in style
    # □·-·※는 kordoc이 100/0으로 둔다 — 같은 값에서 출발해야 한글과 줄 수가 같다('26.9.24 시험 변환)
    assert "letter-spacing:0em" in rr.fit_style("dash", "짧은 문장")[0] and "scaleX(1)" in rr.fit_style("cham", "짧음")[0]
    style, over, _ = rr.fit_style("yo", ("가 " * 49).strip())   # 하한까지 조여도 3줄 — 넘침 표시
    assert over is True
    doc, _ = rr.render(DRAFT.replace("과제 18건을", "과제 18건을 " + "가" * 110))
    assert 'class="blk over yo"' in doc
    assert rr.fit_style("table", "무엇이든") == ("", False, 1.0)


def test_marker_cell_aligns_first_line_with_hanging_indent():
    """부호 칸 폭 = 내어쓰기 — 첫 줄 본문이 둘째 줄과 같은 자리에서 시작한다(게이트② 지적 '26.9.24)."""
    import postprocess_hwpx as ph
    cell = rr.marker_html("dash", "-", 1.0)
    assert f"width:{ph.HIERARCHY_HANG['dash'] / 100:.2f}pt" in cell
    assert f"padding-left:{ph.HIERARCHY_SPACES['dash'] * ph.FORM_SIZES_PT['dash'] / 2:.2f}pt" in cell
    doc, _ = rr.render(DRAFT)
    assert 'text-indent:0;width:37.50pt' in doc or 'text-indent:0;width:39.47pt' in doc   # 대시(장평 95 보정 포함)


def test_review_table_draws_merges_like_hwpx():
    html = rr.render_table([["성과지표", "'23년 > 목표", "'23년 > 실적"], ["**건수**", "1", "2"], ["〃", "3", "4"]])
    assert '<th rowspan="2">성과지표</th><th colspan="2">’23년</th>' in html      # 따옴표는 한글처럼 둥글게
    assert '<td class="lab" rowspan="2"><b>건수</b></td>' in html and "〃" not in html


def test_two_column_table_gets_label_column_like_hwpx():
    """kordoc은 2열 표의 첫 열을 스스로 굵게 해 후처리가 라벨 열로 칠한다 — 리뷰도 같게('26.9.24 시험 변환)."""
    two = rr.render_table([["구 분", "지시 내용"], ["역 할", "추출만 한다"], ["금 지", "원본 수정"]])
    assert two.count('<td class="lab">') == 2
    three = rr.render_table([["구 분", "확인 결과", "적용 기준"], ["추출", "공란", "처방"]])
    assert 'class="lab"' not in three


def test_quotes_become_curly_like_kordoc():
    """kordoc은 곧은따옴표를 둥글게 바꾼다 — 화면과 줄 수 계산 모두 둥근따옴표로('26.9.24)."""
    assert rr.curly("'25년 '표준 로그' \"값\"") == "’25년 ‘표준 로그’ “값”"
    assert rr.fit_style("dash", "'26" * 30)[0] != rr.fit_style("dash", "026" * 30)[0]   # 전각으로 재면 더 조인다


def test_title_box_draws_24pt_one_line_fit():
    """리뷰 제목도 후처리 fit_title과 같은 장평·자간으로 한 줄에 그린다."""
    doc, _ = rr.render("AI 도입 전후 효과 분석 체계 마련 방안 요약 보고\n\n□ 개 요\n")
    r, sp, over = ph.fit_title("AI 도입 전후 효과 분석 체계 마련 방안 요약 보고", ph.TITLE_TEXT_WIDTH_HU / 100)
    assert f"transform:scaleX({r / 100:g})" in doc and "white-space:nowrap" in doc and "font-size:24pt" in doc


def test_header_banner_matches_hwpx_header():
    """머리말 배너(로고·슬로건) — hwpx 머리말과 같은 그림·크기(본문 폭 맞춤 배율 적용)로 쪽 위 여백에 그린다('26.9.24)."""
    c = rr.header_banner_css()
    assert ".page::before" in c and "data:image/png;base64," in c and "data:image/bmp;base64," in c
    assert "width:476.25pt" in c                                   # 시험 변환 실측 표 47625 HWPUNIT
    assert "134.37pt 17.88pt" in c and "95.87pt 25.56pt" in c     # 로고·슬로건 13437×1788 · 9587×2556
    doc, _ = rr.render(DRAFT)
    assert ".page::before" in doc


# '26.9.25 하네스 실전 점검 3회차(가상 자료)의 실제 kordoc 변환 초안 — 후처리 estimate_layout이 인도본에서
# 698pt·1쪽·문단 21줄·표 행 9개로 보고했다. 초안 쪽 추정은 같은 식이라 같은 값이어야 한다.
REAL_CONVERTED = """AI 초안 도우미 시범운영 결과와 확대 조건 보고

< '26. 9. 25.(금), OO본부 OO팀 >

□ 개 요

 ㅇ **(시범운영 결과)** 'AI 문서 초안 도우미'가 검수를 포함해도 보도자료 1건당 작성시간을 45분 줄였으나, 개인정보 입력 차단 기능을 갖춘 뒤 확대 필요
   - '26.7월 ~ 8월 3개 부서 42명이 초안 1,260건(1인당 월평균 15건)을 생성했으며, 사용료는 월 180만 원(총 360만 원) 소요

□ 추진 성과

 ㅇ **(작성시간 절감)** 검수시간을 더해도 보도자료 1건당 45분이 줄었고, 설문 응답자의 81%가 **계속 사용을 희망**해 현업 수용성 확인

[ 시범운영 실측 결과 ]

| 구 분 | 결 과 | 측정 기준 |
|---|---|---|
| **작성 시간** | 보도자료 초안 95분 → 38분(60% 단축) | 20건 표본 실측 |
| **순절감 시간** | 건당 45분 | 검수 12분 추가 반영 |
| **이용 만족도** | 계속 사용 희망 30명(81%) | 설문 응답 37명 |
| **초안 오류** | 수치·인용 오류 7건 | 초안 100건 중, 검수에서 전량 수정 |

※ 작성시간은 보도자료 20건 표본 실측값으로, 다른 문서 유형은 별도 측정 필요

□ 검토 결과

 ㅇ **(확대 대상 문서)** 시범 부서 의견대로 효과가 큰 회의록·결과보고 등 반복 문서부터 확대하고, 효과가 작은 정책 판단 문서는 후순위로 조정
 ㅇ **(개인정보 보호)** 도우미에 개인정보 입력을 막는 기능이 없어, 이용자가 늘기 전에 차단 기능을 먼저 도입 필요
 ㅇ **(초안 검수 유지)** 수치·인용 오류(초안 100건 중 7건)가 검수 단계에서 모두 수정된 만큼, 확대 후에도 검수를 필수 절차로 유지

□ 향후 계획

 ㅇ **(경영회의 상정)** 확대 인원 기준 사용료와 차단 기능 도입 방식을 산정해 '26.10월 경영회의에 전사 확대와 차단 기능 도입을 안건으로 상정
"""


def test_draft_estimate_matches_postprocess_on_a_real_conversion():
    """리뷰 서버 없이도 게이트② 전에 예상 쪽수를 본다 — 변환 뒤 후처리가 보고하는 값과 같은 식(실측 짝 대조)."""
    e = rr.estimate_layout(rr.parse(REAL_CONVERTED))
    assert (e["est_pt"], e["est_pages"], e["paragraph_lines"], e["table_rows"]) == (698, 1, 21, 9)


def test_draft_estimate_tracks_postprocess_on_generated_hwpx(tmp_path):
    """웹앱 생성기(md2hwpx)로 만든 hwpx의 후처리 추정과 쪽수가 같고, 차이는 두 줄(48pt) 이내다."""
    import re as _re
    root = pathlib.Path(__file__).resolve().parents[1]
    fixture = _re.search(r'FIXTURE = """(.*?)"""', (root / "tests/test_md2hwpx.py").read_text(encoding="utf-8"), _re.S).group(1)
    web = root / "webapp/kca-report-hwpx/scripts"
    (tmp_path / "draft.md").write_text(fixture, encoding="utf-8")
    run = lambda *a: subprocess.run([sys.executable, *map(str, a)], capture_output=True, text=True)
    assert run(web / "prep_report_md.py", tmp_path / "draft.md", "-o", tmp_path / "p.md").returncode == 0
    assert run(web / "md2hwpx.py", tmp_path / "p.md", "-o", tmp_path / "o.hwpx").returncode == 0
    real = json.loads(run(web / "postprocess_hwpx.py", tmp_path / "o.hwpx", "--all").stdout)["layout"]
    est = rr.estimate_layout(rr.parse((tmp_path / "p.md").read_text(encoding="utf-8")))
    assert est["est_pages"] == real["est_pages"] and est["pages_by_part"] == real["pages_by_part"]
    assert abs(est["est_pt"] - real["est_pt"]) <= 48, (est["est_pt"], real["est_pt"])


def test_render_cli_reports_estimated_pages(tmp_path, capsys):
    """render_review_html CLI 출력에 예상 쪽수가 있다 — SKILL 게이트②가 게이트⓪ 분량과 대조한다."""
    d = tmp_path / "20_draft.md"
    d.write_text(REAL_CONVERTED, encoding="utf-8")
    assert rr.main([str(d), "-o", str(tmp_path / "r.html")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["est_pages"] == 1 and out["pages_by_part"] == [1]
