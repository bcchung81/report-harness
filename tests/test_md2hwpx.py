"""웹앱판 생성기(md2hwpx) — 하네스 후처리와의 정합·열 폭 불변식 검증.

노트북 하네스는 kordoc을 계속 쓴다. 이 테스트는 `webapp/kca-report-hwpx/`가
같은 postprocess·validate 스크립트를 그대로 통과하는지, 그리고 kordoc이 내던
역행 열 폭을 재현하지 않는지를 고정한다.
"""
import json, pathlib, subprocess, sys, zipfile
import xml.etree.ElementTree as ET
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = ROOT / "webapp" / "kca-report-hwpx"
SCRIPTS = SKILL / "scripts"
HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

FIXTURE = """AI 활용성과 측정 기준(안)

< '26. 8. 4.(화), 경영기획본부 AI디지털심화팀 >

□ 추진 배경

 ㅇ **(지적 사항)** 근거의 객관성이 부족하다는 지적을 받았고, 제출 수치는 재산출할 수 없는 상태

   - 업무시간 단축 75.1%는 전사 평균이 아니라 PoC 9개·36명 표본 집계였음

| 순절감시간 = (도입 전 건당 투입시간 − 도입 후 건당 총소요) × 처리 건수 |
| --- |

※ 도입 전 투입시간은 실측 또는 도입 전 시스템 기록으로 확보하고 항별 증거 등급을 병기

＊ 순절감시간은 재작업 시간을 뺀 값으로, 도입 전후 처리 건수가 같은 과제에만 적용

□ 과제별 적용

 ㅇ **(계열 배정)** 과제 20건을 산출값 성격별 계열로 배정해 대장에 고정

[ 과제 수행 현황 ]

| 계 열 | 건수 | 과제 수행 현황 | 도입 전 값 |
| --- | --- | --- | --- |
| 절감 실적형 | 12 | '25년 계속 1, 신규 완료 1, 진행 10 | 실측 보유 또는 8월 실측 |
| 운영 실적형 | 4 | '25년 계속 1, 진행 2 | 정의 불가 |

붙임 1. 과제별 산출식 1부.  끝.

| 붙임 1 | | 과제별 산출식 |
| --- | --- | --- |

 ㅇ **(배정 원칙)** 도입 전 업무의 실재 여부와 기록 확보 가능성으로 정한다
"""


def run(args):
    return subprocess.run([sys.executable, *map(str, args)],
                          capture_output=True, text=True)


@pytest.fixture(scope="module")
def converted(tmp_path_factory):
    d = tmp_path_factory.mktemp("md2hwpx")
    src = d / "prepared.md"
    src.write_text(FIXTURE, encoding="utf-8")
    base = d / "base.hwpx"
    gen = run([SCRIPTS / "md2hwpx.py", src, "-o", base])
    assert gen.returncode == 0, gen.stderr
    out = d / "out.hwpx"
    out.write_bytes(base.read_bytes())
    post = run([SCRIPTS / "postprocess_hwpx.py", out, "--all", "--sender-size", "12"])
    assert post.returncode == 0, post.stderr
    (d / "post.json").write_text(post.stdout, encoding="utf-8")
    return d, out, json.loads(post.stdout)


def test_postprocess_applies_all_rules(converted):
    """생성기 산출물이 하네스 후처리를 무수정으로 통과하고 룰이 실제로 적용된다."""
    _, _, post = converted
    assert post["title_box"]["found"] is True
    # ＊ 각주가 있으므로 단계가 실제로 돌고 참고 charPr이 해석된다(R011).
    # runs_changed는 단정하지 않는다 — md2hwpx는 kordoc과 달리 ＊ 문단을 이미
    # 참고 스타일로 내보내므로 치환 0건이 정상이다.
    assert post["star_footnote"]["stars_found"] == 1
    assert post["star_footnote"]["ref_charpr_id"] is not None
    assert post["dae_bold"]["runs_changed"] == 2
    assert post["annex_banner"]["title_justified"] == 1
    assert post["sender_size"]["runs_changed"] == 1
    assert post["body_justify"]["changed"] > 0
    assert post["formula_box"]["formula_boxes"] == 1


def test_assert_gate_passes(converted):
    """침묵 실패 차단 게이트가 통과한다 — 실패하면 룰이 무효화된 것이다."""
    d, _, _ = converted
    r = run([SCRIPTS / "assert_postprocess.py", d / "post.json", d / "prepared.md"])
    assert r.returncode == 0, r.stdout


def test_structural_valid(converted):
    _, out, _ = converted
    r = run([SCRIPTS / "validate_hwpx.py", "structural", out])
    assert r.returncode == 0, r.stdout


def test_bold_markers_not_literal(converted):
    """R016 리드 라벨이 볼드 run으로 들어가야 한다 — `**`가 본문에 남으면 실패."""
    _, out, _ = converted
    sec = ET.fromstring(zipfile.ZipFile(out).read("Contents/section0.xml"))
    text = "".join(t.text or "" for t in sec.iter(f"{HP}t"))
    assert "**" not in text


def _tables(path):
    sec = ET.fromstring(zipfile.ZipFile(path).read("Contents/section0.xml"))
    for tbl in sec.iter(f"{HP}tbl"):
        rows = tbl.findall(f"{HP}tr")
        widths = [int(tc.find(f"{HP}cellSz").get("width"))
                  for tc in rows[0].findall(f"{HP}tc")]
        yield tbl, widths


def test_cell_widths_sum_to_table_size(converted):
    """R036: 셀 폭 합 == 표 sz 정확 일치. 어긋나면 한글이 표를 다시 배치한다."""
    _, out, _ = converted
    for tbl, widths in _tables(out):
        assert sum(widths) == int(tbl.find(f"{HP}sz").get("width")), tbl.get("id")


def test_tables_fit_page_width(converted):
    """R042: 표 총폭(sz + outMargin 좌우) < 본문폭 − 283hu. 생성 시점에 이미 충족해야
    apply_fit_page_width가 생성기 표에는 손대지 않는다(멱등 no-op).

    후처리본으로 검사하면 postprocess가 주입한 머리말 배너(도너 크기 → 경계값까지
    축소된 상태)가 섞여 경계에 정확히 앉으므로, 생성 직후 base를 대상으로 본다."""
    d, _, post = converted
    for tbl, _w in _tables(d / "base.hwpx"):
        om = tbl.find(f"{HP}outMargin")
        total = int(tbl.find(f"{HP}sz").get("width")) + int(om.get("left")) + int(om.get("right"))
        assert total < 48190 - 283, (tbl.get("id"), total)
    # 축소된 표는 머리말 배너 하나뿐 — 생성기 표가 끼면 폭 설계가 틀린 것이다
    assert post["fit_page_width"]["tables_fitted"] <= 1, post["fit_page_width"]


def test_column_width_tracks_content():
    """열 폭이 내용 요구에 역행하지 않는다 — kordoc의 결함(34폭 열에 8.6폭/줄)을
    재현하지 않는지 알고리즘 수준에서 고정한다."""
    sys.path.insert(0, str(SCRIPTS))
    from md2hwpx import column_widths, wlen
    rows = [["계 열", "건수", "과제 수행 현황", "도입 전 값", "성과측정 형태"],
            ["절감 실적형", "12", "'25년 계속 1, 신규 완료 1, 진행 10",
             "실측 보유 또는 8월 실측", "순절감시간·단축률 산출"]]
    w = column_widths(rows, 46389)
    assert sum(w) == 46389
    demand = [max(wlen(r[j]) for r in rows) for j in range(5)]
    # 요구가 가장 큰 열이 가장 넓어야 한다 (kordoc은 여기서 역전됐다)
    assert w.index(max(w)) == demand.index(max(demand))
    # 짧은 라벨 열도 하한 아래로 눌리지 않는다
    assert min(w) >= 8 * 600 / 2


def test_title_box_shares_first_paragraph(converted):
    """secPr와 제목 박스는 같은 첫 문단이어야 한다.

    쪼개면 secPr 문단이 본문 15pt·줄간격 160% 빈 줄로 렌더돼 제목표 위에 약 8.5mm
    여백이 생긴다 — 정적 검증(slack·outMargin·줄간격)은 전부 통과하므로 한글로 열어야
    드러난다. '26.8.7 Reachy_Mini 배포본에서 실제로 재발한 결함이다."""
    _, out, _ = converted
    sec = ET.fromstring(zipfile.ZipFile(out).read("Contents/section0.xml"))
    first = sec.findall(f"{HP}p")[0]
    assert first.find(f".//{HP}secPr") is not None
    assert any(r.find(f"{HP}tbl") is not None for r in first.findall(f"{HP}run")), \
        "제목 박스가 secPr 문단과 분리됐다 — 제목표 위에 빈 줄이 생긴다"


def test_column_widths_never_invert():
    """요구 표시폭이 큰 열이 더 좁으면 안 된다.

    옛 고정 상한(40%)은 2열 표에서 ncol×0.40 < 1이라 두 열 모두 걸려 20%가 남았고,
    그 잔여가 최광열 하나에 몰려 배분이 뒤집혔다(실측: 요구 8폭 열 60%, 55폭 열 40%)."""
    sys.path.insert(0, str(SCRIPTS))
    from md2hwpx import column_widths, wlen, W_CONTENT
    cases = [
        [["시 기", "내 용"], ["2020년", "선전에 설립되어 오픈소스 하드웨어 사업을 시작하고 글로벌 유통망을 구축"]],
        [["구 분", "값"], ["아주 긴 항목명이 들어가는 열", "3"]],
        [["A", "B", "C"], ["짧음", "중간 길이 텍스트가 들어간다", "가"]],
    ]
    for rows in cases:
        w = column_widths(rows, W_CONTENT)
        assert sum(w) == W_CONTENT, (rows, w)
        d = [max(wlen(r[j]) for r in rows) for j in range(len(rows[0]))]
        order_d = sorted(range(len(d)), key=lambda j: d[j])
        for a, b in zip(order_d, order_d[1:]):
            if d[b] > d[a] * 2:          # 요구가 2배 이상 크면 폭도 더 넓어야 한다
                assert w[b] > w[a], (rows, d, w)


def test_geometry_guard_catches_inversion(tmp_path):
    """기하 가드가 열 폭 역전을 실제로 잡는지 — 결함을 주입해 확인한다."""
    sys.path.insert(0, str(SCRIPTS))
    import importlib
    ap = importlib.import_module("assert_postprocess")
    import md2hwpx
    src = "제목\n\n□ 절\n\n| 시 기 | 내 용 |\n| --- | --- |\n| 2020 | " + "가" * 60 + " |\n"
    blocks = md2hwpx.parse(src)
    orig = md2hwpx.column_widths
    md2hwpx.column_widths = lambda rows, total: [total - 10000, 10000]   # 역전 주입
    try:
        bad = tmp_path / "bad.hwpx"
        md2hwpx.package(md2hwpx.render(blocks), blocks, bad)
    finally:
        md2hwpx.column_widths = orig
    fails = ap.check_geometry(bad)
    assert any(f["check"] == "table.column_width_inverted" for f in fails), fails


def test_roundtrip_fallback_without_pyhwpx(converted):
    """python-hwpx가 없어도 되읽기가 되고, compare의 최종 검출선이 살아있어야 한다."""
    d, out, _ = converted
    rt = d / "rt.md"
    r = run([SCRIPTS / "roundtrip_md.py", out, "-o", rt, "--stdlib"])
    assert r.returncode == 0, r.stderr
    cmp_ = run([SCRIPTS / "validate_hwpx.py", "compare", d / "prepared.md", rt])
    issues = json.loads(cmp_.stdout)["issues"]
    # 제목 박스 1 + 머리말 배너 1이 정상 가산되는 표 수 차이 외에는 없어야 한다
    assert [i["rule"] for i in issues] == ["count-mismatch:tables"], issues
    assert issues[0]["roundtrip"] - issues[0]["src"] == 2, issues


def test_roundtrip_fallback_detects_literal_markers(tmp_path):
    """폴백이 `**` 리터럴 잔재를 잡아내는지 — 이 검사가 죽으면 방어선이 사라진다."""
    sys.path.insert(0, str(SCRIPTS))
    import importlib
    rt = importlib.import_module("roundtrip_md")
    vh = importlib.import_module("validate_hwpx")
    # 볼드 파싱을 끈 상태를 흉내낸 md — 마커가 문단 텍스트에 그대로 들어간다
    src = tmp_path / "bad.md"
    src.write_text("제목\n\n□ 절\n\n ㅇ **(라벨)** 본문\n", encoding="utf-8")
    bad = tmp_path / "bad.hwpx"
    import md2hwpx
    blocks = md2hwpx.parse(src.read_text(encoding="utf-8"))
    for b in blocks:                      # 세그먼트를 리터럴로 되돌려 결함을 주입
        if b["t"] == "yo":
            b["segs"] = [("ㅇ **(라벨)** 본문", False)]
    md2hwpx.package(md2hwpx.render(blocks), blocks, bad)
    out_md = tmp_path / "rt.md"
    out_md.write_text(rt.read_stdlib(bad), encoding="utf-8")
    issues = vh.compare_texts(src.read_text(encoding="utf-8"),
                              out_md.read_text(encoding="utf-8"))
    assert any(i["rule"] == "markdown-leftover" for i in issues), issues


def test_decode_assets_is_idempotent_noop(tmp_path):
    """자산 복원기는 원본이 있으면 아무 것도 하지 않아야 한다 — 한 SKILL.md로
    Claude·ChatGPT·Gemini 세 플랫폼을 덮는 근거."""
    sys.path.insert(0, str(SCRIPTS))
    import importlib, base64
    da = importlib.import_module("decode_assets")
    d = tmp_path / "assets"; d.mkdir()
    (d / "x.png").write_bytes(b"\x89PNG-real")
    (d / "x.png.b64").write_text(base64.b64encode(b"stale").decode(), encoding="ascii")
    restored, skipped = da.decode(d)
    assert restored == [] and skipped == ["x.png"]
    assert (d / "x.png").read_bytes() == b"\x89PNG-real"
    (d / "y.bmp.b64").write_text(base64.b64encode(b"BMdata").decode(), encoding="ascii")
    restored, _ = da.decode(d)
    assert restored == ["y.bmp"] and (d / "y.bmp").read_bytes() == b"BMdata"


def test_gemini_package_has_no_binary_files():
    """Gemini Spark는 스킬 패키지에 바이너리를 못 넣는다(공식 문서) — 빌드가 이를 지킨다."""
    import subprocess, zipfile as zf, tempfile
    with tempfile.TemporaryDirectory() as td:
        out = pathlib.Path(td) / "g.zip"
        r = run([ROOT / "scripts" / "build_webapp_skill.py", "--target", "gemini", "-o", out])
        assert r.returncode == 0, r.stdout + r.stderr
        names = zf.ZipFile(out).namelist()
    assert not [n for n in names if n.lower().endswith((".png", ".bmp", ".hwpx"))], names
    assert any(n.endswith(".b64") for n in names), names


def test_build_blocks_pii_and_restores_rules():
    """PII가 실린 룰 원본으로 빌드하면 exit 1이고, 재생성됐던 rules.md는 원복된다.

    종전에는 rules.md 기록이 기준 검사보다 먼저라 빌드가 실패해도 --rules로 지정한
    내부 축적본이 소스 트리에 남았다 — 외부 배포 패키지의 PII 가드 부재와 함께 수정."""
    import tempfile
    rules_dst = SKILL / "references" / "rules.md"
    before = rules_dst.read_bytes()
    with tempfile.TemporaryDirectory() as td:
        bad = pathlib.Path(td) / "rules.md"
        bad.write_text("- R001 [draft] 문의 010-1234-5678 로 연락 (근거[관례]: x)\n",
                       encoding="utf-8")
        out = pathlib.Path(td) / "c.skill"
        r = run([ROOT / "scripts" / "build_webapp_skill.py", "--target", "claude",
                 "-o", out, "--rules", bad])
    assert r.returncode == 1, r.stdout + r.stderr
    assert '"pii"' in r.stdout
    assert rules_dst.read_bytes() == before, "빌드 실패 후 rules.md가 원복되지 않았다"
    assert not out.exists()


def test_build_rejects_bad_args_before_touching_rules():
    """인자 오류(exit 2)로 끝나도 rules.md는 손대지 않은 상태여야 한다.

    `webapp/.../rules.md`는 이 공개 저장소의 추적 파일이다. 인자 검사가 룰 렌더 뒤에
    있던 동안은 --target all + -o 조합이 원복 없이 exit 2로 빠져나가, --rules로 지정한
    내부 축적본이 워킹트리에 남은 채 `git commit -a` 한 번이면 공개되는 상태였다."""
    import tempfile
    rules_dst = SKILL / "references" / "rules.md"
    before = rules_dst.read_bytes()
    with tempfile.TemporaryDirectory() as td:
        internal = pathlib.Path(td) / "rules.md"
        internal.write_text("- R999 [draft] 대외비 내부 축적 규칙 (근거[실측]: x)\n",
                            encoding="utf-8")
        r = run([ROOT / "scripts" / "build_webapp_skill.py", "--target", "all",
                 "-o", pathlib.Path(td) / "pkg.zip", "--rules", internal])
    assert r.returncode == 2, r.stdout + r.stderr
    assert rules_dst.read_bytes() == before, "인자 오류로 끝났는데 rules.md가 덮여 있다"
    assert b"R999" not in rules_dst.read_bytes()


def test_build_survives_stray_finder_droppings():
    """상류 스킬 폴더에 .DS_Store가 생겨도 빌드는 통과해야 한다.

    macOS에서 skills/humanizer를 Finder로 한 번 여는 것만으로 서드파티 대조가
    '.DS_Store가 references/humanizer에 누락'이라며 빌드를 통째로 세웠다 — 패키지에
    담기지도 않는 파일이다."""
    import tempfile
    stray = ROOT / "skills" / "humanizer" / ".DS_Store"
    existed = stray.exists()
    if not existed:
        stray.write_bytes(b"\x00\x00\x00\x01Bud1")
    try:
        with tempfile.TemporaryDirectory() as td:
            out = pathlib.Path(td) / "c.skill"
            r = run([ROOT / "scripts" / "build_webapp_skill.py", "--target", "claude", "-o", out])
            assert r.returncode == 0, r.stdout + r.stderr
            assert ".DS_Store" not in zipfile.ZipFile(out).namelist()
    finally:
        if not existed:
            stray.unlink()


def test_bundled_humanizer_ships_license_and_notice():
    """서드파티 번들은 라이선스 전문 동봉 + 루트 고지가 있어야 배포할 수 있다."""
    lic = SKILL / "references" / "humanizer" / "LICENSE"
    assert lic.is_file(), "humanizer LICENSE 미동봉"
    text = lic.read_text(encoding="utf-8")
    assert "MIT License" in text and "DaleSeo" in text
    notice = (SKILL / "NOTICE.md").read_text(encoding="utf-8")
    assert "references/humanizer/LICENSE" in notice
    assert "DaleSeo" in notice and "MIT" in notice


def test_bundled_humanizer_matches_upstream():
    """번들 사본이 상류와 갈라지면 안 된다(SKILL.md는 프론트매터 제거본이라 제외)."""
    import hashlib
    up = ROOT / "skills" / "humanizer"
    for f in sorted(up.rglob("*")):
        if not f.is_file() or f.name == "SKILL.md":
            continue
        mirror = SKILL / "references" / "humanizer" / f.relative_to(up)
        assert mirror.is_file(), f
        assert hashlib.sha256(f.read_bytes()).digest() == \
               hashlib.sha256(mirror.read_bytes()).digest(), f


def test_single_skill_manifest_in_package():
    """패키지 안 SKILL.md는 루트 하나뿐이어야 한다 — 둘이면 매니페스트가 모호해진다."""
    found = sorted(str(p.relative_to(SKILL)) for p in SKILL.rglob("SKILL.md"))
    assert found == ["SKILL.md"], found


def test_harness_scripts_not_forked():
    """웹앱 복사본이 하네스 원본과 바이트 동일해야 한다 — 드리프트 차단."""
    import hashlib
    for name in ("postprocess_hwpx.py", "validate_hwpx.py",
                 "prep_report_md.py", "lint_md_profile.py"):
        a = (ROOT / "skills/report-pipeline/scripts" / name).read_bytes()
        b = (SCRIPTS / name).read_bytes()
        assert hashlib.sha256(a).digest() == hashlib.sha256(b).digest(), name
