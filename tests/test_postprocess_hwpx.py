import sys, pathlib, zipfile, io, re, json
import xml.etree.ElementTree as ET
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import postprocess_hwpx as ph

NS = ph.NS

HEADER_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hh:head xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" version="1.4" secCnt="1">
  <hh:refList>
    <hh:fontfaces itemCnt="1">
      <hh:fontface lang="HANGUL" fontCnt="2">
        <hh:font id="0" face="휴먼명조" type="TTF" isEmbedded="0"/>
        <hh:font id="1" face="맑은고딕" type="TTF" isEmbedded="0"/>
      </hh:fontface>
    </hh:fontfaces>
    <hh:borderFills itemCnt="2">
      <hh:borderFill id="1" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">
        <hh:slash type="NONE" Crooked="0" isCounter="0"/>
        <hh:backSlash type="NONE" Crooked="0" isCounter="0"/>
        <hh:leftBorder type="SOLID" width="0.12 mm" color="#000000"/>
        <hh:rightBorder type="SOLID" width="0.12 mm" color="#000000"/>
        <hh:topBorder type="SOLID" width="0.12 mm" color="#000000"/>
        <hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000"/>
      </hh:borderFill>
      <hh:borderFill id="2" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">
        <hh:slash type="NONE" Crooked="0" isCounter="0"/>
        <hh:backSlash type="NONE" Crooked="0" isCounter="0"/>
        <hh:leftBorder type="NONE" width="0.1 mm" color="#000000"/>
        <hh:rightBorder type="NONE" width="0.1 mm" color="#000000"/>
        <hh:topBorder type="NONE" width="0.1 mm" color="#000000"/>
        <hh:bottomBorder type="NONE" width="0.1 mm" color="#000000"/>
      </hh:borderFill>
    </hh:borderFills>
    <hh:charProperties itemCnt="2">
      <hh:charPr id="0" height="1500" textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="1">
        <hh:fontRef hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>
        <hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>
        <hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>
        <hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>
        <hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>
      </hh:charPr>
      <hh:charPr id="1" height="1300" textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="1">
        <hh:fontRef hangul="1" latin="1" hanja="1" japanese="1" other="1" symbol="1" user="1"/>
        <hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>
        <hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>
        <hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>
        <hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>
      </hh:charPr>
    </hh:charProperties>
    <hh:paraProperties itemCnt="1">
      <hh:paraPr id="0" tabPrIDRef="0" condense="0" fontLineHeight="0" snapToGrid="0" suppressLineNumbers="0" checked="0" textDir="AUTO">
        <hh:align horizontal="JUSTIFY" vertical="BASELINE"/>
        <hh:heading type="NONE" idRef="0" level="0"/>
        <hh:breakSetting breakLatinWord="KEEP_WORD" breakNonLatinWord="BREAK_WORD" widowOrphan="0" keepWithNext="0" keepLines="0" pageBreakBefore="0" lineWrap="BREAK"/>
        <hh:autoSpacing eAsianEng="0" eAsianNum="0"/>
        <hh:margin>
          <hc:intent value="0" unit="HWPUNIT"/>
          <hc:left value="0" unit="HWPUNIT"/>
          <hc:right value="0" unit="HWPUNIT"/>
          <hc:prev value="0" unit="HWPUNIT"/>
          <hc:next value="0" unit="HWPUNIT"/>
        </hh:margin>
        <hh:lineSpacing type="PERCENT" value="160"/>
        <hh:border borderFillIDRef="1" offsetLeft="0" offsetRight="0" offsetTop="0" offsetBottom="0" connect="0" ignoreMargin="0"/>
      </hh:paraPr>
    </hh:paraProperties>
  </hh:refList>
</hh:head>
"""

# 시나리오: 발신줄 → □1 → ㅇ1 → -1 → ＊1(본문 charPr, 치환 대상) → 캡션 → 표(＊→캡션 간
# 스페이서 삽입 검증) → (기존 빈 문단, 표→□ 전환 modify 검증) → □2 → ㅇ2 → □3(ㅇ→□ 블록
# 구분 insert 검증)
SECTION_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>&lt; '26. 1. 1.(목), 테스트팀 &gt;</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 제목1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 요지1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>- 상세1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>＊ 각주1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>[ 표 제목 ]</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:tbl id="1" rowCnt="1" colCnt="1"><hp:tr><hp:tc><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>셀</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t/></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 제목2</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 요지2</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 제목3</hp:t></hp:run></hp:p>
</hs:sec>
"""

MIMETYPE = b"application/hwp+zip"


def build_hwpx(path, header_xml=HEADER_XML, section_xml=SECTION_XML):
    with zipfile.ZipFile(path, "w") as z:
        zi = zipfile.ZipInfo("mimetype")
        zi.compress_type = zipfile.ZIP_STORED
        z.writestr(zi, MIMETYPE)
        z.writestr("META-INF/container.xml", "<container/>")
        z.writestr("Contents/content.hpf", "<opf:package xmlns:opf='x'/>")
        z.writestr("Contents/header.xml", header_xml)
        z.writestr("Contents/section0.xml", section_xml)
    return path


def build_kordoc_like(path, header_xml=HEADER_XML, section_xml=SECTION_XML):
    """kordoc generate_document 실산출 레이아웃 재현('26.7.29 실측) —
    디렉터리 엔트리 3개·version.xml 등 필수 멤버 부재·전량 STORED."""
    container = ('<ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container">'
                 '<ocf:rootfiles><ocf:rootfile full-path="Contents/content.hpf" '
                 'media-type="application/hwpml-package+xml"/></ocf:rootfiles></ocf:container>')
    hpf = ('<opf:package xmlns:opf="http://www.idpf.org/2007/opf/"><opf:manifest>'
           '<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>'
           '<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>'
           '</opf:manifest><opf:spine><opf:itemref idref="header" linear="no"/>'
           '<opf:itemref idref="section0" linear="yes"/></opf:spine></opf:package>')
    with zipfile.ZipFile(path, "w") as z:
        zi = zipfile.ZipInfo("mimetype")
        zi.compress_type = zipfile.ZIP_STORED
        z.writestr(zi, MIMETYPE)
        for d in ("META-INF/", "Contents/", "Preview/"):
            z.writestr(zipfile.ZipInfo(d), b"")
        z.writestr("META-INF/container.xml", container)
        z.writestr("Contents/content.hpf", hpf)
        z.writestr("Contents/header.xml", header_xml)
        z.writestr("Contents/section0.xml", section_xml)
        z.writestr("Preview/PrvText.txt", "반입 테스트")
    return path


def all_text_and_ids(section_xml_bytes):
    """비파괴 검증용: 텍스트가 있는 문단의 (텍스트, charPrIDRef) 목록만 추린다(스페이서 제외)."""
    root = ET.fromstring(section_xml_bytes)
    out = []
    for p in root.iter(ph.qn("hp", "p")):
        for run in p.findall(ph.qn("hp", "run")):
            t = run.find(ph.qn("hp", "t"))
            if t is not None and t.text:
                out.append((t.text, run.get("charPrIDRef")))
    return out


@pytest.fixture
def hwpx_file(tmp_path):
    p = tmp_path / "sample.hwpx"
    build_hwpx(str(p))
    return p


def test_classify_symbols():
    mkp = lambda text: ET.fromstring(
        f'<hp:p xmlns:hp="{NS["hp"]}" paraPrIDRef="0"><hp:run charPrIDRef="0"><hp:t>{text}</hp:t></hp:run></hp:p>'
    )
    assert ph.classify(mkp("□ 제목")) == "dae"
    assert ph.classify(mkp("ㅇ 요지")) == "yo"
    assert ph.classify(mkp("- 상세")) == "dash"
    assert ph.classify(mkp("＊ 각주")) == "star"
    assert ph.classify(mkp("※ 참조")) == "cham"
    assert ph.classify(mkp("&lt; '26. 1. 1.(목), 팀 &gt;")) == "sending"
    assert ph.classify(mkp("[ 표 제목 ]")) == "caption"


def test_transition_lookup_values():
    assert ph.transition_for("sending", "dae") == ("sending_to_dae", 1200)
    assert ph.transition_for("dae", "yo") == ("dae_to_yo", 600)
    assert ph.transition_for("yo", "dash") == ("yo_to_dash", 300)   # R013 정정 '26.9.10
    assert ph.transition_for("dash", "star") == ("dash_to_star", 300)
    assert ph.transition_for("star", "caption") == ("star_to_caption", 1000)
    assert ph.transition_for("yo", "dae") == ("block_boundary", 800)
    assert ph.transition_for("table", "dae") == ("block_boundary", 800)
    assert ph.transition_for("yo", "yo") == ("yo_to_yo", 600)  # 사용자 확정('26.7.22): 연속 ㅇ 6pt
    assert ph.transition_for("dash", "dash") is None


# --- ①＊ 치환 -----------------------------------------------------------

def test_star_footnote_replaces_charpr(hwpx_file):
    summary = ph.process_file(str(hwpx_file), star=True, spacing=False)
    assert summary["star_footnote"]["ref_charpr_id"] == "1"
    assert summary["star_footnote"]["stars_found"] == 1
    assert summary["star_footnote"]["runs_changed"] == 1
    with zipfile.ZipFile(hwpx_file) as z:
        sec = z.read("Contents/section0.xml")
    pairs = dict(all_text_and_ids(sec))
    assert pairs["＊ 각주1"] == "1"


def test_star_footnote_idempotent(hwpx_file):
    ph.process_file(str(hwpx_file), star=True, spacing=False)
    summary2 = ph.process_file(str(hwpx_file), star=True, spacing=False)
    assert summary2["star_footnote"]["stars_found"] == 1
    assert summary2["star_footnote"]["runs_changed"] == 0  # 이미 치환됨 — 재실행 안전


def test_star_footnote_missing_ref_raises(tmp_path):
    header_no_ref = HEADER_XML.replace(
        '<hh:font id="1" face="맑은고딕" type="TTF" isEmbedded="0"/>',
        '<hh:font id="1" face="휴먼명조" type="TTF" isEmbedded="0"/>',
    )
    p = tmp_path / "noref.hwpx"
    build_hwpx(str(p), header_xml=header_no_ref)
    with pytest.raises(ph.PostprocessError):
        ph.process_file(str(p), star=True, spacing=False)


def test_star_footnote_skips_when_no_targets(tmp_path):
    """＊ 문단이 없으면 참고 charPr이 없어도 중단하지 않고 뒤 단계가 이어진다.

    회귀 대상: 기관 서식 채움본(TASK-11 v6 — ＊ 0건, 13pt 글꼴이 맑은고딕이 아님)에서
    이 전제 실패가 예외로 터져 `--all`의 **모든 뒤 단계가 무적용**됐다. 표 폭 정합
    (R036·R042)과 패키지 정합(R043)까지 건너뛰므로 반입 가능성에도 영향이 간다."""
    header_no_ref = HEADER_XML.replace(
        '<hh:font id="1" face="맑은고딕" type="TTF" isEmbedded="0"/>',
        '<hh:font id="1" face="휴먼명조" type="TTF" isEmbedded="0"/>',
    )
    section_no_star = SECTION_XML.replace("＊", "·")
    p = tmp_path / "nostar.hwpx"
    build_hwpx(str(p), header_xml=header_no_ref, section_xml=section_no_star)
    summary = ph.process_file(str(p), star=True, spacing=True)
    assert summary["star_footnote"]["skipped"] == "no_star_targets"
    assert summary["star_footnote"]["stars_found"] == 0
    # 뒤 단계가 실제로 돌았다 — 패키지 정합이 보고에 잡힌다
    assert "package_canonical" in summary
    assert "fit_page_width" in summary


# --- ②전환 유형별 스페이서 높이 판정 ---------------------------------------

def test_spacing_inserts_and_modifies(hwpx_file):
    summary = ph.process_file(str(hwpx_file), star=False, spacing=True)
    events = summary["spacing"]["events"]
    names = [e["transition"] for e in events]
    # insert 경로: 발신줄→□, □→ㅇ(x2), ㅇ→-, -→＊, ＊→표(캡션 내장 후 승계, R034), ㅇ→□(블록구분)
    assert names.count("sending_to_dae") == 1
    assert names.count("dae_to_yo") == 2
    assert names.count("yo_to_dash") == 1
    assert names.count("dash_to_star") == 1
    assert names.count("star_to_table") == 1
    assert names.count("block_boundary") == 2  # 표→□2(기존 빈 문단 modify) + ㅇ2→□3(insert)
    assert summary["spacing"]["modified"] == 1  # 표→□2 구간의 기존 빈 문단
    assert summary["spacing"]["inserted"] == len(events) - 1

    with zipfile.ZipFile(hwpx_file) as z:
        sec = ET.fromstring(z.read("Contents/section0.xml"))
        header = ET.fromstring(z.read("Contents/header.xml"))

    heights = {cp.get("id"): cp.get("height") for cp in header.iter(ph.qn("hh", "charPr"))}
    tops = list(sec)
    texts = [ph.para_text(p).strip() for p in tops]

    def height_of(p):
        run = p.find(ph.qn("hp", "run"))
        return heights[run.get("charPrIDRef")]

    idx_sending = texts.index("< '26. 1. 1.(목), 테스트팀 >")
    idx_dae1 = next(i for i, t in enumerate(texts) if t == "□ 제목1")
    assert idx_dae1 == idx_sending + 2  # 스페이서 한 칸 삽입됨
    assert height_of(tops[idx_dae1 - 1]) == "1200"  # 제목표 직후 첫 □ 12pt (R060)

    idx_yo1 = texts.index("ㅇ 요지1")
    assert height_of(tops[idx_yo1 - 1]) == "600"

    idx_dash1 = texts.index("- 상세1")
    assert height_of(tops[idx_dash1 - 1]) == "300"   # ㅇ→대시 3pt (R013 정정 '26.9.10)

    idx_star1 = texts.index("＊ 각주1")
    assert height_of(tops[idx_star1 - 1]) == "300"

    # 캡션은 표 안 hp:caption으로 내장(R034) — 스페이서 1000은 표 래퍼 문단 앞에 위치
    idx_table = next(i for i, p in enumerate(tops)
                     if any(r.find(ph.qn("hp", "tbl")) is not None
                            for r in p.findall(ph.qn("hp", "run"))))
    assert height_of(tops[idx_table - 1]) == "1000"
    assert "[ 표 제목 ]" not in texts  # 최상위 캡션 문단은 표 안으로 이동

    idx_dae2 = texts.index("□ 제목2")
    assert height_of(tops[idx_dae2 - 1]) == "800"  # 표→□2, 기존 빈 문단 재활용(modify)

    idx_dae3 = texts.index("□ 제목3")
    assert height_of(tops[idx_dae3 - 1]) == "800"  # ㅇ2→□3, 신규 삽입(insert)

    # 600 높이 charPr은 dae_to_yo가 두 번 나와도 재사용되어 신규 등록이 1개만 추가돼야 한다.
    height_values = [cp.get("height") for cp in header.iter(ph.qn("hh", "charPr"))]
    assert height_values.count("600") == 1


def test_spacing_yo_to_yo_inserts_6pt(tmp_path):
    section = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 요지1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 요지2</hp:t></hp:run></hp:p>
</hs:sec>
"""
    p = tmp_path / "same_level.hwpx"
    build_hwpx(str(p), section_xml=section)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert [e["transition"] for e in summary["spacing"]["events"]] == ["yo_to_yo"]
    assert summary["spacing"]["events"][0]["height"] == 600
    assert summary["target_found"] is True


# --- ③비파괴(텍스트 콘텐츠 불변) ------------------------------------------

def test_all_preserves_text_content(hwpx_file):
    with zipfile.ZipFile(hwpx_file) as z:
        before = [t for t, _ in all_text_and_ids(z.read("Contents/section0.xml"))]

    ph.process_file(str(hwpx_file), star=True, spacing=True)

    with zipfile.ZipFile(hwpx_file) as z:
        after = [t for t, _ in all_text_and_ids(z.read("Contents/section0.xml"))]

    # 띄어쓰기 계층('26.7.22)은 선두 공백만 바꾸므로 strip 비교 — 의미 콘텐츠 비파괴 확인
    assert [b.strip() for b in before] == [a.strip() for a in after]


def test_zip_structure_preserved(hwpx_file):
    with zipfile.ZipFile(hwpx_file) as z:
        names_before = [n for n in z.namelist() if not n.endswith("/")]
        mimetype_before = z.read("mimetype")

    ph.process_file(str(hwpx_file), star=True, spacing=True)

    with zipfile.ZipFile(hwpx_file) as z:
        assert set(names_before) <= set(z.namelist())  # 기존 멤버 보존(정합이 추가는 하되 삭제 금지)
        assert z.namelist()[0] == "mimetype"
        assert z.read("mimetype") == mimetype_before
        bad = z.testzip()
        assert bad is None
        for n in z.namelist():
            if n.endswith(".xml"):
                ET.fromstring(z.read(n))  # 전체 xml 파싱 가능(구조 정상)


# --- 패키지 정합 R043 (내부망 반입 판별) ---------------------------------

def test_canonicalize_kordoc_package(tmp_path):
    """kordoc 최소 패키지 → 한컴 정본 프로파일: 필수 멤버 보강·디렉터리 제거·OCF 시그니처."""
    f = tmp_path / "k.hwpx"
    build_kordoc_like(f)
    ph.process_file(str(f), spacing=True)

    raw = f.read_bytes()
    with zipfile.ZipFile(f) as z:
        infos = z.infolist()
        names = z.namelist()
        assert names[0] == "mimetype" and names[1] == "version.xml"
        assert not any(n.endswith("/") for n in names)          # 디렉터리 엔트리 제거
        for req in ("settings.xml", "META-INF/manifest.xml", "META-INF/container.rdf"):
            assert req in names
        first = infos[0]
        assert first.compress_type == zipfile.ZIP_STORED
        assert first.header_offset == 0 and not first.extra
        assert raw[38:57] == MIMETYPE                            # OCF 평문 시그니처 위치
        by = {i.filename: i for i in infos}
        assert by["version.xml"].compress_type == zipfile.ZIP_STORED       # 정품 프로파일
        assert by["Contents/header.xml"].compress_type == zipfile.ZIP_DEFLATED
        cx = z.read("META-INF/container.xml").decode()
        assert "container.rdf" in cx and "PrvText.txt" in cx     # rootfiles 정본화
        assert 'href="settings.xml"' in z.read("Contents/content.hpf").decode()
        rdf = z.read("META-INF/container.rdf").decode()
        assert "Contents/header.xml" in rdf and "Contents/section0.xml" in rdf
        ET.fromstring(z.read("version.xml"))                     # 스키마 파싱 가능
        summary_names = names  # 텍스트 불변은 test_all_preserves_text_content가 보장


def test_canonicalize_removes_script_stubs(tmp_path):
    """한글 재저장본의 기본 JScript 스텁(확장자 없는 활성콘텐츠) 제거 + hpf 등재 철회."""
    f = tmp_path / "resaved.hwpx"
    build_kordoc_like(f)
    # 한글 재저장이 삽입하는 형태 재현: Scripts 멤버 + hpf item/itemref 등재
    with zipfile.ZipFile(f, "a") as z:
        z.writestr("Scripts/headerScripts", "var Documents = XHwpDocuments;".encode("utf-16-le"))
        z.writestr("Scripts/sourceScripts", "function OnDocument_New(){}".encode("utf-16-le"))
    with zipfile.ZipFile(f) as z:
        data = {n: z.read(n) for n in z.namelist()}
    data["Contents/content.hpf"] = data["Contents/content.hpf"].replace(
        b"</opf:manifest>",
        b'<opf:item id="headersc" href="Scripts/headerScripts" media-type="application/x-javascript ;charset=utf-16"/>'
        b'<opf:item id="sourcesc" href="Scripts/sourceScripts" media-type="application/x-javascript ;charset=utf-16"/>'
        b"</opf:manifest>").replace(
        b"</opf:spine>",
        b'<opf:itemref idref="headersc" linear="no"/></opf:spine>')
    with zipfile.ZipFile(f, "w") as z:
        zi = zipfile.ZipInfo("mimetype"); zi.compress_type = zipfile.ZIP_STORED
        z.writestr(zi, data.pop("mimetype"))
        for n, d in data.items():
            z.writestr(n, d)

    ph.process_file(str(f), spacing=True)

    with zipfile.ZipFile(f) as z:
        assert not any(n.startswith("Scripts/") for n in z.namelist())
        hpf = z.read("Contents/content.hpf")
        assert b"Scripts/" not in hpf and b"headersc" not in hpf
        ET.fromstring(hpf)  # 등재 철회 후에도 XML 정상


def test_canonicalize_idempotent(tmp_path):
    f = tmp_path / "k.hwpx"
    build_kordoc_like(f)
    ph.process_file(str(f), star=True)
    b1 = f.read_bytes()
    ph.process_file(str(f), star=True)
    assert f.read_bytes() == b1


def test_canonicalize_reports_summary(tmp_path, capsys):
    f = tmp_path / "k.hwpx"
    build_kordoc_like(f)
    rc = ph.main([str(f), "--spacing"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    pc = out["package_canonical"]
    assert "version.xml" in pc["added"] and pc["dirs_removed"] == 3
    assert pc["container_rewritten"] and pc["settings_registered"]


# --- CLI / exit code ------------------------------------------------------

def test_main_no_args_exit2(capsys):
    rc = ph.main([])
    assert rc == 2


def test_main_invalid_flag_exit2(hwpx_file, capsys):
    rc = ph.main([str(hwpx_file), "--bogus"])
    assert rc == 2


def test_main_all_success_exit0(hwpx_file, capsys):
    rc = ph.main([str(hwpx_file), "--all"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = __import__("json").loads(out)
    assert payload["changed"] is True


def test_main_nothing_to_do_exit1(tmp_path, capsys):
    section = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="3" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>요지1</hp:t></hp:run></hp:p>
</hs:sec>
"""
    header = HEADER_XML.replace(
        "</hh:paraProperties>",
        '''<hh:paraPr id="3" tabPrIDRef="0"><hh:align horizontal="JUSTIFY" vertical="BASELINE"/><hh:margin><hc:intent value="-3000" unit="HWPUNIT"/><hc:left value="0" unit="HWPUNIT"/><hc:right value="0" unit="HWPUNIT"/><hc:prev value="0" unit="HWPUNIT"/><hc:next value="0" unit="HWPUNIT"/></hh:margin></hh:paraPr></hh:paraProperties>''')
    p = tmp_path / "nothing.hwpx"
    build_hwpx(str(p), header_xml=header, section_xml=section)
    rc = ph.main([str(p), "--spacing"])
    assert rc == 1


def test_main_missing_file_exit2(capsys):
    rc = ph.main(["/nonexistent/path/x.hwpx", "--all"])
    assert rc == 2


def test_yo_to_star_transition_inferred():
    from postprocess_hwpx import transition_for
    assert transition_for("yo", "star") == ("yo_to_star", 300)


def test_yo_to_yo_and_dash_to_yo_transitions():
    from postprocess_hwpx import transition_for
    assert transition_for("yo", "yo") == ("yo_to_yo", 600)
    assert transition_for("dash", "yo") == ("dash_to_yo", 600)


def test_zero_margins_removes_parapr_prev(tmp_path):
    # 콘텐츠 문단이 참조하는 paraPr의 prev/next 여백이 spacing 처리 시 0으로
    header = HEADER_XML.replace(
        '<hc:prev value="0" unit="HWPUNIT"/>',
        '<hc:prev value="3000" unit="HWPUNIT"/>')
    p = tmp_path / "zm.hwpx"
    build_hwpx(str(p), header_xml=header)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["zero_margins"]["count"] == 1
    assert summary["zero_margins"]["zeroed"][0]["old"]["prev"] == "3000"
    with zipfile.ZipFile(str(p)) as z:
        hdr_root = ET.fromstring(z.read("Contents/header.xml"))
    # 최상위 콘텐츠 문단이 참조하는 paraPr(id=0)의 prev=3000이 0으로 교정됐는지.
    # ※ 캡션 내장(R034)이 zero_margins보다 먼저 실행되므로, 내장 캡션의 CENTER 복제
    #   paraPr은 base의 prev=3000을 물려받은 채 남는다 — 최상위 흐름 밖이라 R014 비대상.
    pp0 = next(pp for pp in hdr_root.iter(ph.qn("hh", "paraPr")) if pp.get("id") == "0")
    prev0 = pp0.find(f"{ph.qn('hh', 'margin')}/{ph.qn('hc', 'prev')}")
    assert prev0.get("value") == "0"
    # 실효 간격 리포트: □→ㅇ = 스페이서 6pt + prev 0
    gaps = {g["between"]: g["gap_pt"] for g in summary["effective_gaps"]}
    assert gaps.get("dae→yo") == 6.0


def test_table_alignment_and_caption_embed(tmp_path):
    # R034: 캡션은 hp:caption으로 내장(CENTER) / R015 정정: 본문 콘텐츠 표 래퍼 RIGHT
    p = tmp_path / "ct.hwpx"
    build_hwpx(str(p))
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["caption_embed"]["embedded"] == 1
    assert summary["table_alignment"]["aligned"]["caption"] == 0  # 잔존 캡션 문단 없음
    assert summary["table_alignment"]["aligned"]["table_right"] == 1
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    aligns = {}
    for pp in hdr.iter(ph.qn("hh", "paraPr")):
        al = pp.find(ph.qn("hh", "align"))
        aligns[pp.get("id")] = al.get("horizontal") if al is not None else None
    tbl = next(t for t in sec.iter(ph.qn("hp", "tbl")))
    cap = tbl.find(ph.qn("hp", "caption"))
    assert cap is not None
    cap_p = next(cp for cp in cap.iter(ph.qn("hp", "p")))
    assert "[ 표 제목 ]" in "".join(t.text or "" for t in cap_p.iter(ph.qn("hp", "t")))
    assert aligns[cap_p.get("paraPrIDRef")] == "CENTER"  # 내장 캡션 문단 CENTER
    wrapper = next(c for c in sec if c.tag == ph.qn("hp", "p")
                   and any(r.find(ph.qn("hp", "tbl")) is not None
                           for r in c.findall(ph.qn("hp", "run"))))
    assert aligns[wrapper.get("paraPrIDRef")] == "RIGHT"  # 표 래퍼 문단 RIGHT


# --- ④표-문단 간격 보정 전환 값 -------------------------------------------

def test_new_table_spacing_transitions():
    assert ph.transition_for("caption", "table") == ("caption_to_table", 300)
    assert ph.transition_for("table", "cham") == ("table_to_cham", 300)
    assert ph.transition_for("yo", "caption") == ("yo_to_caption", 600)
    assert ph.transition_for("dash", "caption") == ("dash_to_caption", 600)
    assert ph.transition_for("cham", "caption") == ("cham_to_caption", 600)
    # table→dae 블록 경계 8pt (R060 — 두 번째 이후 □ 상단)
    assert ph.transition_for("table", "dae") == ("block_boundary", 800)


# --- ⑤표 셀 텍스트 가운데 정렬(제목 박스 제외) -----------------------------

# 시나리오: 제목 박스 표(첫 □ 이전) → 발신줄 → □1 → 캡션 → 콘텐츠 표
TITLE_BOX_SECTION_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:tbl id="1" rowCnt="1" colCnt="1" borderFillIDRef="1"><hp:tr><hp:tc borderFillIDRef="1"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>제목텍스트</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>&lt; '26. 1. 1.(목), 테스트팀 &gt;</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 제목1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>[ 표 제목 ]</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:tbl id="2" rowCnt="1" colCnt="1"><hp:tr><hp:tc><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>셀값</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
</hs:sec>
"""


def test_center_cell_text_excludes_title_box(tmp_path):
    p = tmp_path / "title_box.hwpx"
    build_hwpx(str(p), section_xml=TITLE_BOX_SECTION_XML)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["center_cells"]["tables"] == 1       # 제목 박스 표는 제외, 콘텐츠 표만 카운트
    assert summary["center_cells"]["paragraphs"] == 2   # 셀 문단 + 내장 캡션 문단(R034)

    with zipfile.ZipFile(p) as z:
        sec = z.read("Contents/section0.xml").decode()

    i_title_cell = sec.find("제목텍스트")
    seg_title = sec[max(0, i_title_cell - 200):i_title_cell]
    pid_title = re.findall(r'paraPrIDRef="(\d+)"', seg_title)[-1]
    assert pid_title == "0"  # 제목 박스 셀은 가운데 정렬 대상에서 제외되어 원래 paraPr 유지

    i_cell = sec.find("셀값")
    seg_cell = sec[max(0, i_cell - 200):i_cell]
    pid_cell = re.findall(r'paraPrIDRef="(\d+)"', seg_cell)[-1]
    assert pid_cell != "0"  # 콘텐츠 표 셀은 새 CENTER paraPr로 치환됨

    with zipfile.ZipFile(p) as z:
        hdr = z.read("Contents/header.xml").decode()
    m = re.search(rf'<hh:paraPr id="{pid_cell}"[^>]*>.*?</hh:paraPr>', hdr, re.S)
    assert 'horizontal="CENTER"' in m.group()


def test_center_cell_text_on_content_table(hwpx_file):
    summary = ph.process_file(str(hwpx_file), star=False, spacing=True)
    assert summary["center_cells"]["tables"] == 1
    assert summary["center_cells"]["paragraphs"] == 2  # 셀 문단 + 내장 캡션 문단(R034)
    with zipfile.ZipFile(hwpx_file) as z:
        hdr = z.read("Contents/header.xml").decode()
        sec = z.read("Contents/section0.xml").decode()
    i = sec.find("셀")
    seg = sec[max(0, i - 200):i]
    pid = re.findall(r'paraPrIDRef="(\d+)"', seg)[-1]
    assert pid != "0"
    m = re.search(rf'<hh:paraPr id="{pid}"[^>]*>.*?</hh:paraPr>', hdr, re.S)
    assert 'horizontal="CENTER"' in m.group()


# --- ⑥제목 박스 테두리 제거 -------------------------------------------------

def test_title_box_borderless_replaces_refs(tmp_path):
    p = tmp_path / "title_borderless2.hwpx"
    build_hwpx(str(p), section_xml=TITLE_BOX_SECTION_XML)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["title_box"]["found"] is True
    assert summary["title_box"]["fills_replaced"] >= 2  # hp:tbl + hp:tc 각각 치환
    with zipfile.ZipFile(p) as z:
        sec = z.read("Contents/section0.xml").decode()
    i = sec.find("제목텍스트")
    seg = sec[max(0, i - 400):i]
    # 원본(id=1, SOLID) 참조가 배경 보존 무테두리 변형으로 교체됨 ('26.7.22 개정)
    assert 'borderFillIDRef="1"' not in seg
    new_id = summary["title_box"]["variants"]["1"]
    assert f'borderFillIDRef="{new_id}"' in seg


def test_title_box_borderless_creates_fill_when_missing(tmp_path):
    header_no_borderless = HEADER_XML.replace(
        '<hh:leftBorder type="NONE" width="0.1 mm" color="#000000"/>\n'
        '        <hh:rightBorder type="NONE" width="0.1 mm" color="#000000"/>\n'
        '        <hh:topBorder type="NONE" width="0.1 mm" color="#000000"/>\n'
        '        <hh:bottomBorder type="NONE" width="0.1 mm" color="#000000"/>',
        '<hh:leftBorder type="SOLID" width="0.1 mm" color="#000000"/>\n'
        '        <hh:rightBorder type="SOLID" width="0.1 mm" color="#000000"/>\n'
        '        <hh:topBorder type="SOLID" width="0.1 mm" color="#000000"/>\n'
        '        <hh:bottomBorder type="SOLID" width="0.1 mm" color="#000000"/>',
    )
    bf_block = re.search(
        r'<hh:borderFills.*?</hh:borderFills>', header_no_borderless, re.S).group()
    assert 'Border type="NONE"' not in bf_block  # left/right/top/bottomBorder 전부 SOLID(대각선 slash/backSlash는 NONE 그대로)
    p = tmp_path / "title_borderless_new.hwpx"
    build_hwpx(str(p), header_xml=header_no_borderless, section_xml=TITLE_BOX_SECTION_XML)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["title_box"]["found"] is True
    assert summary["title_box"]["fills_replaced"] >= 2
    with zipfile.ZipFile(p) as z:
        hdr = z.read("Contents/header.xml").decode()
    assert 'itemCnt="3"' in re.search(r'<hh:borderFills itemCnt="(\d+)"', hdr).group()
    new_fill = re.search(r'<hh:borderFill id="3"[^>]*>.*?</hh:borderFill>', hdr, re.S).group()
    # 좌·우만 NONE — 상·하 괘선은 양식 제목부의 시각 요소라 보존한다('26.9.8 회귀)
    assert re.search(r'leftBorder type="NONE"', new_fill)
    assert re.search(r'rightBorder type="NONE"', new_fill)
    assert re.search(r'topBorder type="SOLID"', new_fill)
    assert re.search(r'bottomBorder type="SOLID"', new_fill)
    assert 'slash type="NONE"' in new_fill  # 대각선(slash/backSlash)은 원본 그대로 보존(원래도 NONE)


def test_title_box_not_found_when_no_table_before_dae(hwpx_file):
    # hwpx_file(기존 SECTION_XML)은 첫 □ 이전에 표가 없다(첫 표는 □1 이후) → 제목 박스 없음
    summary = ph.process_file(str(hwpx_file), star=False, spacing=True)
    assert summary["title_box"]["found"] is False
    assert summary["title_box"]["fills_replaced"] == 0


# --- ⑦발신 크기 훅 ----------------------------------------------------------

def test_apply_sender_size_preserves_font(hwpx_file):
    summary = ph.process_file(str(hwpx_file), star=False, spacing=False, sender_size=13)
    r = summary["sender_size"]
    assert r["height"] == 1300
    assert r["sending_found"] == 1
    assert r["runs_changed"] == 1
    with zipfile.ZipFile(hwpx_file) as z:
        hdr = z.read("Contents/header.xml").decode()
        sec = z.read("Contents/section0.xml").decode()
    i = sec.find("테스트팀")
    seg = sec[max(0, i - 200):i]
    new_id = re.findall(r'charPrIDRef="(\d+)"', seg)[-1]
    assert new_id != "0"
    cp = re.search(rf'<hh:charPr id="{new_id}"[^>]*>.*?</hh:charPr>', hdr, re.S).group()
    assert 'height="1300"' in cp
    assert 'hangul="0"' in cp  # 발신 줄 원 charPr(id=0, 휴먼명조) 기반 복제 — 기존 height=1300(id=1, 맑은고딕)과 다른 폰트 유지


def test_apply_sender_size_idempotent(hwpx_file):
    ph.process_file(str(hwpx_file), star=False, spacing=False, sender_size=13)
    summary2 = ph.process_file(str(hwpx_file), star=False, spacing=False, sender_size=13)
    assert summary2["sender_size"]["runs_changed"] == 0


def test_apply_sender_size_no_sending_line(tmp_path):
    section = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 요지1</hp:t></hp:run></hp:p>
</hs:sec>
"""
    p = tmp_path / "nosend.hwpx"
    build_hwpx(str(p), section_xml=section)
    summary = ph.process_file(str(p), star=False, spacing=False, sender_size=13)
    assert summary["sender_size"]["sending_found"] == 0
    assert summary["target_found"] is False


# --- ⑧＊/※ 들여쓰기 훅 -------------------------------------------------------

# --- CLI: --sender-size 파싱 / --star-indent 제거 확인 ----------------------

def test_main_sender_size_cli(hwpx_file, capsys):
    rc = ph.main([str(hwpx_file), "--sender-size", "13"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = __import__("json").loads(out)
    assert payload["sender_size"]["height"] == 1300
    assert "spacing" not in payload  # --spacing 미지정 시 다른 기능은 실행 안 됨


def test_main_sender_size_missing_value_exit2(hwpx_file):
    rc = ph.main([str(hwpx_file), "--sender-size"])
    assert rc == 2


def test_main_sender_size_non_numeric_exit2(hwpx_file):
    rc = ph.main([str(hwpx_file), "--sender-size", "abc"])
    assert rc == 2


def test_main_star_indent_removed_rejects_any_value(hwpx_file):
    """R019 폐기로 --star-indent는 CLI에서 제거됐다 — 값 형식과 무관하게 거부된다.

    종전 테스트는 `15`·`a,b` 같은 잘못된 값만 확인해서 '플래그는 있는데 값이 틀렸다'로
    읽혔다. 실제로는 플래그 자체가 없어 **유효해 보이는 값도** 거부된다. 문서가 이 플래그를
    쓸 수 있는 것처럼 서술했던 드리프트를 여기서 고정한다."""
    for value in ("15", "a,b", "0,-6000"):
        assert ph.main([str(hwpx_file), "--star-indent", value]) == 2, value


def test_main_all_includes_sender_size_default(hwpx_file, capsys):
    """--all이 발신 줄 12pt(R018)를 기본 적용한다 — 종전 별도 지정·9곳 복제 계약의 반전.

    빠뜨리면 R018 미적용본이 검증을 통과하던 사고 경로를 기본값 승격으로 제거했다."""
    rc = ph.main([str(hwpx_file), "--all"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = __import__("json").loads(out)
    assert payload["sender_size"]["height"] == ph.SENDER_SIZE_PT * 100
    assert "star_indent" not in payload
    assert "center_cells" in payload   # 기능 1은 spacing 묶음으로 --all에 포함됨
    assert "title_box" in payload      # 기능 3도 spacing 묶음으로 --all에 포함됨


def test_main_all_sender_size_override(hwpx_file, capsys):
    """--sender-size PT는 --all의 기본값 12pt를 재정의한다."""
    rc = ph.main([str(hwpx_file), "--all", "--sender-size", "13"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = __import__("json").loads(out)
    assert payload["sender_size"]["height"] == 1300
    assert "center_cells" in payload


def test_title_box_keeps_gradient_fill(tmp_path):
    # 그라데이션 배경 + SOLID 테두리 borderFill을 참조하는 제목 박스 밴드 행 →
    # 좌·우 테두리만 NONE, fillBrush(gradation) 보존된 변형으로 교체돼야 한다.
    # 채움은 밴드 행이 지고 제목 행은 비어 있다(양식·실산출물 실측) — R084 판정이
    # 요구하는 형태이기도 하다.
    header = HEADER_XML.replace(
        "</hh:borderFills>",
        '''<hh:borderFill id="7" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">
      <hh:slash type="NONE" Crooked="0" isCounter="0"/>
      <hh:backSlash type="NONE" Crooked="0" isCounter="0"/>
      <hh:leftBorder type="SOLID" width="0.12 mm" color="#000000"/>
      <hh:rightBorder type="SOLID" width="0.12 mm" color="#000000"/>
      <hh:topBorder type="SOLID" width="0.12 mm" color="#000000"/>
      <hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000"/>
      <hc:fillBrush><hc:gradation type="LINEAR" angle="90"><hc:color value="#FFFFFF"/><hc:color value="#0066CC"/></hc:gradation></hc:fillBrush>
    </hh:borderFill></hh:borderFills>''')
    section = '''<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:tbl id="1" rowCnt="3" colCnt="1" borderFillIDRef="7"><hp:sz width="47909" height="3614"/><hp:tr><hp:tc borderFillIDRef="7"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t/></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSz width="47909" height="382"/></hp:tc></hp:tr><hp:tr><hp:tc borderFillIDRef="1"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>제목</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="1"/><hp:cellSz width="47909" height="2850"/></hp:tc></hp:tr><hp:tr><hp:tc borderFillIDRef="7"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t/></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="2"/><hp:cellSz width="47909" height="382"/></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 절</hp:t></hp:run></hp:p>
</hs:sec>
'''
    p = tmp_path / "grad.hwpx"
    build_hwpx(str(p), header_xml=header, section_xml=section)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["title_box"]["found"] is True
    assert summary["title_box_form"]["skipped"] == "already_restored"   # 이미 3행 원형
    assert summary["title_box"]["fills_replaced"] == 4   # 표 + 셀 3개
    import xml.etree.ElementTree as _ET
    with zipfile.ZipFile(str(p)) as z:
        hdr_root = _ET.fromstring(z.read("Contents/header.xml"))
        sec_txt = z.read("Contents/section0.xml").decode()
    new_id = summary["title_box"]["variants"]["7"]
    target = None
    for bf in hdr_root.iter(ph.qn("hh", "borderFill")):
        if bf.get("id") == new_id:
            target = bf
    assert target is not None
    for tname in ("leftBorder", "rightBorder"):
        assert target.find(ph.qn("hh", tname)).get("type") == "NONE"
    for tname in ("topBorder", "bottomBorder"):   # 상·하 괘선 보존
        assert target.find(ph.qn("hh", tname)).get("type") == "SOLID"
    assert target.find(ph.qn("hc", "fillBrush")) is not None  # 그라데이션 보존
    assert f'borderFillIDRef="{new_id}"' in sec_txt


def test_space_hierarchy_prefix_and_flatten(tmp_path):
    section = '''<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 절</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="3" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 요지</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="3" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>- 상세</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>＊ 각주</hp:t></hp:run></hp:p>
</hs:sec>
'''
    header = HEADER_XML.replace(
        "</hh:paraProperties>",
        '''<hh:paraPr id="3" tabPrIDRef="0"><hh:align horizontal="JUSTIFY" vertical="BASELINE"/><hh:margin><hc:intent value="-2205" unit="HWPUNIT"/><hc:left value="1500" unit="HWPUNIT"/><hc:right value="0" unit="HWPUNIT"/><hc:prev value="0" unit="HWPUNIT"/><hc:next value="0" unit="HWPUNIT"/></hh:margin></hh:paraPr></hh:paraProperties>''')
    p = tmp_path / "sh.hwpx"
    build_hwpx(str(p), header_xml=header, section_xml=section)
    summary = ph.process_file(str(p), star=False, spacing=True)
    sh = summary["space_hierarchy"]
    assert sh["prefixed"] >= 3 and sh["flattened"] >= 2
    with zipfile.ZipFile(str(p)) as z:
        sec = z.read("Contents/section0.xml").decode()
    assert "<hp:t>□ 절</hp:t>" in sec              # 0칸
    assert "<hp:t> ㅇ 요지</hp:t>" in sec           # 1칸
    assert "<hp:t>   - 상세</hp:t>" in sec          # 3칸
    assert "<hp:t>     ＊ 각주</hp:t>" in sec       # 5칸 (star-footnote 미실행이라 텍스트만 확인)
    # 내어쓰기: ㅇ 문단 paraPr left=3000·intent=-3000 (랩 줄 자동 들여쓰기)
    import xml.etree.ElementTree as _ET
    with zipfile.ZipFile(str(p)) as z:
        hdr_root = _ET.fromstring(z.read("Contents/header.xml"))
        sec_root = _ET.fromstring(z.read("Contents/section0.xml"))
    margins = {}
    for pp in hdr_root.iter(ph.qn("hh", "paraPr")):
        m = pp.find(ph.qn("hh", "margin"))
        if m is not None:
            margins[pp.get("id")] = {tt: (m.find(ph.qn("hc", tt)).get("value") if m.find(ph.qn("hc", tt)) is not None else None) for tt in ("left", "intent")}
    kinds_seen = {}
    for para in sec_root.iter(ph.qn("hp", "p")):
        k = ph.classify(para)
        if k in ("yo", "dash", "star") and k not in kinds_seen:
            kinds_seen[k] = margins.get(para.get("paraPrIDRef"), {})
    assert kinds_seen["yo"] == {"left": "0", "intent": "-3000"}
    assert kinds_seen["dash"] == {"left": "0", "intent": "-3750"}
    assert kinds_seen["star"] == {"left": "0", "intent": "-5200"}


def test_page_margins_forced_to_template(tmp_path):
    section = '''<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:secPr><hp:pagePr landscape="WIDELY" width="59528" height="84188" gutterType="LEFT_ONLY"><hp:margin header="4251" footer="4251" gutter="0" left="5669" right="5669" top="4252" bottom="4252"/></hp:pagePr></hp:secPr><hp:t> ㅇ 본문</hp:t></hp:run></hp:p>
</hs:sec>
'''
    p = tmp_path / "pm.hwpx"
    build_hwpx(str(p), section_xml=section)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["page_margins"]["attrs_changed"] >= 2   # top·footer 교정
    with zipfile.ZipFile(str(p)) as z:
        sec_out = z.read("Contents/section0.xml").decode()
    assert 'top="2835"' in sec_out and 'footer="2835"' in sec_out
    assert 'header="4252"' in sec_out and 'bottom="4252"' in sec_out


TITLE_BOX_SECTION = '''<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:tbl id="1" rowCnt="3" colCnt="1" borderFillIDRef="1"><hp:sz width="47909" widthRelTo="ABSOLUTE" height="3614" heightRelTo="ABSOLUTE" protect="0"/><hp:tr><hp:tc borderFillIDRef="1"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t/></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSz width="47909" height="382"/></hp:tc></hp:tr><hp:tr><hp:tc borderFillIDRef="1"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>제목 텍스트</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="1"/><hp:cellSz width="47909" height="2850"/></hp:tc></hp:tr><hp:tr><hp:tc borderFillIDRef="1"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t/></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="2"/><hp:cellSz width="47909" height="382"/></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>&lt; '26. 7. 24.(금), 테스트팀 &gt;</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 제목1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 요지1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>[ 캡션 ]</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:tbl id="2" rowCnt="1" colCnt="1" borderFillIDRef="1"><hp:tr><hp:tc borderFillIDRef="1"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>셀 텍스트</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSz width="47909" height="382"/></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>※ 단서</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>☞ 결론 유도 문장</hp:t></hp:run></hp:p>
</hs:sec>
'''


def test_title_box_topgap_keeps_rows_fixes_linespacing(tmp_path):
    p = tmp_path / "tg.hwpx"
    build_hwpx(str(p), section_xml=TITLE_BOX_SECTION)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["title_box_topgap"]["anchors_fixed"] == 1
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    # 행 삭제 금지: 그라데이션 밴드 행(3행 원형) 유지
    tbl = next(t for t in sec.iter(ph.qn("hp", "tbl")) if t.get("id") == "1")
    assert tbl.get("rowCnt") == "3" and len(tbl.findall(ph.qn("hp", "tr"))) == 3
    # 앵커 문단 줄간격 100% 치환
    anchor = next(c for c in sec if c.tag == ph.qn("hp", "p")
                  and any(r.find(ph.qn("hp", "tbl")) is not None
                          and r.find(ph.qn("hp", "tbl")).get("id") == "1"
                          for r in c.findall(ph.qn("hp", "run"))))
    ls_by_id = {}
    for pp in hdr.iter(ph.qn("hh", "paraPr")):
        ls = pp.find(ph.qn("hh", "lineSpacing"))
        if ls is not None:
            ls_by_id[pp.get("id")] = ls.get("value")
    assert ls_by_id[anchor.get("paraPrIDRef")] == "100"
    # 본문 콘텐츠 표(id=2) 앵커는 줄간격 유지(캡션·표 센터 paraPr일 뿐 160 유지)
    tbl2_anchor = next(c for c in sec if c.tag == ph.qn("hp", "p")
                       and any(r.find(ph.qn("hp", "tbl")) is not None
                               and r.find(ph.qn("hp", "tbl")).get("id") == "2"
                               for r in c.findall(ph.qn("hp", "run"))))
    assert ls_by_id[tbl2_anchor.get("paraPrIDRef")] == "160"


def test_title_box_topgap_idempotent(tmp_path):
    p = tmp_path / "tg2.hwpx"
    build_hwpx(str(p), section_xml=TITLE_BOX_SECTION)
    ph.process_file(str(p), star=False, spacing=True)
    summary2 = ph.process_file(str(p), star=False, spacing=True)
    assert summary2["title_box_topgap"]["anchors_fixed"] == 0
    assert summary2["title_box_topgap"]["outmargins_fixed"] == 0


def test_title_box_topgap_zeroes_outmargin_top(tmp_path):
    section = TITLE_BOX_SECTION.replace(
        '<hp:tbl id="1" rowCnt="3" colCnt="1" borderFillIDRef="1">',
        '<hp:tbl id="1" rowCnt="3" colCnt="1" borderFillIDRef="1">'
        '<hp:outMargin left="283" right="283" top="283" bottom="283"/>')
    p = tmp_path / "tg3.hwpx"
    build_hwpx(str(p), section_xml=section)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["title_box_topgap"]["outmargins_fixed"] == 1
    with zipfile.ZipFile(str(p)) as z:
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    tbl = next(t for t in sec.iter(ph.qn("hp", "tbl")) if t.get("id") == "1")
    out = tbl.find(ph.qn("hp", "outMargin"))
    assert out.get("top") == "0" and out.get("bottom") == "283"


def test_caption_and_cell_font_12pt(tmp_path):
    p = tmp_path / "cf.hwpx"
    build_hwpx(str(p), section_xml=TITLE_BOX_SECTION)
    summary = ph.process_file(str(p), star=False, spacing=True)
    cfr = summary["caption_table_font"]
    assert cfr["height"] == 1200
    # R034 내장 후 캡션 문단은 표 안에 있으므로 cell_runs로 집계된다(최상위 캡션 0건)
    assert cfr["caption_runs_changed"] == 0 and cfr["cell_runs_changed"] >= 2
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    heights = {cp.get("id"): cp.get("height") for cp in hdr.iter(ph.qn("hh", "charPr"))}
    # 캡션 문단 run charPr 높이 1200
    for para in sec.iter(ph.qn("hp", "p")):
        if ph.classify(para) == "caption":
            run = para.find(ph.qn("hp", "run"))
            assert heights[run.get("charPrIDRef")] == "1200"
    # 콘텐츠 표 셀 문단 run charPr 높이 1200 (제목 박스 셀은 제외)
    tbl2 = next(t for t in sec.iter(ph.qn("hp", "tbl")) if t.get("id") == "2")
    for cp_ref in [r.get("charPrIDRef") for r in tbl2.iter(ph.qn("hp", "run"))]:
        assert heights[cp_ref] == "1200"
    tbl1 = next(t for t in sec.iter(ph.qn("hp", "tbl")) if t.get("id") == "1")
    for cp_ref in [r.get("charPrIDRef") for r in tbl1.iter(ph.qn("hp", "run"))]:
        assert heights[cp_ref] != "1200"


def test_dae_bold_applied(tmp_path):
    p = tmp_path / "db.hwpx"
    build_hwpx(str(p), section_xml=TITLE_BOX_SECTION)
    summary = ph.process_file(str(p), star=False, spacing=True)
    dbr = summary["dae_bold"]
    assert dbr["dae_found"] == 1 and dbr["runs_changed"] == 1
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    bold_ids = {cp.get("id") for cp in hdr.iter(ph.qn("hh", "charPr"))
                if cp.find(ph.qn("hh", "bold")) is not None}
    for para in sec.iter(ph.qn("hp", "p")):
        if ph.classify(para) == "dae":
            assert para.find(ph.qn("hp", "run")).get("charPrIDRef") in bold_ids
    # 재실행 멱등
    summary2 = ph.process_file(str(p), star=False, spacing=True)
    assert summary2["dae_bold"]["runs_changed"] == 0


def test_arrow_hierarchy_spacing(tmp_path):
    p = tmp_path / "ar.hwpx"
    build_hwpx(str(p), section_xml=TITLE_BOX_SECTION)
    ph.process_file(str(p), star=False, spacing=True)
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = z.read("Contents/section0.xml").decode()
        sec_root = ET.fromstring(z.read("Contents/section0.xml"))
    # ☞ 문단: ※·＊와 같은 5칸 선두 띄어쓰기
    assert "<hp:t>     ☞ 결론 유도 문장</hp:t>" in sec
    # 내어쓰기: left=0·intent=-6000 (15pt 본문 4글자 폭)
    margins = {}
    for pp in hdr.iter(ph.qn("hh", "paraPr")):
        m = pp.find(ph.qn("hh", "margin"))
        if m is not None:
            margins[pp.get("id")] = {t: m.find(ph.qn("hc", t)).get("value")
                                     for t in ("left", "intent")
                                     if m.find(ph.qn("hc", t)) is not None}
    for para in sec_root.iter(ph.qn("hp", "p")):
        if ph.classify(para) == "arrow":
            assert margins[para.get("paraPrIDRef")] == {"left": "0", "intent": "-6000"}


def test_classify_arrow():
    p = ET.fromstring('<hp:p xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" paraPrIDRef="0"><hp:run charPrIDRef="0"><hp:t>☞ 귀결</hp:t></hp:run></hp:p>')
    assert ph.classify(p) == "arrow"
    assert ph.TRANSITIONS[("cham", "arrow")] == ("cham_to_arrow", 300)


BANNER_SECTION = '''<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 본문 절</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 요지</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:tbl id="9" rowCnt="1" colCnt="3" borderFillIDRef="1"><hp:tr><hp:tc borderFillIDRef="1"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>붙 임</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSz width="5000" height="382"/></hp:tc><hp:tc borderFillIDRef="1"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t/></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="1" rowAddr="0"/><hp:cellSz width="1000" height="382"/></hp:tc><hp:tc borderFillIDRef="1"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>검토 근거 상세</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="2" rowAddr="0"/><hp:cellSz width="40000" height="382"/></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 붙임 절</hp:t></hp:run></hp:p>
</hs:sec>
'''

HEADER_WITH_HEADLINE = HEADER_XML.replace(
    '<hh:font id="1" face="맑은고딕" type="TTF" isEmbedded="0"/>',
    '<hh:font id="1" face="맑은고딕" type="TTF" isEmbedded="0"/>\n        '
    '<hh:font id="2" face="HY헤드라인M" type="TTF" isEmbedded="0"/>')


def test_annex_banner_pagebreak_and_font(tmp_path):
    p = tmp_path / "bn.hwpx"
    build_hwpx(str(p), header_xml=HEADER_WITH_HEADLINE, section_xml=BANNER_SECTION)
    summary = ph.process_file(str(p), star=False, spacing=True)
    abr = summary["annex_banner"]
    assert abr["banners"] == 1 and abr["cell_runs_changed"] >= 2
    # R023이 배너 셀을 12pt로 낮추지 않아야 한다
    assert summary["caption_table_font"]["cell_runs_changed"] == 0
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    # 앵커 문단 pageBreakBefore=1
    anchor = next(c for c in sec if c.tag == ph.qn("hp", "p")
                  and any(r.find(ph.qn("hp", "tbl")) is not None
                          for r in c.findall(ph.qn("hp", "run"))))
    pb = {}
    fonts_h = {}
    for pp in hdr.iter(ph.qn("hh", "paraPr")):
        bs = pp.find(ph.qn("hh", "breakSetting"))
        pb[pp.get("id")] = bs.get("pageBreakBefore") if bs is not None else None
    assert pb[anchor.get("paraPrIDRef")] == "1"
    # 배너 셀 charPr = HY헤드라인M(2)·1600
    info = {}
    for cp in hdr.iter(ph.qn("hh", "charPr")):
        fr = cp.find(ph.qn("hh", "fontRef"))
        info[cp.get("id")] = (cp.get("height"), fr.get("hangul") if fr is not None else None)
    tbl = next(t for t in sec.iter(ph.qn("hp", "tbl")))
    for run in tbl.iter(ph.qn("hp", "run")):
        assert info[run.get("charPrIDRef")] == ("1600", "2")


def test_annex_banner_idempotent_and_no_font_noop(tmp_path):
    p = tmp_path / "bn2.hwpx"
    build_hwpx(str(p), header_xml=HEADER_WITH_HEADLINE, section_xml=BANNER_SECTION)
    ph.process_file(str(p), star=False, spacing=True)
    s2 = ph.process_file(str(p), star=False, spacing=True)
    assert s2["annex_banner"]["cell_runs_changed"] == 0
    # HY헤드라인M 폰트가 없는 문서에서는 폰트 치환 no-op, 라벨 흰색 치환 1건만 발생
    p3 = tmp_path / "bn3.hwpx"
    build_hwpx(str(p3), section_xml=BANNER_SECTION)
    s3 = ph.process_file(str(p3), star=False, spacing=True)
    assert s3["annex_banner"]["banners"] == 1
    assert s3["annex_banner"]["cell_runs_changed"] == 1


def test_is_banner_table_rejects_content_tables():
    tbl = ET.fromstring(
        '<hp:tbl xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" rowCnt="1" colCnt="3">'
        '<hp:tr>'
        '<hp:tc><hp:subList><hp:p><hp:run><hp:t>구 분</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
        '<hp:tc><hp:subList><hp:p><hp:run><hp:t>a</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
        '<hp:tc><hp:subList><hp:p><hp:run><hp:t>b</hp:t></hp:run></hp:p></hp:subList></hp:tc>'
        '</hp:tr></hp:tbl>')
    assert not ph._is_banner_table(tbl)


def test_annex_banner_cell_styles(tmp_path):
    p = tmp_path / "bs.hwpx"
    build_hwpx(str(p), header_xml=HEADER_WITH_HEADLINE, section_xml=BANNER_SECTION)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["annex_banner"]["fills_set"] == 3
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    fills = {bf.get("id"): bf for bf in hdr.iter(ph.qn("hh", "borderFill"))}
    tbl = next(t for t in sec.iter(ph.qn("hp", "tbl")))
    cells = tbl.find(ph.qn("hp", "tr")).findall(ph.qn("hp", "tc"))
    # 라벨 셀: 4변 SOLID 0.5mm #1B1760 + 채움 #2B2D63
    bf0 = fills[cells[0].get("borderFillIDRef")]
    for side in ("left", "right", "top", "bottom"):
        el = bf0.find(ph.qn("hh", f"{side}Border"))
        assert (el.get("type"), el.get("width"), el.get("color")) == ("SOLID", "0.5 mm", "#1B1760")
    brush = bf0.find(f"{ph.qn('hc', 'fillBrush')}/{ph.qn('hc', 'winBrush')}")
    assert brush.get("faceColor") == "#2B2D63"
    # 스페이서: 좌변만 SOLID, 채움 없음
    bf1 = fills[cells[1].get("borderFillIDRef")]
    assert bf1.find(ph.qn("hh", "leftBorder")).get("type") == "SOLID"
    assert bf1.find(ph.qn("hh", "topBorder")).get("type") == "NONE"
    assert bf1.find(ph.qn("hc", "fillBrush")) is None
    # 제목 셀: 상·하변 SOLID, 좌·우 NONE
    bf2 = fills[cells[2].get("borderFillIDRef")]
    assert bf2.find(ph.qn("hh", "topBorder")).get("type") == "SOLID"
    assert bf2.find(ph.qn("hh", "bottomBorder")).get("type") == "SOLID"
    assert bf2.find(ph.qn("hh", "leftBorder")).get("type") == "NONE"
    # 라벨 글자 흰색·16pt, 행 높이 2830
    info = {cp.get("id"): (cp.get("height"), cp.get("textColor"))
            for cp in hdr.iter(ph.qn("hh", "charPr"))}
    label_run = next(r for r in cells[0].iter(ph.qn("hp", "run")))
    assert info[label_run.get("charPrIDRef")] == ("1600", "#FFFFFF")
    assert cells[0].find(ph.qn("hp", "cellSz")).get("height") == "2830"
    # 멱등
    s2 = ph.process_file(str(p), star=False, spacing=True)
    assert s2["annex_banner"]["fills_set"] == 0 and s2["annex_banner"]["cell_runs_changed"] == 0


# --- R037 배너 제목 셀 양쪽정렬 ---------------------------------------------

def _parapr_aligns(hdr_root):
    aligns = {}
    for pp in hdr_root.iter(ph.qn("hh", "paraPr")):
        al = pp.find(ph.qn("hh", "align"))
        aligns[pp.get("id")] = al.get("horizontal") if al is not None else None
    return aligns


def _banner_cells(sec_root):
    tbl = next(t for t in sec_root.iter(ph.qn("hp", "tbl")))
    return tbl.find(ph.qn("hp", "tr")).findall(ph.qn("hp", "tc"))


def test_annex_banner_title_cell_justify(tmp_path):
    # 제목 셀(3번째) 문단이 CENTER 기반이어도 JUSTIFY로 치환된다 (R037)
    header = HEADER_WITH_HEADLINE.replace('horizontal="JUSTIFY"', 'horizontal="CENTER"')
    p = tmp_path / "bj.hwpx"
    build_hwpx(str(p), header_xml=header, section_xml=BANNER_SECTION)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["annex_banner"]["title_justified"] == 1
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    aligns = _parapr_aligns(hdr)
    cells = _banner_cells(sec)
    # 제목 셀 문단이 JUSTIFY paraPr을 '실참조'하는지 검증 (선언만이 아니라 사용)
    title_p = next(cp for cp in cells[2].iter(ph.qn("hp", "p")))
    assert aligns[title_p.get("paraPrIDRef")] == "JUSTIFY"
    # 라벨('붙 임')·스페이서 셀은 CENTER 현행 유지 (center_cells 배정)
    for tc in cells[:2]:
        for cell_p in tc.iter(ph.qn("hp", "p")):
            assert aligns[cell_p.get("paraPrIDRef")] == "CENTER"
    # 멱등: 재실행 시 추가 치환 없음
    s2 = ph.process_file(str(p), star=False, spacing=True)
    assert s2["annex_banner"]["title_justified"] == 0


def test_annex_banner_title_cell_not_recentered(tmp_path):
    # 기본(JUSTIFY 기반) 문서: center_cells가 배너 제목 셀을 CENTER로 덮어쓰지 않는다
    p = tmp_path / "bj2.hwpx"
    build_hwpx(str(p), header_xml=HEADER_WITH_HEADLINE, section_xml=BANNER_SECTION)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["annex_banner"]["title_justified"] == 0  # 이미 JUSTIFY — 치환 불필요
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    aligns = _parapr_aligns(hdr)
    cells = _banner_cells(sec)
    title_p = next(cp for cp in cells[2].iter(ph.qn("hp", "p")))
    assert aligns[title_p.get("paraPrIDRef")] == "JUSTIFY"


# --- R038 ※·＊ → ㅇ 복귀 전환 간격 6pt ---------------------------------------

def test_cham_star_to_yo_transition_values():
    assert ph.transition_for("cham", "yo") == ("cham_to_yo", 600)
    assert ph.transition_for("star", "yo") == ("star_to_yo", 600)


def test_spacing_cham_to_yo_inserts_6pt(tmp_path):
    # 결함 재현: ※ 단서 문단 바로 다음 ㅇ 문단 — 종전에는 전환 미정의로 간격 0
    section = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 요지1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>※ 도입 후 총소요 산식 단서</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ (판정 규율) 분류가 절감 실적을 좌우</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>＊ 각주 문단</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 요지3</hp:t></hp:run></hp:p>
</hs:sec>
"""
    p = tmp_path / "cham_yo.hwpx"
    build_hwpx(str(p), section_xml=section)
    summary = ph.process_file(str(p), star=False, spacing=True)
    names = [e["transition"] for e in summary["spacing"]["events"]]
    assert names.count("cham_to_yo") == 1
    assert names.count("star_to_yo") == 1
    for e in summary["spacing"]["events"]:
        if e["transition"] in ("cham_to_yo", "star_to_yo"):
            assert e["height"] == 600
    # XML 실사용: ※ 문단과 다음 ㅇ 문단 사이에 6pt(600) 스페이서 문단 존재
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    heights = {cp.get("id"): cp.get("height") for cp in hdr.iter(ph.qn("hh", "charPr"))}
    tops = list(sec)
    texts = [ph.para_text(x).strip() for x in tops]
    idx_yo2 = next(i for i, t in enumerate(texts) if t.startswith("ㅇ (판정 규율)"))
    spacer = tops[idx_yo2 - 1]
    assert ph.para_text(spacer).strip() == ""
    assert heights[spacer.find(ph.qn("hp", "run")).get("charPrIDRef")] == "600"


# --- R039 괄호 13pt — run 경계를 넘는 구간 처리 -------------------------------

HEADER_WITH_BOLD = HEADER_XML.replace(
    "</hh:charProperties>",
    '''<hh:charPr id="2" height="1500" textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="1">
        <hh:fontRef hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>
        <hh:bold/>
      </hh:charPr>
    </hh:charProperties>''').replace(
    '<hh:charProperties itemCnt="2">', '<hh:charProperties itemCnt="3">')


def _charpr_info(hdr_root):
    """charPr id → (height, bold 여부, shadeColor)"""
    info = {}
    for cp in hdr_root.iter(ph.qn("hh", "charPr")):
        info[cp.get("id")] = (cp.get("height"),
                              cp.find(ph.qn("hh", "bold")) is not None,
                              cp.get("shadeColor"))
    return info


def _run_pieces(sec_root):
    """최상위 문단들의 (텍스트, charPrIDRef) run 조각 목록(스페이서 제외)."""
    out = []
    for para in sec_root:
        if para.tag != ph.qn("hp", "p"):
            continue
        for run in para.findall(ph.qn("hp", "run")):
            t = run.find(ph.qn("hp", "t"))
            if t is not None and t.text:
                out.append((t.text, run.get("charPrIDRef")))
    return out


CROSS_RUN_SECTION = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 대상은 (대상 </hp:t></hp:run><hp:run charPrIDRef="2"><hp:t>T1</hp:t></hp:run><hp:run charPrIDRef="0"><hp:t> 등) 서술 계속</hp:t></hp:run></hp:p>
</hs:sec>
"""


def test_paren_small_cross_run_bold_preserved(tmp_path):
    # 결함 재현: 문장 안 볼드(**T1**)로 run이 쪼개져 괄호가 run 경계를 넘는 경우
    p = tmp_path / "paren_cross.hwpx"
    build_hwpx(str(p), header_xml=HEADER_WITH_BOLD, section_xml=CROSS_RUN_SECTION)
    summary = ph.process_file(str(p), star=False, spacing=True)
    ps = summary["paren_small"]
    assert ps["cross_run_skipped"] == 0
    assert ps["paren_spans"] == 1
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    info = _charpr_info(hdr)
    pieces = _run_pieces(sec)
    by_text = {t: cp for t, cp in pieces}
    # 괄호 구간 3조각 전부 13pt, 볼드 run 조각은 13pt+볼드(볼드 보존)
    assert info[by_text["(대상 "]] == ("1300", False, "none")
    assert info[by_text["T1"]] == ("1300", True, "none")
    assert info[by_text[" 등)"]] == ("1300", False, "none")
    # 괄호 밖 조각은 15pt 유지
    assert info[by_text[" 서술 계속"]][0] == "1500"
    assert [t for t, _ in pieces if "ㅇ 대상은" in t]  # 선두 서술 조각 존재


def test_paren_small_cross_run_idempotent(tmp_path):
    p = tmp_path / "paren_idem.hwpx"
    build_hwpx(str(p), header_xml=HEADER_WITH_BOLD, section_xml=CROSS_RUN_SECTION)
    ph.process_file(str(p), star=False, spacing=True)
    s2 = ph.process_file(str(p), star=False, spacing=True)
    assert s2["paren_small"]["paren_spans"] == 0
    assert s2["paren_small"]["cross_run_skipped"] == 0


def test_paren_small_lead_exception_cross_run(tmp_path):
    # R016·R033 예외: ㅇ 선두 괄호 리드는 run이 쪼개져 있어도 15pt 볼드 유지
    section = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ (</hp:t></hp:run><hp:run charPrIDRef="2"><hp:t>판 정</hp:t></hp:run><hp:run charPrIDRef="0"><hp:t>) 분류 기준 서술</hp:t></hp:run></hp:p>
</hs:sec>
"""
    p = tmp_path / "paren_lead.hwpx"
    build_hwpx(str(p), header_xml=HEADER_WITH_BOLD, section_xml=section)
    summary = ph.process_file(str(p), star=False, spacing=True)
    ps = summary["paren_small"]
    assert ps["lead_skipped"] == 1
    assert ps["paren_spans"] == 0
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    info = _charpr_info(hdr)
    for t, cp in _run_pieces(sec):
        assert info[cp][0] == "1500"  # 리드 괄호는 축소되지 않음


def test_paren_small_single_run_still_works(tmp_path):
    section = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 서술 문장(부가 설명) 계속</hp:t></hp:run></hp:p>
</hs:sec>
"""
    p = tmp_path / "paren_single.hwpx"
    build_hwpx(str(p), section_xml=section)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["paren_small"]["paren_spans"] == 1
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    info = _charpr_info(hdr)
    by_text = {t: cp for t, cp in _run_pieces(sec)}
    assert info[by_text["(부가 설명)"]][0] == "1300"
    assert info[by_text[" 계속"]][0] == "1500"


# --- R040 `==문구==` 노란 음영 하이라이트 -------------------------------------

def test_highlight_single_run(tmp_path):
    section = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 핵심은 ==특히 강조== 사항</hp:t></hp:run></hp:p>
</hs:sec>
"""
    p = tmp_path / "hl.hwpx"
    build_hwpx(str(p), section_xml=section)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["highlight"]["highlights"] == 1
    assert summary["highlight"]["shade"] == "#FFFF00"
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec_raw = z.read("Contents/section0.xml").decode()
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    assert "==" not in sec_raw  # 마커 제거 완료
    info = _charpr_info(hdr)
    by_text = {t: cp for t, cp in _run_pieces(sec)}
    # 실측 인코딩(260331 charPr82): shadeColor=#FFFF00 + 볼드, 크기·폰트는 본문 유지
    assert info[by_text["특히 강조"]] == ("1500", True, "#FFFF00")
    assert info[by_text[" 사항"]] == ("1500", False, "none")


def test_highlight_cross_run_bold_inside(tmp_path):
    section = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 앞 ==하이</hp:t></hp:run><hp:run charPrIDRef="2"><hp:t>라이트</hp:t></hp:run><hp:run charPrIDRef="0"><hp:t> 끝== 뒤</hp:t></hp:run></hp:p>
</hs:sec>
"""
    p = tmp_path / "hl_cross.hwpx"
    build_hwpx(str(p), header_xml=HEADER_WITH_BOLD, section_xml=section)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["highlight"]["highlights"] == 1
    assert summary["highlight"]["skipped"] == 0
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec_raw = z.read("Contents/section0.xml").decode()
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    assert "==" not in sec_raw
    info = _charpr_info(hdr)
    by_text = {t: cp for t, cp in _run_pieces(sec)}
    assert info[by_text["하이"]] == ("1500", True, "#FFFF00")
    assert info[by_text["라이트"]] == ("1500", True, "#FFFF00")  # 원래 볼드 run — 볼드 유지+음영
    assert info[by_text[" 끝"]] == ("1500", True, "#FFFF00")
    assert info[by_text[" 뒤"]] == ("1500", False, "none")


def test_highlight_unpaired_left_alone(tmp_path):
    section = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 값 == 비교 서술</hp:t></hp:run></hp:p>
</hs:sec>
"""
    p = tmp_path / "hl_unpaired.hwpx"
    build_hwpx(str(p), section_xml=section)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["highlight"]["highlights"] == 0
    with zipfile.ZipFile(str(p)) as z:
        sec = z.read("Contents/section0.xml").decode()
    assert "값 == 비교 서술" in sec  # 짝 없는 == 는 건드리지 않음


def test_highlight_idempotent(tmp_path):
    section = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 핵심은 ==강조== 사항</hp:t></hp:run></hp:p>
</hs:sec>
"""
    p = tmp_path / "hl_idem.hwpx"
    build_hwpx(str(p), section_xml=section)
    ph.process_file(str(p), star=False, spacing=True)
    s2 = ph.process_file(str(p), star=False, spacing=True)
    assert s2["highlight"]["highlights"] == 0


def test_highlight_inside_table_cell(tmp_path):
    # 마커 잔존 방지: 표 셀 문단도 처리 대상
    section = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 절</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:tbl id="1" rowCnt="1" colCnt="1"><hp:tr><hp:tc><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>셀 ==중요== 값</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
</hs:sec>
"""
    p = tmp_path / "hl_cell.hwpx"
    build_hwpx(str(p), section_xml=section)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["highlight"]["highlights"] == 1
    with zipfile.ZipFile(str(p)) as z:
        sec = z.read("Contents/section0.xml").decode()
    assert "==" not in sec


# --- R041 머리말 배너 앵커 lineSpacing 100%·textWidth 보정 --------------------

BANNER_PAGE_SECTION = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:secPr><hp:pagePr landscape="WIDELY" width="59528" height="84188" gutterType="LEFT_ONLY"><hp:margin header="4252" footer="2835" gutter="0" left="5669" right="5669" top="2835" bottom="4252"/></hp:pagePr></hp:secPr><hp:t> ㅇ 본문</hp:t></hp:run></hp:p>
</hs:sec>
"""


def _header_anchor_and_cells(sec_root):
    """주입된 hp:header에서 (앵커 문단, 배너 표 내부 문단들)을 찾는다."""
    hdr = next(h for h in sec_root.iter(ph.qn("hp", "header")))
    sub = hdr.find(ph.qn("hp", "subList"))
    anchor = next(pp for pp in sub.findall(ph.qn("hp", "p"))
                  if any(r.find(ph.qn("hp", "tbl")) is not None
                         for r in pp.findall(ph.qn("hp", "run"))))
    tbl = next(t for t in anchor.iter(ph.qn("hp", "tbl")))
    cell_ps = list(tbl.iter(ph.qn("hp", "p")))
    return sub, anchor, cell_ps


def _linespacing_values(hdr_root, parapr_id):
    for pp in hdr_root.iter(ph.qn("hh", "paraPr")):
        if pp.get("id") == parapr_id:
            return {ls.get("value") for ls in pp.iter(ph.qn("hh", "lineSpacing"))}
    return set()


def test_header_banner_anchor_linespacing_100_and_textwidth(tmp_path):
    p = tmp_path / "hb.hwpx"
    build_hwpx(str(p), section_xml=BANNER_PAGE_SECTION)
    summary = ph.process_file(str(p), star=False, spacing=False, header_banner=True)
    hbr = summary["header_banner"]
    assert hbr["injected"] == 1
    geo = hbr["geometry"]
    assert geo["linespacing_fixed"] >= 1          # 도너 150% → 100% (hp:switch 양 분기)
    assert geo["textwidth_fixed"] == {"old": "51026", "new": 48190}  # 180mm → 본문 폭 170mm
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    sub, anchor, cell_ps = _header_anchor_and_cells(sec)
    # 앵커 문단이 참조하는 paraPr의 lineSpacing 전 분기 100 (실사용 확인)
    assert _linespacing_values(hdr, anchor.get("paraPrIDRef")) == {"100"}
    # 배너 셀 내부 문단 paraPr(도너 160%)은 그대로 — 앵커만 대상
    for cp in cell_ps:
        assert _linespacing_values(hdr, cp.get("paraPrIDRef")) == {"160"}
    assert sub.get("textWidth") == "48190"


def test_header_banner_exists_path_repairs_legacy(tmp_path):
    # 기주입 문서(앵커 150% 잔존·textWidth 도너값)를 재실행으로 소급 수리
    p = tmp_path / "hb_legacy.hwpx"
    build_hwpx(str(p), section_xml=BANNER_PAGE_SECTION)
    s1 = ph.process_file(str(p), star=False, spacing=False, header_banner=True)
    anchor_pp = s1["header_banner"]["geometry"]["anchor_parapr"]
    # 구버전 주입 상태 재현: 앵커 lineSpacing을 150으로, textWidth를 도너값으로 되돌린 zip 재작성
    with zipfile.ZipFile(str(p)) as z:
        data = {n: z.read(n) for n in z.namelist()}
        names = z.namelist()
    hdr_txt = data["Contents/header.xml"].decode()
    m = re.search(rf'(<hh:paraPr id="{anchor_pp}".*?</hh:paraPr>)', hdr_txt, re.S)
    legacy_block = m.group(1).replace('value="100"', 'value="150"')
    data["Contents/header.xml"] = hdr_txt.replace(m.group(1), legacy_block).encode()
    data["Contents/section0.xml"] = data["Contents/section0.xml"].replace(
        b'textWidth="48190"', b'textWidth="51026"')
    with zipfile.ZipFile(str(p), "w") as z:
        for n in names:
            z.writestr(n, data[n])
    s2 = ph.process_file(str(p), star=False, spacing=False, header_banner=True)
    hbr = s2["header_banner"]
    assert hbr["injected"] == 0 and hbr["reason"] == "header_exists"
    geo = hbr["geometry"]
    assert geo["anchor_parapr"] == anchor_pp
    assert geo["linespacing_fixed"] == 2          # hp:case·hp:default 두 분기 150→100
    assert geo["textwidth_fixed"] == {"old": "51026", "new": 48190}
    assert s2["changed"] is True
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    sub, anchor, _ = _header_anchor_and_cells(sec)
    assert _linespacing_values(hdr, anchor.get("paraPrIDRef")) == {"100"}
    assert sub.get("textWidth") == "48190"


def test_header_banner_idempotent_geometry(tmp_path):
    p = tmp_path / "hb_idem.hwpx"
    build_hwpx(str(p), section_xml=BANNER_PAGE_SECTION)
    ph.process_file(str(p), star=False, spacing=False, header_banner=True)
    s2 = ph.process_file(str(p), star=False, spacing=False, header_banner=True)
    hbr = s2["header_banner"]
    assert hbr["injected"] == 0
    assert hbr["geometry"]["linespacing_fixed"] == 0
    assert hbr["geometry"]["textwidth_fixed"] is None


# ── apply_fit_page_width (R036·R042) ────────────────────────────────────────
# 본문 폭 48190 (59528 - 5669*2, KCA 좌우 20mm 규격)

def _fit_section(tables_xml):
    return ET.fromstring(f"""<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="{NS['hs']}" xmlns:hp="{NS['hp']}" xmlns:hc="{NS['hc']}">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:secPr><hp:pagePr landscape="WIDELY" width="59528" height="84188" gutterType="LEFT_ONLY"><hp:margin header="4251" footer="2835" gutter="0" left="5669" right="5669" top="2834" bottom="4252"/></hp:pagePr></hp:secPr><hp:t>발신</hp:t></hp:run></hp:p>
  {tables_xml}
</hs:sec>""")


def _fit_tbl(tid, width, om_l, om_r, cells, extra=""):
    tcs = "".join(
        f'<hp:tc><hp:cellSz width="{w}" height="1000"/><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0">'
        f'<hp:run charPrIDRef="0"><hp:t>셀</hp:t></hp:run></hp:p></hp:subList></hp:tc>' for w in cells)
    return (f'<hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0">'
            f'<hp:tbl id="{tid}" rowCnt="1" colCnt="{len(cells)}">'
            f'<hp:sz width="{width}" height="1000"/>'
            f'<hp:outMargin left="{om_l}" right="{om_r}" top="0" bottom="0"/>'
            f'<hp:tr>{tcs}</hp:tr>{extra}</hp:tbl></hp:run></hp:p>')


def _tbl_metrics(sec, tid):
    for tbl in sec.iter(ph.qn("hp", "tbl")):
        if tbl.get("id") == tid:
            sz = int(tbl.find(ph.qn("hp", "sz")).get("width"))
            om = tbl.find(ph.qn("hp", "outMargin"))
            om_l, om_r = int(om.get("left")), int(om.get("right"))
            cells = [int(tc.find(ph.qn("hp", "cellSz")).get("width"))
                     for tc in tbl.find(ph.qn("hp", "tr")).findall(ph.qn("hp", "tc"))]
            return sz, om_l + om_r, cells
    raise AssertionError(f"tbl {tid} not found")


TEXT_W = 48190


def test_fit_page_width_exact_match_gets_slack():
    """R042 핵심: 총 폭 == 본문 폭(slack 0)도 축소 대상 — '이내'가 아니라 '미만'."""
    # 20260728건 실측 재현: 제목표 sz 47624 + outMargin 283+283 = 48190 == 본문 폭
    sec = _fit_section(_fit_tbl("9300001", 47624, 283, 283, [47624]))
    r = ph.apply_fit_page_width([sec])
    assert r["tables_fitted"] == 1
    sz, om, cells = _tbl_metrics(sec, "9300001")
    total = sz + om
    assert total < TEXT_W                       # 총 폭이 본문 폭과 같아지지 않는다
    assert TEXT_W - total >= ph.FIT_PAGE_SLACK  # slack ≥ 566 확보
    assert sum(cells) == sz                     # 셀 폭 합 == 표 sz (한글 재계산 방지)


def test_fit_page_width_overflow_lands_below_text_width():
    """폭 초과 표(R036 원래 대상)도 이제 본문 폭 '미만'으로 착지한다."""
    sec = _fit_section(_fit_tbl("1", 50737, 141, 141, [23953, 26784]))
    r = ph.apply_fit_page_width([sec])
    assert r["tables_fitted"] == 1
    sz, om, cells = _tbl_metrics(sec, "1")
    assert sz + om == TEXT_W - ph.FIT_PAGE_SLACK
    assert sz + om < TEXT_W
    assert sum(cells) == sz


def test_fit_page_width_keeps_tables_with_enough_slack():
    """이미 여유가 충분한 본문 표(slack 1801)는 건드리지 않는다."""
    sec = _fit_section(_fit_tbl("1001", 46389, 0, 0, [5927, 13999, 26463]))
    r = ph.apply_fit_page_width([sec])
    assert r["tables_fitted"] == 0
    assert _tbl_metrics(sec, "1001") == (46389, 0, [5927, 13999, 26463])


def test_fit_page_width_idempotent():
    """1회 축소 후 재실행은 무변경 — slack이 정확히 FIT_PAGE_SLACK이어도 재축소하지 않는다."""
    sec = _fit_section(_fit_tbl("1", 47624, 283, 283, [47624]))
    ph.apply_fit_page_width([sec])
    first = _tbl_metrics(sec, "1")
    r2 = ph.apply_fit_page_width([sec])
    assert r2["tables_fitted"] == 0
    assert _tbl_metrics(sec, "1") == first


PIC_XML = (
    '<hp:pic id="9700002" zOrder="2"><hp:offset x="0" y="0"/>'
    '<hp:orgSz width="60000" height="7980"/><hp:curSz width="14315" height="1905"/>'
    '<hp:rotationInfo angle="0" centerX="7157" centerY="952" rotateimage="1"/>'
    '<hp:renderingInfo><hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
    '<hc:scaMatrix e1="0.238583" e2="0" e3="0" e4="0" e5="0.238722" e6="0"/>'
    '<hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/></hp:renderingInfo>'
    '<hp:sz width="14315" widthRelTo="ABSOLUTE" height="1905" heightRelTo="ABSOLUTE" protect="0"/>'
    '</hp:pic>')


def test_fit_page_width_rescales_pic_derived_cache():
    """R042 위생: 그림 축소 시 scaMatrix e1/e5·rotationInfo center를 curSz에서 재계산한다."""
    # 도너 배너 재현: 표 50737+141*2 → 초과, 내부 pic curSz 14315×1905 (scaMatrix는 도너 원값)
    sec = _fit_section(_fit_tbl("9700001", 50737, 141, 141, [23953, 26784], extra=PIC_XML))
    r = ph.apply_fit_page_width([sec])
    assert r["tables_fitted"] == 1 and r["detail"][0]["pics_scaled"] == 1
    pic = next(sec.iter(ph.qn("hp", "pic")))
    cur = pic.find(ph.qn("hp", "curSz"))
    cw, ch = int(cur.get("width")), int(cur.get("height"))
    ratio = r["detail"][0]["ratio"]
    assert cw == int(round(14315 * ratio)) and ch == int(round(1905 * ratio))
    sz = pic.find(ph.qn("hp", "sz"))
    assert (int(sz.get("width")), int(sz.get("height"))) == (cw, ch)
    sca = pic.find(ph.qn("hp", "renderingInfo")).find(ph.qn("hc", "scaMatrix"))
    assert sca.get("e1") == f"{cw / 60000:.6f}"   # 스테일 도너값 0.238583이 아니라 curSz/orgSz
    assert sca.get("e5") == f"{ch / 7980:.6f}"
    rot = pic.find(ph.qn("hp", "rotationInfo"))
    assert (rot.get("centerX"), rot.get("centerY")) == (str(cw // 2), str(ch // 2))
    # 위치 파생이 아닌 항목은 불변: transMatrix는 그대로
    trans = pic.find(ph.qn("hp", "renderingInfo")).find(ph.qn("hc", "transMatrix"))
    assert trans.get("e3") == "0" and trans.get("e6") == "0"


# --- R031 서술 중 ＊ 위첨자 ---------------------------------------------------
# rules-seed.md R031: "본문 서술 중 용어 뒤 ＊ 표지는 위첨자 — charPr에 <hh:supscript/>
# 자식 추가한 복제본으로 run 분리(높이·offset은 유지). 하단 `＊ 용어 : 설명` 각주 문단
# (선두 ＊)은 평문 유지(R011 참고 charPr 13pt 그대로)."

def _charpr_supscript(hdr_root):
    """charPr id → <hh:supscript/> 자식 보유 여부"""
    return {cp.get("id"): cp.find(ph.qn("hh", "supscript")) is not None
            for cp in hdr_root.iter(ph.qn("hh", "charPr"))}


def _charpr_by_id(hdr_root):
    return {cp.get("id"): cp for cp in hdr_root.iter(ph.qn("hh", "charPr"))}


def _runs_of_para(sec_root, lead):
    """텍스트가 lead로 시작하는 첫 문단(표 셀 내부 포함)의 (텍스트, charPrIDRef) run 목록."""
    for para in sec_root.iter(ph.qn("hp", "p")):
        if ph.para_text(para).strip().startswith(lead):
            return [(r.find(ph.qn("hp", "t")).text, r.get("charPrIDRef"))
                    for r in para.findall(ph.qn("hp", "run"))
                    if r.find(ph.qn("hp", "t")) is not None]
    raise AssertionError(f"문단을 찾지 못함: {lead!r}")


SUPSCRIPT_SECTION = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 제목1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 바이브코딩＊ 도입 확대</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>＊ 바이브코딩 : AI 보조 개발 방식</hp:t></hp:run></hp:p>
</hs:sec>
"""


def test_superscript_star_splits_run_and_keeps_footnote_plain(tmp_path):
    """R031 정상 동작 + 예외: 서술 중 ＊만 위첨자 run으로 분리, 선두 ＊ 각주 문단은 평문."""
    p = tmp_path / "sup.hwpx"
    build_hwpx(str(p), section_xml=SUPSCRIPT_SECTION)
    summary = ph.process_file(str(p), star=False, spacing=True)
    # 각주 문단의 ＊는 세지 않는다 — 서술 중 1개만
    assert summary["superscript_star"]["stars_superscripted"] == 1
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    sup = _charpr_supscript(hdr)
    cps = _charpr_by_id(hdr)

    # (1) 서술 문단: ＊ 앞뒤가 쪼개져 3조각, 가운데 ＊ run만 위첨자 charPr
    body = _runs_of_para(sec, "ㅇ 바이브코딩")
    assert [t for t, _ in body] == [" ㅇ 바이브코딩", "＊", " 도입 확대"]  # R025 1칸 들여쓰기 포함
    assert sup[body[1][1]] is True
    assert sup[body[0][1]] is False and sup[body[2][1]] is False
    assert body[0][1] == body[2][1] == "0"  # 앞뒤 조각은 본문 charPr 그대로

    # (2) 위첨자 charPr은 본문 charPr의 복제본 — height·offset·fontRef 유지, id만 신규
    base_cp, sup_cp = cps["0"], cps[body[1][1]]
    assert body[1][1] != "0"
    assert sup_cp.get("height") == base_cp.get("height") == "1500"
    assert (sup_cp.find(ph.qn("hh", "offset")).attrib
            == base_cp.find(ph.qn("hh", "offset")).attrib)
    assert (sup_cp.find(ph.qn("hh", "fontRef")).attrib
            == base_cp.find(ph.qn("hh", "fontRef")).attrib)

    # (3) 각주 문단(선두 ＊)은 run 분리도 위첨자 charPr 배정도 없음 — 평문 유지
    foot = _runs_of_para(sec, "＊ 바이브코딩")
    assert len(foot) == 1
    assert foot[0][0] == "     ＊ 바이브코딩 : AI 보조 개발 방식"  # R025 5칸만 붙음
    assert sup[foot[0][1]] is False


def test_superscript_star_inside_table_cell(tmp_path):
    """apply_superscript_star docstring: '표 셀 내부 문단도 동일 처리'."""
    section = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 제목1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:tbl id="1" rowCnt="1" colCnt="1"><hp:tr><hp:tc><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>구축＊ 완료</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
</hs:sec>
"""
    p = tmp_path / "sup_cell.hwpx"
    build_hwpx(str(p), section_xml=section)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["superscript_star"]["stars_superscripted"] == 1
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    sup = _charpr_supscript(hdr)
    cps = _charpr_by_id(hdr)
    cell = _runs_of_para(sec, "구축")
    assert [t for t, _ in cell] == ["구축", "＊", " 완료"]
    assert sup[cell[1][1]] is True
    assert sup[cell[0][1]] is False and sup[cell[2][1]] is False
    # 뒤이어 도는 R023(셀 12pt)이 위첨자 속성을 지우지 않는다 — 복제본에 supscript 보존
    assert [cps[cid].get("height") for _, cid in cell] == ["1200", "1200", "1200"]


def test_superscript_star_idempotent(tmp_path):
    """2회 실행해도 ＊ run이 다시 쪼개지지 않고 텍스트도 보존된다."""
    p = tmp_path / "sup_idem.hwpx"
    build_hwpx(str(p), section_xml=SUPSCRIPT_SECTION)
    s1 = ph.process_file(str(p), star=False, spacing=True)
    assert s1["superscript_star"]["stars_superscripted"] == 1
    with zipfile.ZipFile(str(p)) as z:
        hdr1 = ET.fromstring(z.read("Contents/header.xml"))
        first = _runs_of_para(ET.fromstring(z.read("Contents/section0.xml")), "ㅇ 바이브코딩")
    assert [t for t, _ in first] == [" ㅇ 바이브코딩", "＊", " 도입 확대"]  # 1회차에 이미 분리됨
    sup_id = first[1][1]
    assert _charpr_supscript(hdr1)[sup_id] is True
    n_charpr_1 = len(list(hdr1.iter(ph.qn("hh", "charPr"))))

    s2 = ph.process_file(str(p), star=False, spacing=True)
    assert s2["superscript_star"]["stars_superscripted"] == 0
    with zipfile.ZipFile(str(p)) as z:
        hdr2 = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    # run 재분리도, 위첨자 charPr 재생성도 없다
    assert _runs_of_para(sec, "ㅇ 바이브코딩") == first
    assert len(list(hdr2.iter(ph.qn("hh", "charPr")))) == n_charpr_1
    assert "".join(t for t, _ in _runs_of_para(sec, "ㅇ 바이브코딩")) == " ㅇ 바이브코딩＊ 도입 확대"


# --- R032 본문 계층 양쪽 정렬 -------------------------------------------------
# rules-seed.md R032: "본문 계층 문단(□·ㅇ·대시)은 양쪽 정렬(JUSTIFY) — 우측 들쭉날쭉
# 방지. ＊·※ 각주·표 캡션·발신 줄은 기존 정렬 유지."

HEADER_LEFT = HEADER_XML.replace('<hh:align horizontal="JUSTIFY"',
                                 '<hh:align horizontal="LEFT"')

JUSTIFY_SECTION = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>&lt; '26. 1. 1.(목), 테스트팀 &gt;</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 제목1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>ㅇ 요지1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>- 상세1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>＊ 각주1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>※ 참고1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>[ 표 제목 ]</hp:t></hp:run></hp:p>
</hs:sec>
"""


def _para_align_by_text(hdr_root, sec_root):
    """최상위 텍스트 문단 → {문단 텍스트(strip): 그 문단 paraPr의 align horizontal}"""
    aligns = {}
    for pp in hdr_root.iter(ph.qn("hh", "paraPr")):
        el = pp.find(ph.qn("hh", "align"))
        aligns[pp.get("id")] = el.get("horizontal") if el is not None else None
    out = {}
    for para in sec_root:
        if para.tag != ph.qn("hp", "p"):
            continue
        text = ph.para_text(para).strip()
        if not text:            # 스페이서·표 래퍼 문단 제외
            continue
        out[text] = aligns.get(para.get("paraPrIDRef"))
    return out


def test_body_justify_only_hierarchy_kinds(tmp_path):
    """□·ㅇ·대시·※·＊가 JUSTIFY로 바뀌고 캡션·발신 줄 정렬은 건드리지 않는다 (R061)."""
    p = tmp_path / "justify.hwpx"
    build_hwpx(str(p), header_xml=HEADER_LEFT, section_xml=JUSTIFY_SECTION)
    summary = ph.process_file(str(p), star=False, spacing=True)
    bj = summary["body_justify"]
    assert bj["found"] == 5      # □1 · ㅇ1 · -1 · ※1 · ＊1 (R061)
    assert bj["changed"] == 5    # LEFT → JUSTIFY 복제 배정 (※·＊ 포함)
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    aligns = _para_align_by_text(hdr, sec)
    assert aligns["□ 제목1"] == "JUSTIFY"
    assert aligns["ㅇ 요지1"] == "JUSTIFY"
    assert aligns["- 상세1"] == "JUSTIFY"
    assert aligns["※ 참고1"] == "JUSTIFY"   # R061
    assert aligns["＊ 각주1"] == "JUSTIFY"   # R061 — ＊도 ※와 동일 처리
    assert aligns["※ 참고1"] == "JUSTIFY"  # R061 — ※도 양쪽 정렬
    # 예외: 발신 줄도 기존 정렬 유지
    assert aligns["< '26. 1. 1.(목), 테스트팀 >"] == "LEFT"
    # 예외: 표 캡션은 R015가 배정한 CENTER를 유지(JUSTIFY로 덮어쓰지 않음)
    assert aligns["[ 표 제목 ]"] == "CENTER"


def test_body_justify_noop_when_already_justify(tmp_path):
    """이미 JUSTIFY인 paraPr은 복제 없이 그대로 — found는 세고 changed는 0."""
    p = tmp_path / "justify_noop.hwpx"
    build_hwpx(str(p), section_xml=JUSTIFY_SECTION)   # 기본 HEADER_XML = JUSTIFY
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["body_justify"] == {"found": 5, "changed": 0}  # ※·＊ 포함 (R061)
    with zipfile.ZipFile(str(p)) as z:
        hdr = ET.fromstring(z.read("Contents/header.xml"))
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    aligns = _para_align_by_text(hdr, sec)
    assert aligns["□ 제목1"] == aligns["ㅇ 요지1"] == aligns["- 상세1"] == "JUSTIFY"
    assert aligns["＊ 각주1"] == aligns["※ 참고1"] == "JUSTIFY"  # 원래 정렬 그대로 보존


def test_body_justify_idempotent(tmp_path):
    """재실행 시 새 paraPr을 또 만들지 않는다(멱등)."""
    p = tmp_path / "justify_idem.hwpx"
    build_hwpx(str(p), header_xml=HEADER_LEFT, section_xml=JUSTIFY_SECTION)
    ph.process_file(str(p), star=False, spacing=True)
    with zipfile.ZipFile(str(p)) as z:
        hdr1 = ET.fromstring(z.read("Contents/header.xml"))
        sec1 = ET.fromstring(z.read("Contents/section0.xml"))
    before_ids = [pp.get("id") for pp in hdr1.iter(ph.qn("hh", "paraPr"))]
    before = _para_align_by_text(hdr1, sec1)
    s2 = ph.process_file(str(p), star=False, spacing=True)
    assert s2["body_justify"] == {"found": 5, "changed": 0}  # ※·＊ 포함 (R061)
    with zipfile.ZipFile(str(p)) as z:
        hdr2 = ET.fromstring(z.read("Contents/header.xml"))
        sec2 = ET.fromstring(z.read("Contents/section0.xml"))
    assert [pp.get("id") for pp in hdr2.iter(ph.qn("hh", "paraPr"))] == before_ids
    assert _para_align_by_text(hdr2, sec2) == before


# --- 계층 글자 크기 재강제 (FORM_SIZES_PT) -----------------------------------
# 근거: '26.9.8 실측 — kordoc generate_document가 sizes.dae·sizes.bodyTitle을 무시하고
# □ 17pt·대시 14pt·제목 23~25pt로 산출한 회귀. 후처리가 양식 값으로 되돌려야 한다.

FORM_SIZES_SECTION_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:tbl id="1" rowCnt="1" colCnt="1" borderFillIDRef="2"><hp:tr><hp:tc borderFillIDRef="2"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="3"><hp:t>문서 제목</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="4"><hp:t>□ 추진 배경</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t> ㅇ 요지 문장</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="5"><hp:t>   - 상세 문장</hp:t></hp:run></hp:p>
</hs:sec>
"""


def _charpr_xml(cid, height):
    return (
        f'<hh:charPr id="{cid}" height="{height}" textColor="#000000" shadeColor="none" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="2">'
        '<hh:fontRef hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
        '<hh:ratio hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
        '<hh:spacing hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/>'
        '<hh:relSz hangul="100" latin="100" hanja="100" japanese="100" other="100" symbol="100" user="100"/>'
        '<hh:offset hangul="0" latin="0" hanja="0" japanese="0" other="0" symbol="0" user="0"/></hh:charPr>'
    )


def _form_sizes_header():
    # charPr 3=제목 2300 · 4=□ 1700 · 5=대시 1400 (kordoc 회귀 산출값)
    extra = "".join(_charpr_xml(cid, h)
                    for cid, h in (("3", "2300"), ("4", "1700"), ("5", "1400")))
    return HEADER_XML.replace("</hh:charProperties>", extra + "</hh:charProperties>")


def _heights_by_text(path):
    import xml.etree.ElementTree as _ET
    with zipfile.ZipFile(path) as z:
        hdr = _ET.fromstring(z.read("Contents/header.xml"))
        sec = z.read("Contents/section0.xml").decode()
    heights = {cp.get("id"): int(cp.get("height"))
               for cp in hdr.iter(ph.qn("hh", "charPr"))}
    out = {}
    for m in re.finditer(r'charPrIDRef="(\d+)"><hp:t>([^<]*)</hp:t>', sec):
        out[m.group(2)] = heights.get(m.group(1))
    return out


def test_form_sizes_restores_form_values(tmp_path):
    p = tmp_path / "form_sizes.hwpx"
    build_hwpx(str(p), header_xml=_form_sizes_header(),
               section_xml=FORM_SIZES_SECTION_XML)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["form_sizes"]["runs_changed"] > 0
    assert summary["form_sizes"]["title_runs_changed"] == 1
    h = _heights_by_text(str(p))
    assert h["문서 제목"] == ph.TITLE_BOX_SIZE_PT * 100 == 2000
    assert h["□ 추진 배경"] == ph.FORM_SIZES_PT["dae"] * 100 == 1500
    assert h["   - 상세 문장"] == ph.FORM_SIZES_PT["dash"] * 100 == 1500


def test_form_sizes_is_idempotent(tmp_path):
    p = tmp_path / "form_sizes_idem.hwpx"
    build_hwpx(str(p), header_xml=_form_sizes_header(),
               section_xml=FORM_SIZES_SECTION_XML)
    ph.process_file(str(p), star=False, spacing=True)
    second = ph.process_file(str(p), star=False, spacing=True)
    assert second["form_sizes"]["runs_changed"] == 0
    assert second["form_sizes"]["title_runs_changed"] == 0


# --- 열 폭 재배분 (apply_table_column_fit) ------------------------------------
# 근거: '26.9.8 실측 — 3열 표에서 내용량이 가장 많은 열이 가장 좁게 산출돼 행 높이가
# 불어나고 표가 페이지를 넘겼다. 총 폭은 유지한 채 내용량 비례로 되돌린다.

def _column_fit_section(widths, texts):
    cells = []
    for row_i, row in enumerate(texts):
        tcs = "".join(
            f'<hp:tc borderFillIDRef="2"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0">'
            f'<hp:run charPrIDRef="0"><hp:t>{cell}</hp:t></hp:run></hp:p></hp:subList>'
            f'<hp:cellAddr colAddr="{c}" rowAddr="{row_i}"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
            f'<hp:cellSz width="{widths[c]}" height="1000"/></hp:tc>'
            for c, cell in enumerate(row))
        cells.append(f"<hp:tr>{tcs}</hp:tr>")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n'
            '<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
            'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">\n'
            '  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0">'
            '<hp:t>□ 절</hp:t></hp:run></hp:p>\n'
            '  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0">'
            f'<hp:tbl id="1" rowCnt="{len(texts)}" colCnt="{len(widths)}" borderFillIDRef="2">'
            f'<hp:sz width="{sum(widths)}" height="2000"/>'
            '<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
            + "".join(cells) +
            '</hp:tbl></hp:run></hp:p>\n</hs:sec>\n')


def test_table_pagination_sets_placement_attrs(tmp_path):
    """표에 본문 자리 차지 배치를 보장한다 — 없으면 페이지 분할이 듣지 않는다 (R063).

    회귀 대상: kordoc 산출 표에는 textWrap·textFlow·lock이 아예 없다(인도본 17건 실측
    246개 중 218개 누락). 배치가 정해지지 않으면 한글이 표를 본문 흐름 밖 개체로 다뤄
    경계에서 나누지 않고 통째로 다음 장으로 민다 — pageBreak=CELL만으로는 듣지 않는다."""
    p = tmp_path / "placement.hwpx"
    build_hwpx(str(p), section_xml=_column_fit_section(
        [9000, 24000, 15000], [["구 분", "주 제", "내 용"], ["a", "b", "c"]]))
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["table_pagination"]["attrs_fixed"] > 0
    with zipfile.ZipFile(p) as z:
        sec = ET.fromstring(z.read("Contents/section0.xml"))
    for tbl in sec.iter(ph.qn("hp", "tbl")):
        for attr, value in ph.TABLE_PLACEMENT.items():
            assert tbl.get(attr) == value, f"{attr} 미설정"
        assert tbl.get("pageBreak") == "CELL"


def test_table_pagination_keeps_existing_placement(tmp_path):
    """이미 배치가 잡힌 표(한컴 저장본·기관 양식)는 그 값을 존중한다 — 없을 때만 채운다."""
    sec = _column_fit_section([9000, 24000, 15000],
                              [["구 분", "주 제", "내 용"], ["a", "b", "c"]])
    sec = sec.replace("<hp:tbl ", '<hp:tbl textWrap="SQUARE" ', 1)
    p = tmp_path / "placement_keep.hwpx"
    build_hwpx(str(p), section_xml=sec)
    ph.process_file(str(p), star=False, spacing=True)
    with zipfile.ZipFile(p) as z:
        root = ET.fromstring(z.read("Contents/section0.xml"))
    assert next(root.iter(ph.qn("hp", "tbl"))).get("textWrap") == "SQUARE"


def test_column_fit_reverses_inverted_widths(tmp_path):
    # 내용이 가장 긴 3열이 가장 좁게 잡힌 표 — 재배분 후 3열이 가장 넓어야 한다
    widths = [9000, 24000, 15000]
    texts = [["구 분", "주 제", "내 용"],
             ["도입", "짧은 주제", "아주 긴 내용이 들어가는 열이며 실제로 여러 줄을 차지한다" * 2]]
    p = tmp_path / "colfit.hwpx"
    build_hwpx(str(p), section_xml=_column_fit_section(widths, texts))
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["column_fit"]["tables_fitted"] == 1
    after = summary["column_fit"]["detail"][0]["after"]
    assert sum(after) == sum(widths)          # 표 총 폭 불변
    assert after[2] == max(after)             # 내용 열이 가장 넓다
    assert after[0] == min(after)             # 구분 열이 가장 좁다


def test_column_fit_does_not_narrow_the_content_column(tmp_path):
    """이미 내용 열이 넓게 잡힌 표를 좁히면 안 된다 — 정률 상한이 만든 역주행 회귀.

    `구 분 | 담당 | 내 용` 표는 기관 보고서의 전형인데, 종전 상한 60%가 kordoc이 이미
    74%를 준 내용 열을 끌어내리고 그만큼을 라벨 열에 얹었다('26.9.10 실측 35315→28515).
    내용 비례 배분이 목적인 단계가 정률 상한과 싸운 것이다. 지금은 하한이 '가장 긴 셀이
    한 줄에 들어갈 폭'이고 상한은 다른 열의 하한 합에서 자연히 생긴다 — 적정한 표는
    아예 손대지 않는 것이 정답이다."""
    widths = [4144, 8064, 35315]
    texts = [["구 분", "담당", "내 용"],
             ["도입", "기획팀", "기관 내부 업무 처리 절차를 단계별로 나누어 점검하고 병목 구간을 개선 과제로 정리"],
             ["확산", "데이터전략팀", "시범 적용 결과를 바탕으로 적용 범위를 넓히며 담당자 교육과 매뉴얼 정비를 함께 추진"]]
    p = tmp_path / "colfit_wide.hwpx"
    build_hwpx(str(p), section_xml=_column_fit_section(widths, texts))
    summary = ph.process_file(str(p), star=False, spacing=True)
    detail = summary["column_fit"]["detail"]
    after = detail[0]["after"] if detail else widths
    assert after[2] >= widths[2], "내용 열이 오히려 좁아졌다"
    assert after[2] == max(after)


def test_column_floors_keep_longest_cell_on_one_line():
    """열 하한은 그 열에서 가장 긴 셀이 한 줄에 들어갈 폭이다.

    회귀 대상: 하한을 머리글로만 잡아 `과제 10`이 `과제`/`10`으로, `No`가 `N`/`o`로
    쪼개졌다('26.9.10 렌더 실측). _weighted_len은 줄 길이 판정용(ASCII 0.5)이라
    열 폭 하한에 쓰면 영문 머리글을 과소평가한다."""
    section = _column_fit_section([3627, 5878, 38018],
                                  [["No", "과제명", "내 용"],
                                   ["1", "과제 1", "긴 서술" * 20],
                                   ["20", "과제 10", "긴 서술" * 20]])
    root = ET.fromstring(section)
    tbl = next(t for t, _ in ph._iter_content_tables([root]))
    rows = tbl.findall(ph.qn("hp", "tr"))
    total = 3627 + 5878 + 38018
    floors = ph._column_floors(rows, 3, total)
    assert floors[0] * total >= ph._cell_width_hu("No") + ph.COL_FIT_CELL_PAD
    assert floors[1] * total >= ph._cell_width_hu("과제 10") + ph.COL_FIT_CELL_PAD
    assert floors[2] == ph.COL_FIT_FLOOR_MAX, "긴 서술 열의 하한은 상한선에서 잘린다"
    shares = ph._fit_shares([1.0, 3.5, 47.0], floors)
    assert abs(sum(shares) - 1.0) < 1e-9
    assert all(sh >= f - 1e-9 for sh, f in zip(shares, floors))
    assert shares[2] == max(shares)


def test_column_fit_is_idempotent(tmp_path):
    widths = [9000, 24000, 15000]
    texts = [["구 분", "주 제", "내 용"],
             ["도입", "짧은 주제", "아주 긴 내용이 들어가는 열" * 3]]
    p = tmp_path / "colfit_idem.hwpx"
    build_hwpx(str(p), section_xml=_column_fit_section(widths, texts))
    ph.process_file(str(p), star=False, spacing=True)
    second = ph.process_file(str(p), star=False, spacing=True)
    assert second["column_fit"]["tables_fitted"] == 0


def test_column_fit_skips_merged_tables(tmp_path):
    sec = _column_fit_section([9000, 24000, 15000],
                              [["구 분", "주 제", "내 용"], ["a", "b", "c" * 40]])
    sec = sec.replace('<hp:cellSpan colSpan="1" rowSpan="1"/>',
                      '<hp:cellSpan colSpan="2" rowSpan="1"/>', 1)
    p = tmp_path / "colfit_merged.hwpx"
    build_hwpx(str(p), section_xml=sec)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["column_fit"]["tables_fitted"] == 0


# --- 제목 박스 원형 복원 (apply_title_box_form) --------------------------------
# 근거: 양식 실측 3건(이음5G '26.7.30 · cert-poc '26.8.3 · xmos '26.8.7) 동일 —
# 3행 1열, 0행 단색 #0080C0 · 2행 방사형 그라데이션 #0080C0→#3CBFFF.
# kordoc이 '26.9월 1행(상·하 실선·채움 없음)으로 바꾸며 파란 띠가 사라진 회귀.

ONE_ROW_TITLE_SECTION = '''<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:tbl id="1" rowCnt="1" colCnt="1" borderFillIDRef="1"><hp:sz width="47907" height="4084"/><hp:outMargin left="0" right="0" top="0" bottom="600"/><hp:tr><hp:tc borderFillIDRef="1"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>문서 제목</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/><hp:cellSz width="47907" height="4084"/></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 절</hp:t></hp:run></hp:p>
</hs:sec>
'''


def _title_box_rows(path):
    import xml.etree.ElementTree as _ET
    with zipfile.ZipFile(path) as z:
        sec = _ET.fromstring(z.read("Contents/section0.xml"))
        hdr = _ET.fromstring(z.read("Contents/header.xml"))
    tbl = next(t for t in sec.iter(ph.qn("hp", "tbl")))
    fills = {bf.get("id"): bf for bf in hdr.iter(ph.qn("hh", "borderFill"))}
    out = []
    for tr in tbl.findall(ph.qn("hp", "tr")):
        tc = tr.find(ph.qn("hp", "tc"))
        sz = tc.find(ph.qn("hp", "cellSz"))
        bf = fills[tc.get("borderFillIDRef")]
        fill = bf.find(ph.qn("hc", "fillBrush"))
        kind = None
        if fill is not None:
            kind = "gradation" if fill.find(ph.qn("hc", "gradation")) is not None else "winBrush"
        out.append((int(sz.get("height")), kind))
    return tbl, out


def test_title_box_form_restores_blue_bands(tmp_path):
    p = tmp_path / "title_form.hwpx"
    build_hwpx(str(p), section_xml=ONE_ROW_TITLE_SECTION)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["title_box_form"]["restored"] == 1
    tbl, rows = _title_box_rows(str(p))
    assert tbl.get("rowCnt") == "3"
    assert [h for h, _ in rows] == [ph.TITLE_BOX_BAND_HEIGHT,
                                    ph.TITLE_BOX_TITLE_HEIGHT,
                                    ph.TITLE_BOX_BAND_HEIGHT]
    assert [k for _, k in rows] == ["winBrush", None, "gradation"]
    # 총 폭(sz + outMargin 좌우) 불변 — 47907
    sz = tbl.find(ph.qn("hp", "sz"))
    out = tbl.find(ph.qn("hp", "outMargin"))
    assert (int(sz.get("width")) + int(out.get("left")) + int(out.get("right"))) == 47907
    assert out.get("left") == out.get("right") == str(ph.TITLE_BOX_SIDE_MARGIN)


def test_title_box_form_is_idempotent(tmp_path):
    p = tmp_path / "title_form_idem.hwpx"
    build_hwpx(str(p), section_xml=ONE_ROW_TITLE_SECTION)
    ph.process_file(str(p), star=False, spacing=True)
    second = ph.process_file(str(p), star=False, spacing=True)
    assert second["title_box_form"]["restored"] == 0
    _, rows = _title_box_rows(str(p))
    assert [k for _, k in rows] == ["winBrush", None, "gradation"]


def test_title_box_form_keeps_gradient_through_borderless(tmp_path):
    """복원된 밴드의 그라데이션이 뒤이은 borderless 처리에서 살아남는다."""
    p = tmp_path / "title_form_keep.hwpx"
    build_hwpx(str(p), section_xml=ONE_ROW_TITLE_SECTION)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["title_box"]["fills_replaced"] == 0   # 이미 4변 NONE → 재교체 없음
    _, rows = _title_box_rows(str(p))
    assert rows[2][1] == "gradation"


# --- 제목 박스 판정 정밀화 ('26.9.10) -----------------------------------------
# 종전 판정은 "첫 □ 문단 이전의 표 전부 = 제목 박스"였다. kordoc 보고서 산출물은 그
# 구간에 요약 박스(1행 1열 #DFE6F7)·문서정보표·장 배너를 함께 싣기 때문에 요약 박스가
# 제목 박스로 개조돼 음영을 잃고 20pt로 부풀었다('26.9.10 실측 재현).

SUMMARY_FILL_HEADER = HEADER_XML.replace(
    "</hh:borderFills>",
    '''<hh:borderFill id="3" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">
      <hh:slash type="NONE" Crooked="0" isCounter="0"/>
      <hh:backSlash type="NONE" Crooked="0" isCounter="0"/>
      <hh:leftBorder type="SOLID" width="0.12 mm" color="#000000"/>
      <hh:rightBorder type="SOLID" width="0.12 mm" color="#000000"/>
      <hh:topBorder type="SOLID" width="0.12 mm" color="#000000"/>
      <hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000"/>
      <hc:fillBrush><hc:winBrush faceColor="#DFE6F7" hatchColor="#000000" alpha="0"/></hc:fillBrush>
    </hh:borderFill></hh:borderFills>''')

# 제목 박스(1행 1열, 채움 없음) + 요약 박스(1행 1열, #DFE6F7) — 둘 다 첫 □ 이전
TITLE_WITH_SUMMARY_SECTION = '''<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:tbl id="1" rowCnt="1" colCnt="1" borderFillIDRef="1"><hp:sz width="47907" height="4084"/><hp:outMargin left="0" right="0" top="0" bottom="600"/><hp:tr><hp:tc borderFillIDRef="1"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>문서 제목</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/><hp:cellSz width="47907" height="4084"/></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:tbl id="2" rowCnt="1" colCnt="1" borderFillIDRef="3"><hp:sz width="47907" height="3280"/><hp:outMargin left="0" right="0" top="0" bottom="600"/><hp:tr><hp:tc borderFillIDRef="3"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>보고 목적을 밝히고자 함</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/><hp:cellSz width="47907" height="3280"/></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 절</hp:t></hp:run></hp:p>
</hs:sec>
'''

# 제목 박스가 2행인 산출물(kordoc report_info — 제목 행 + 담당자 행)
TWO_ROW_TITLE_SECTION = '''<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:tbl id="1" rowCnt="2" colCnt="1" borderFillIDRef="1"><hp:sz width="47907" height="6027"/><hp:outMargin left="0" right="0" top="0" bottom="600"/><hp:tr><hp:tc borderFillIDRef="1"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>문서 제목</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="0"/><hp:cellSpan colSpan="1" rowSpan="1"/><hp:cellSz width="47907" height="4084"/></hp:tc></hp:tr><hp:tr><hp:tc borderFillIDRef="1"><hp:subList><hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>('26. 9. 10., 데이터전략팀)</hp:t></hp:run></hp:p></hp:subList><hp:cellAddr colAddr="0" rowAddr="1"/><hp:cellSpan colSpan="1" rowSpan="1"/><hp:cellSz width="47907" height="1943"/></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
  <hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>□ 절</hp:t></hp:run></hp:p>
</hs:sec>
'''


def _table_rows(path, tbl_index):
    """(cellSz height, 채움 종류, 텍스트) 목록을 표 단위로 뽑는다."""
    with zipfile.ZipFile(path) as z:
        sec = ET.fromstring(z.read("Contents/section0.xml"))
        hdr = ET.fromstring(z.read("Contents/header.xml"))
    fills = {bf.get("id"): bf for bf in hdr.iter(ph.qn("hh", "borderFill"))}
    tbl = [t for t, _ in ph._iter_content_tables([sec])][tbl_index]
    out = []
    for tr in tbl.findall(ph.qn("hp", "tr")):
        tc = tr.find(ph.qn("hp", "tc"))
        bf = fills[tc.get("borderFillIDRef")]
        fill = bf.find(ph.qn("hc", "fillBrush"))
        kind = None
        if fill is not None:
            kind = ("gradation" if fill.find(ph.qn("hc", "gradation")) is not None
                    else fill.find(ph.qn("hc", "winBrush")).get("faceColor"))
        out.append((int(tc.find(ph.qn("hp", "cellSz")).get("height")), kind,
                    "".join(t.text or "" for t in tc.iter(ph.qn("hp", "t")))))
    return tbl, out


def test_title_box_form_leaves_summary_box_intact(tmp_path):
    """요약 박스(첫 □ 이전 1행 1열 #DFE6F7)를 제목 박스로 오인해 개조하지 않는다."""
    p = tmp_path / "title_summary.hwpx"
    build_hwpx(str(p), header_xml=SUMMARY_FILL_HEADER,
               section_xml=TITLE_WITH_SUMMARY_SECTION)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["title_box_form"]["restored"] == 1   # 제목 박스 하나뿐
    _, title_rows = _table_rows(str(p), 0)
    assert [k for _, k, _ in title_rows] == ["#0080C0", None, "gradation"]
    _, summary_rows = _table_rows(str(p), 1)
    assert len(summary_rows) == 1, "요약 박스에 밴드 행이 생겼다"
    assert summary_rows[0][1] == "#DFE6F7", "요약 박스 음영이 지워졌다"
    assert summary_rows[0][2] == "보고 목적을 밝히고자 함"


def test_form_sizes_leaves_summary_box_size(tmp_path):
    """요약 박스 글자를 제목 박스 20pt로 부풀리지 않는다(본문 15pt 유지)."""
    p = tmp_path / "title_summary_size.hwpx"
    build_hwpx(str(p), header_xml=SUMMARY_FILL_HEADER,
               section_xml=TITLE_WITH_SUMMARY_SECTION)
    ph.process_file(str(p), star=False, spacing=True)
    with zipfile.ZipFile(p) as z:
        sec = ET.fromstring(z.read("Contents/section0.xml"))
        hdr = ET.fromstring(z.read("Contents/header.xml"))
    heights = {cp.get("id"): cp.get("height") for cp in hdr.iter(ph.qn("hh", "charPr"))}
    sized = {}
    for tbl, _ in ph._iter_content_tables([sec]):
        for run in tbl.iter(ph.qn("hp", "run")):
            t = run.find(ph.qn("hp", "t"))
            if t is not None and (t.text or "").strip():
                sized[t.text] = heights[run.get("charPrIDRef")]
    assert sized["문서 제목"] == str(ph.TITLE_BOX_SIZE_PT * 100)
    assert sized["보고 목적을 밝히고자 함"] == "1500"


def test_title_box_form_restores_two_row_title(tmp_path):
    """제목 행 + 부가 행(담당자) 2행 산출물도 제목 행만 밴드로 감싼다."""
    p = tmp_path / "title_two_row.hwpx"
    build_hwpx(str(p), section_xml=TWO_ROW_TITLE_SECTION)
    summary = ph.process_file(str(p), star=False, spacing=True)
    assert summary["title_box_form"]["restored"] == 1
    tbl, rows = _table_rows(str(p), 0)
    assert tbl.get("rowCnt") == "4"
    assert [k for _, k, _ in rows] == ["#0080C0", None, "gradation", None]
    assert [h for h, _, _ in rows] == [ph.TITLE_BOX_BAND_HEIGHT,
                                       ph.TITLE_BOX_TITLE_HEIGHT,
                                       ph.TITLE_BOX_BAND_HEIGHT, 1943]
    assert rows[1][2] == "문서 제목"
    assert rows[3][2] == "('26. 9. 10., 데이터전략팀)", "부가 행이 사라졌다"
    # cellAddr rowAddr은 삽입 후에도 0..n-1로 연속이어야 한다
    addrs = [tc.find(ph.qn("hp", "cellAddr")).get("rowAddr")
             for tc in tbl.iter(ph.qn("hp", "tc"))]
    assert addrs == ["0", "1", "2", "3"]


def test_title_box_form_two_row_is_idempotent(tmp_path):
    p = tmp_path / "title_two_row_idem.hwpx"
    build_hwpx(str(p), section_xml=TWO_ROW_TITLE_SECTION)
    ph.process_file(str(p), star=False, spacing=True)
    second = ph.process_file(str(p), star=False, spacing=True)
    assert second["title_box_form"]["restored"] == 0
    tbl, rows = _table_rows(str(p), 0)
    assert tbl.get("rowCnt") == "4"
    assert [k for _, k, _ in rows] == ["#0080C0", None, "gradation", None]


def test_title_box_form_reports_skip_reason(tmp_path):
    """대상이 없거나 이미 복원된 경우를 '무동작'과 구분해 보고한다."""
    p = tmp_path / "title_skip.hwpx"
    build_hwpx(str(p), section_xml=ONE_ROW_TITLE_SECTION)
    first = ph.process_file(str(p), star=False, spacing=True)
    assert first["title_box_form"]["skipped"] is None
    second = ph.process_file(str(p), star=False, spacing=True)
    assert second["title_box_form"]["skipped"] == "already_restored"
