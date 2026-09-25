import sys, pathlib, zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
from validate_hwpx import (structural_check, profile_counts, compare_texts,
                           content_pieces, freshness_check)

MIMETYPE = b"application/hwp+zip"

def make_zip(tmp_path, xml=b"<?xml version='1.0'?><root/>", *,
             mimetype=MIMETYPE, mimetype_stored=True, mimetype_first=True,
             with_version=True, with_dirs=False):
    """한컴 정본 최소 패키지. 키워드로 반입 거부 유형을 재현한다."""
    p = tmp_path / "t.hwpx"
    with zipfile.ZipFile(p, "w") as z:
        def put_mimetype():
            zi = zipfile.ZipInfo("mimetype")
            zi.compress_type = zipfile.ZIP_STORED if mimetype_stored else zipfile.ZIP_DEFLATED
            z.writestr(zi, mimetype)
        if mimetype_first:
            put_mimetype()
        if with_version:
            z.writestr("version.xml", "<?xml version='1.0'?><hv:HCFVersion xmlns:hv='http://www.hancom.co.kr/hwpml/2011/version'/>")
        if with_dirs:
            z.writestr(zipfile.ZipInfo("Contents/"), b"")
        z.writestr("META-INF/container.xml", "<container/>")
        z.writestr("Contents/content.hpf", "<opf:package xmlns:opf='x'/>")
        z.writestr("Contents/header.xml", "<?xml version='1.0'?><root/>")
        z.writestr("Contents/section0.xml", xml)
        if not mimetype_first:
            put_mimetype()
    return p

def test_structural_ok(tmp_path):
    assert structural_check(make_zip(tmp_path)) == []

def test_structural_broken_xml(tmp_path):
    errs = structural_check(make_zip(tmp_path, b"<root><unclosed>"))
    assert errs and "section0.xml" in errs[0]

# --- 반입 판별(OCF·패키지) 회귀 — '26.7.29 내부망 자료교환 반입 거부 건 ---

def test_structural_missing_version_xml(tmp_path):
    errs = structural_check(make_zip(tmp_path, with_version=False))
    assert any("version.xml" in e for e in errs)

def test_structural_mimetype_deflated(tmp_path):
    errs = structural_check(make_zip(tmp_path, mimetype_stored=False))
    assert any("STORED" in e for e in errs)

def test_structural_mimetype_not_first(tmp_path):
    errs = structural_check(make_zip(tmp_path, mimetype_first=False))
    assert any("first entry" in e for e in errs)

def test_structural_wrong_mimetype_content(tmp_path):
    errs = structural_check(make_zip(tmp_path, mimetype=b"application/epub+zip"))
    assert any("application/hwp+zip" in e for e in errs)

def test_structural_directory_entries(tmp_path):
    errs = structural_check(make_zip(tmp_path, with_dirs=True))
    assert any("directory" in e for e in errs)

def test_profile_counts():
    c = profile_counts("□ A\n ㅇ b 137명(23.7%)\n   - c\n＊ 각주\n| a | b |\n|---|---|\n")
    assert c["sections"] == 1 and c["points"] == 1 and c["subs"] == 1
    assert c["footnotes"] == 1 and c["tables"] == 1
    assert "137" in c["numbers"] and "23.7" in c["numbers"]

def test_compare_detects_lost_number_and_leftover():
    src = "□ A\n ㅇ 총 502건 정비\n"
    rt = "□ A\n ㅇ 총 **502**건 정비 - 그대로 노출\n"   # 볼드 기호·인라인 대시 잔재
    issues = {i["rule"] for i in compare_texts(src, rt)}
    assert "markdown-leftover" in issues

def test_compare_ok_when_identical():
    src = "□ A\n ㅇ 총 502건 정비\n"
    assert compare_texts(src, src) == []

def test_max_cols_loss_detected():         # 표 컬럼 유실 검출 (스펙 누락 보완)
    src = "| 구분 | 사업명 | 담당부서 |\n|---|---|---|\n| 1 | AI플랫폼 | 정보화기획팀 |\n"
    rt  = "| 구분 | 사업명 |\n|---|---|\n| 1 | AI플랫폼 |\n"
    assert any(i["rule"] == "count-mismatch:max_cols" for i in compare_texts(src, rt))

def test_backtick_leftover_detected():
    issues = compare_texts("ㅇ 코드 사용법\n", "ㅇ `코드` 사용법\n")
    assert any(i["rule"] == "markdown-leftover" for i in issues)

def test_double_hash_leftover_detected():
    issues = compare_texts("소제목\n", "## 소제목\n")
    assert any(i["rule"] == "markdown-leftover" for i in issues)

def test_hr_leftover_detected():
    issues = compare_texts("□ 제목\nㅇ 내용\n", "□ 제목\nㅇ 내용\n---\n")
    assert any(i["rule"] == "markdown-leftover" for i in issues)

def test_italic_strike_leftover_detected():
    assert any(i["rule"] == "markdown-leftover" for i in compare_texts("ㅇ 강조 문구\n", "ㅇ *강조* 문구\n"))
    assert any(i["rule"] == "markdown-leftover" for i in compare_texts("ㅇ 삭제 문구\n", "ㅇ ~~삭제~~ 문구\n"))

def test_number_reformat_not_lost():       # 표기 정규화는 손실 아님 (오탐 제거)
    assert compare_texts("ㅇ 예산 1,234백만원 편성\n", "ㅇ 예산 1234백만원 편성\n") == []
    assert compare_texts("ㅇ 비율 23.70%\n", "ㅇ 비율 23.7%\n") == []

def test_real_number_loss_still_detected():
    issues = compare_texts("ㅇ 총 502건 정비, 137명 참여\n", "ㅇ 총 502건 정비\n")
    assert any(i["rule"] == "numbers-lost" and "137" in str(i["values"]) for i in issues)

def test_cli_missing_args_exit2(tmp_path):
    import subprocess, sys as _sys
    r = subprocess.run([_sys.executable, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts/validate_hwpx.py"), "compare"], capture_output=True)
    assert r.returncode == 2

def test_numbers_mode_flags_unsourced(tmp_path):
    from validate_hwpx import numbers_check
    draft = "ㅇ 예산 349,850,000원, 참여 137명(23.7%)\n"
    rdir = tmp_path / "research"; rdir.mkdir()
    (rdir / "a.md").write_text("계약금액 349850000원 규모")   # 349,850,000 근거 있음(정규화 일치)
    issues = numbers_check(draft, rdir)
    vals = {v for i in issues for v in i["values"]}
    assert "137" in vals and "23.7" in vals          # 근거 없는 수치만 잔존
    assert not any("349" in v for v in vals)

def test_numbers_mode_clean(tmp_path):
    from validate_hwpx import numbers_check
    rdir = tmp_path / "research"; rdir.mkdir()
    (rdir / "a.jsonl").write_text('{"t":"137명 참여, 비율 23.70%"}')
    assert numbers_check("ㅇ 137명(23.7%)\n", rdir) == []

def test_numbers_mode_ignores_korean_dates(tmp_path):
    from validate_hwpx import numbers_check
    rdir = tmp_path / "research"; rdir.mkdir()
    draft = "ㅇ 시행 : '26.7월 / 기간 '26. 1. 13(화) ~ 1. 23(금) / 정비 502건\n"
    issues = numbers_check(draft, rdir)
    vals = {v for i in issues for v in i["values"]}
    assert "26.7" not in vals and "26.1" not in vals   # 날짜 표기는 수치 아님
    assert "502" in vals                                # 실수치는 검출 유지

def test_highlight_marker_leftover_detected():   # R040: 되읽기에 == 마커 잔존 시 검출
    issues = compare_texts("ㅇ 핵심 강조 문구\n", "ㅇ 핵심 ==강조== 문구\n")
    assert any(i["rule"] == "markdown-leftover" for i in issues)


# --- 문장 단위 대조 ('26.9.10 신설) ------------------------------------------
# 종전 compare는 개수(sections·points·subs·footnotes·tables·max_cols)·수치 집합·
# 마크다운 잔재만 봤다 — 문장이 통째로 갈려도 총량과 수치가 맞으면 통과했다.

def test_compare_detects_swapped_sentence():
    """개수·수치가 모두 같은데 문장만 바뀐 경우를 잡는다."""
    src = "□ 개 요\n ㅇ (조사 결론) 공통 번호가 없어 기관 간 연계가 끊긴 상태\n"
    rt = "□ 개 요\n ㅇ (조사 결론) 담당자 면담으로 연계 경로를 확인한 상태\n"
    a = {i["rule"] for i in compare_texts(src, src)}
    b = [i for i in compare_texts(src, rt) if i["rule"] == "content-dropped"]
    assert not a
    assert b and b[0]["count"] == 1


def test_compare_ignores_lead_symbol_mapping():
    """마크다운 `- `가 개조식 `ㅇ `·`□ `로 바뀌는 것은 손실이 아니다.

    변환 규약 자체가 그 매핑이라, 선두 기호를 그대로 대조하면 정상 변환이 전량
    '소실'로 뒤집힌다('26.9.10 실측 — 인도 4건에서 문장 100%가 오탐)."""
    src = "- 개 요\n- (조사 범위) 자료 목록 23종을 대조\n"
    rt = "□ 개 요\nㅇ (조사 범위) 자료 목록 23종을 대조\n"
    assert not [i for i in compare_texts(src, rt) if i["rule"] == "content-dropped"]


def test_compare_ignores_readback_escapes():
    """되읽기가 붙이는 `\\~` 이스케이프는 손실이 아니다.

    실측에서 이 잡음 하나로 멀쩡한 문장 47조각이 소실로 잡혔다."""
    src = " ㅇ 결제 후 3 ~ 5개월 소요\n"
    rt = " ㅇ 결제 후 3 \\~ 5개월 소요\n"
    assert not [i for i in compare_texts(src, rt) if i["rule"] == "content-dropped"]


def test_content_pieces_flattens_table_cells():
    pieces = content_pieces("| 구 분 | 내 용 |\n| --- | --- |\n| 도입 | 절차 점검 |\n")
    assert pieces == ["구 분", "내 용", "도입", "절차 점검"]


# --- 산출물 신선도 ('26.9.10 신설) -------------------------------------------

def test_freshness_detects_stale_prepared():
    """초안을 고치고 재변환을 안 하면 인도본이 조용히 낡는다 — 그 상태를 잡는다.

    실측('26.9.10): 인도 건 4개 중 3개에서 20_draft가 40_prepared보다 최신이었고
    본문 수치까지 달랐다(초안 `16건` vs 인도본 `17건`)."""
    draft = "□ 개 요\n\n ㅇ (조사 결론) 대상 16건을 대조\n"
    prepared = "□ 개 요\n\n ㅇ (조사 결론) 대상 17건을 대조\n"
    issues = freshness_check(draft, prepared)
    assert issues and issues[0]["rule"] == "prepared-stale"
    assert issues[0]["drifted"] == 1


def test_freshness_clean_when_prepared_matches_draft():
    draft = "□ 개 요\n\n ㅇ (조사 결론) 대상 16건을 대조\n"
    assert freshness_check(draft, draft) == []


def test_freshness_ignores_prep_normalization():
    """prep이 지우는 단일행 HTML 주석은 어긋남이 아니다 — prep을 다시 태워 비교한다."""
    draft = "<!-- 작업 메모 -->\n□ 개 요\n\n ㅇ (조사 결론) 대상 16건을 대조\n"
    prepared = "□ 개 요\n\n ㅇ (조사 결론) 대상 16건을 대조\n"
    assert freshness_check(draft, prepared) == []


def test_compare_accepts_merged_table_roundtrip():
    """병합 표는 되읽기가 HTML <table>로 준다 — 초안의 `A > B`·`〃` 표기와 맞춰 센다('26.9.24)."""
    import validate_hwpx as vh
    src = "| 성과지표 | '23년 > 목표 | '23년 > 실적 |\n| --- | --- | --- |\n| 건수 | 100 | 120 |\n| 〃 | 50 | 60 |\n"
    rt = ('<table>\n<tr><th rowspan="2">성과지표</th><th colspan="2">\'23년</th></tr>\n<tr><td>목표</td><td>실적</td></tr>\n'
          '<tr><td rowspan="2">건수</td><td>100</td><td>120</td></tr>\n<tr><td>50</td><td>60</td></tr>\n</table>\n')
    assert vh.compare_texts(src, rt) == []


# ---------------------------------------------------------------- 되읽기 오탐 제거 ('26.9.25 — 같은 오탐 5회 반복)
TITLE_SRC = "AI 성과 측정 체계 마련 방안\n\n< '26. 9. 24.(목), 경영기획본부 AI디지털심화팀 >\n\n□ 개 요\n\nㅇ **(측정 기준)** 18건을 4개 유형으로 분류\n"


def _rules(issues):
    return [i["rule"] for i in issues]


def test_readback_bold_and_title_heading_are_not_leftovers():
    """되읽기는 글자 모양 볼드를 `**…**`로, 제목 박스를 `# 제목`으로 돌려준다 — 원문과 같으면 잔재가 아니다."""
    rt = ("# AI 성과 측정 체계 마련 방안\n\n< ’26. 9. 24.(목), 경영기획본부 AI디지털심화팀 >\n\n□ 개 요\n\n"
          "ㅇ **(측정 기준)** 18건을 4개 유형으로 분류\n")
    assert compare_texts(TITLE_SRC, rt) == []                          # 볼드·제목·굽은 따옴표 모두 무해


def test_real_leftovers_still_caught():
    assert "markdown-leftover" in _rules(compare_texts(TITLE_SRC, TITLE_SRC.replace("**(측정 기준)**", "**(측정 기준)")))
    other = "# 다른 제목\n" + TITLE_SRC.split("\n", 1)[1]
    assert "markdown-leftover" in _rules(compare_texts(TITLE_SRC, other))      # 원문 제목과 다른 헤딩


def test_inline_dash_allowed_only_when_source_has_it():
    src = "□ 산식\n\n| 개선율 = (도입 전 - 도입 후) ÷ 도입 전 × 100 |\n| --- |\n"
    rt = "□ 산식\n\n개선율 = (도입 전 - 도입 후) ÷ 도입 전 × 100\n"             # 1칸 상자가 문단으로 되읽힘
    assert compare_texts(src, rt) == []                                # 표 수·잔재·문장 모두 무해
    assert "markdown-leftover" in _rules(compare_texts("ㅇ 총 502건 정비\n", "ㅇ 총 502건 정비 - 그대로 노출\n"))


def test_readback_preamble_block_is_not_body():
    """MCP 되읽기 머리의 `📑 문서 구조:` 목록은 본문 대시가 아니다('26.9.3 count-mismatch:subs 오탐)."""
    rt = "📑 문서 구조:\n- AI 성과 측정 체계 마련 방안\n\n" + TITLE_SRC
    assert compare_texts(TITLE_SRC, rt) == []
    assert profile_counts(rt)["subs"] == profile_counts(TITLE_SRC)["subs"]


def test_literal_markup_counts_marks_left_in_hwpx(tmp_path):
    """되읽기의 `**`는 볼드 재직렬화일 수 있어 hwpx 글자에 기호가 문자로 남았는지는 XML에서 직접 센다."""
    import validate_hwpx as vh
    hp = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    xml = (f"<?xml version='1.0'?><hs:sec xmlns:hs='x' xmlns:hp='{hp}'><hp:p><hp:run><hp:t>정상 문장</hp:t></hp:run></hp:p>"
           f"<hp:p><hp:run><hp:t>**남은 기호** 문장</hp:t></hp:run></hp:p></hs:sec>").encode()
    issues = vh.literal_markup(make_zip(tmp_path, xml))
    assert [(i["rule"], i["mark"], i["count"]) for i in issues] == [("literal-markup", "**", 1)]
    clean = f"<?xml version='1.0'?><hs:sec xmlns:hs='x' xmlns:hp='{hp}'><hp:p><hp:run><hp:t>정상</hp:t></hp:run></hp:p></hs:sec>"
    assert vh.literal_markup(make_zip(tmp_path, clean.encode())) == []


def test_literal_markup_ignores_verbatim_quote_block_text(tmp_path):
    """원문 인용 블록(```text)은 원문 그대로라 백틱 등이 있어도 잔재가 아니다('26.9.25 실변환 — 지시문 원문 백틱 2건)."""
    import validate_hwpx as vh
    src = "□ 붙임\n\n```text\n⁠- 11번째 열부터는 `원시_` 접두어를 붙인다\n```\n"
    hp = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    xml = (f"<?xml version='1.0'?><hs:sec xmlns:hs='x' xmlns:hp='{hp}'><hp:p><hp:run>"
           f"<hp:t>- 11번째 열부터는 `원시_` 접두어를 붙인다</hp:t></hp:run></hp:p></hs:sec>").encode()
    path = make_zip(tmp_path, xml)
    assert vh.literal_markup(path) != []                                  # 인용 줄을 모르면 잡는다
    assert vh.literal_markup(path, vh.quote_texts(src)) == []             # 원문 인용 줄이면 뺀다


def test_short_quote_line_does_not_exempt_other_text(tmp_path):
    """인용 줄이 짧아도(예: '1') 그 글자를 포함한 다른 문단의 잔재까지 면제하지 않는다('26.9.25 코드 리뷰)."""
    import validate_hwpx as vh
    src = "□ 붙임\n\n```text\n1\n```\n"
    hp = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    xml = (f"<?xml version='1.0'?><hs:sec xmlns:hs='x' xmlns:hp='{hp}'><hp:p><hp:run>"
           f"<hp:t>**남은 기호** 문장 1</hp:t></hp:run></hp:p></hs:sec>").encode()
    assert [i["mark"] for i in vh.literal_markup(make_zip(tmp_path, xml), vh.quote_texts(src))] == ["**"]


def test_marks_only_fragment_is_not_exempted_by_quote_line(tmp_path):
    """기호만 따로 떨어진 <hp:t>(`**`)는 인용 줄에 같은 기호가 있어도 잔재다 — 기호뿐인 조각은 어느 인용 줄과도
    겹쳐 보인다('26.9.25 코드 리뷰 #2)."""
    import validate_hwpx as vh
    src = "□ 붙임\n\n```text\n원문에 **굵게** 표기가 있다\n```\n"
    hp = "http://www.hancom.co.kr/hwpml/2011/paragraph"
    xml = (f"<?xml version='1.0'?><hs:sec xmlns:hs='x' xmlns:hp='{hp}'><hp:p><hp:run>"
           f"<hp:t>**</hp:t></hp:run><hp:run><hp:t>본문 강조</hp:t></hp:run></hp:p></hs:sec>").encode()
    assert [i["mark"] for i in vh.literal_markup(make_zip(tmp_path, xml), vh.quote_texts(src))] == ["**"]


def test_quote_line_inside_longer_run_only_exempts_the_quote(tmp_path):
    """인용 줄 + 본문이 한 <hp:t>에 들면 인용 부분만 빼고 나머지 잔재를 본다."""
    import validate_hwpx as vh
    src = "□ 붙임\n\n```text\n열 이름은 `원시_` 접두어\n```\n"
    hp = "http://www.hancom.co.kr/hwpml/2011/paragraph"

    def run(text):
        return make_zip(tmp_path, (f"<?xml version='1.0'?><hs:sec xmlns:hs='x' xmlns:hp='{hp}'><hp:p><hp:run>"
                                   f"<hp:t>{text}</hp:t></hp:run></hp:p></hs:sec>").encode())
    allowed = vh.quote_texts(src)
    assert vh.literal_markup(run("열 이름은 `원시_` 접두어 — 설명 문장"), allowed) == []
    assert [i["mark"] for i in vh.literal_markup(run("열 이름은 `원시_` 접두어 — **잔재**"), allowed)] == ["**"]


def test_blank_table_dropped_in_conversion_is_reported():
    """글자 없는 표(서명란)는 표 수와 따로 센다 — 되읽기에 느는 빈 표(머리말 배너)는 잡음이지만 원본의 빈 표가
    빠진 것은 손실이다('26.9.25 코드 리뷰 #2)."""
    body = "□ 개요\n\nㅇ 결재 서명란\n\n"
    blank = "| | |\n|---|---|\n| | |\n\n"
    src = body + blank
    assert profile_counts(src)["blank_tables"] == 1 and profile_counts(src)["tables"] == 0
    assert any(i["rule"] == "count-mismatch:blank_tables" for i in compare_texts(src, body))
    assert not any("tables" in i["rule"] for i in compare_texts(body, body + blank))   # 되읽기에만 느는 빈 표는 보지 않는다
