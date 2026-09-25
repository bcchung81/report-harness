"""규약 문서 ↔ 코드 상수 드리프트 탐지 (R066).

같은 값이 rules.md·rules-seed.md·format-profile.kca.md·코드·테스트 최대 8곳에 손으로
복제돼 있어, 한 곳만 고치면 나머지가 조용히 거짓말을 시작한다. 실제 사고:
  · R062 정정 시 rules.md·md-profile은 고쳤으나 rules-seed.md를 놓쳐 새 설치가 틀린
    '1줄 75자'를 물려받을 뻔했다 ('26.8.7)
  · R060 신설 시 코드·프로파일·테스트 3곳을 동시에 고쳐야 회귀가 통과했다

이 테스트는 **format-profile.kca.md를 단일 출처로 보고** 코드 상수가 그와 어긋나면
실패시킨다. 값을 바꾸려면 프로파일과 코드를 함께 고쳐야 한다.
"""
import re
import pathlib
import importlib.util
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROFILE = ROOT / "skills/report-pipeline/references/format-profile.kca.md"
SEED = ROOT / "skills/report-pipeline/references/rules-seed.md"
RULES = ROOT / "report/_harness/rules.md"

_spec = importlib.util.spec_from_file_location(
    "ph_drift", ROOT / "skills/report-pipeline/scripts/postprocess_hwpx.py")
ph = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ph)


def _profile_text():
    return PROFILE.read_text(encoding="utf-8")


def _hwpunits_from_gap_table():
    """§7 계층 간격표의 (경계, HWPUNIT) 쌍을 뽑는다."""
    out = {}
    for row in re.finditer(r"^\|\s*([^|]+?)\s*\|\s*(\d+)pt\s*\|\s*(\d+)\s*\|", _profile_text(), re.M):
        label, pt, hu = row.group(1), int(row.group(2)), int(row.group(3))
        assert pt * 100 == hu, f"프로파일 자체 모순: {label} {pt}pt ≠ {hu} HWPUNIT"
        out[label] = hu
    return out


def test_gap_table_pt_and_hwpunit_agree():
    """프로파일 간격표의 pt 열과 HWPUNIT 열이 서로 맞는다(100배)."""
    gaps = _hwpunits_from_gap_table()
    assert gaps, "§7 계층 간격표를 못 찾았다 — 프로파일 구조가 바뀌었는지 확인"


def test_first_dae_gap_matches_code():
    """발신 줄 → 첫 □ 간격이 프로파일과 TRANSITIONS에서 같다 (R060)."""
    gaps = _hwpunits_from_gap_table()
    key = next(k for k in gaps if k.startswith("발신 줄 → □"))
    assert ph.TRANSITIONS[("sending", "dae")][1] == gaps[key]


def test_yo_to_dash_gap_matches_code():
    """ㅇ → 대시 간격이 프로파일과 TRANSITIONS에서 같다 (R013 '26.9.10 정정 3pt).

    종전 드리프트 검사는 §7 간격표 8행 중 두 행(발신→□·블록 경계)만 코드와 대조했다 —
    나머지는 프로파일만 고치고 코드를 안 고쳐도(또는 그 반대여도) 통과했다."""
    gaps = _hwpunits_from_gap_table()
    key = next(k for k in gaps if k.replace(" ", "") == "ㅇ→-")
    assert gaps[key] == 300, "프로파일의 ㅇ→대시 간격이 3pt가 아니다"
    assert ph.TRANSITIONS[("yo", "dash")][1] == gaps[key]


def test_block_boundary_matches_code():
    """두 번째 이후 □ 상단 간격이 프로파일과 BLOCK_BOUNDARY_HEIGHT에서 같다 (R060)."""
    gaps = _hwpunits_from_gap_table()
    key = next(k for k in gaps if "두 번째 이후 □ 상단" in k)
    assert ph.BLOCK_BOUNDARY_HEIGHT == gaps[key]


def test_hierarchy_indent_table_matches_code():
    """계층별 들여쓰기표(공백 칸수·hang)가 HIERARCHY_SPACES·HIERARCHY_HANG과 같다 (R061)."""
    rows = re.findall(r"^\|\s*(□|ㅇ|대시|※·＊)\s*\|\s*(\d+)칸\s*\|\s*([\d.]+)pt\s*\|",
                      _profile_text(), re.M)
    assert len(rows) == 4, "계층별 들여쓰기표 4행을 못 찾았다"
    kinds = {"□": ["dae"], "ㅇ": ["yo"], "대시": ["dash"], "※·＊": ["cham", "star"]}
    for label, spaces, hang_pt in rows:
        for kind in kinds[label]:
            assert ph.HIERARCHY_SPACES[kind] == int(spaces), f"{label} 공백 칸수 불일치"
            assert ph.HIERARCHY_HANG[kind] == int(round(float(hang_pt) * 100)), \
                f"{label} 내어쓰기 불일치"


def test_sender_size_default_matches_profile():
    """--all이 기본 적용하는 발신 줄 크기가 프로파일 실측(R018)과 같다.

    종전에는 이 값이 문서 9곳에 '--sender-size 12'로 복제돼 있었다 — 기본값 승격 후
    프로파일과 코드 상수 두 곳만 남기고, 그 둘의 일치를 여기서 강제한다."""
    assert re.search(r"발신 줄 12pt\(R018\)", _profile_text()), "프로파일의 발신 줄 실측 서술이 사라졌다"
    assert ph.SENDER_SIZE_PT == 12


def test_form_sizes_match_profile():
    """계층 글자 크기 재강제 값이 format-profile §2 명시값과 같다.

    kordoc generate_document가 sizes 인자를 무시하고 □ 17pt·대시 14pt·제목 23~25pt를
    산출한 '26.9.8 회귀 이후, 양식 값을 후처리가 되돌린다 — 그 값이 프로파일과 갈리면
    되돌린 결과 자체가 틀리므로 두 곳의 일치를 여기서 강제한다."""
    profile = _profile_text()
    assert "| 문서 제목 | HY헤드라인M | 24pt |" in profile, "프로파일의 제목 24pt 행이 사라졌다"
    assert "| □ (1단 제목) | HY헤드라인M | 15pt |" in profile, "프로파일의 □ 15pt 행이 사라졌다"
    assert "| ㅇ (2단 요지) | 휴먼명조 | 15pt |" in profile, "프로파일의 ㅇ 15pt 행이 사라졌다"
    assert "| - (3단 상세) | 휴먼명조 | 15pt |" in profile, "프로파일의 대시 15pt 행이 사라졌다"
    assert ph.TITLE_BOX_SIZE_PT == 24
    assert ph.FORM_SIZES_PT["dae"] == 15
    assert ph.FORM_SIZES_PT["yo"] == 15
    assert ph.FORM_SIZES_PT["dash"] == 15
    assert ph.FORM_SIZES_PT["cham"] == 13


def test_title_box_form_matches_profile():
    """제목 박스 원형 값이 프로파일 서술과 코드에서 같다.

    format-profile §7이 '상단 얇은 행(3.8pt)은 양식 원형(1열×3행)의 그라데이션 배경
    밴드이므로 삭제 금지'라고 못박은 그 구조를, kordoc이 더 이상 만들지 않아 후처리가
    복원한다 — 밴드 높이가 갈리면 복원 결과가 양식과 어긋난다."""
    profile = _profile_text()
    assert "양식 원형(1열×3행)" in profile, "프로파일의 제목표 3행 원형 서술이 사라졌다"
    assert "3.8pt" in profile, "프로파일의 밴드 높이 서술이 사라졌다"
    assert ph.TITLE_BOX_BAND_HEIGHT == 382          # 3.8pt
    assert ph.TITLE_BOX_TITLE_HEIGHT == 2850        # 28.5pt
    # 어느 행이 어떤 채움을 갖는지까지 대조한다 — 색 문자열만 훑으면 상·하 밴드가
    # 뒤바뀌어도 통과한다(종전 검사의 구멍)
    assert '<hc:winBrush faceColor="#0080C0"' in ph.TITLE_BOX_TOP_FILL, "0행은 단색 #0080C0"
    assert "gradation" not in ph.TITLE_BOX_TOP_FILL, "0행에 그라데이션이 들어갔다"
    assert 'type="RADIAL"' in ph.TITLE_BOX_BOTTOM_FILL, "2행은 방사형 그라데이션"
    assert (ph.TITLE_BOX_BOTTOM_FILL.index("#0080C0")
            < ph.TITLE_BOX_BOTTOM_FILL.index("#3CBFFF")), "2행 그라데이션 색 순서 역전"
    # 프로파일이 같은 값을 단일 출처로 들고 있다(CLAUDE.md 값 드리프트 규약)
    for token in ('winBrush #0080C0', 'RADIAL', '#0080C0→#3CBFFF', '4변 `NONE`'):
        assert token in profile, f"프로파일에 복원 확정값 서술이 없다: {token}"


def test_line_fit_floors_match_rules():
    """자간·장평 하한이 rules-seed.md 서술과 코드에서 같다 (R062)."""
    body = SEED.read_text(encoding="utf-8")
    assert "자간 -10 미만·장평 90 미만은" in body, "R062 하한 서술이 사라졌다"
    assert ph.MIN_SPACING == -10
    assert ph.MIN_RATIO == 90


@pytest.mark.skipif(not RULES.exists(), reason="운영 축적본 없음 — 시드 단독 환경(fresh clone·CI)")
def test_seed_carries_every_operational_rule():
    """rules-seed.md(새 설치 baseline)가 운영 rules.md의 규칙을 **본문까지** 그대로 담는다.

    R062 정정 때 시드를 놓쳐 새 설치가 틀린 값을 물려받을 뻔한 사고의 회귀 방지.
    ID 집합만 비교하던 구버전은 같은 사고의 본문 변형(근거 등급 누락 등 60건)을 놓쳤다.
    """
    rule_lines = lambda p: {m.group(1): m.group(0).rstrip() for m in re.finditer(
        r"^- (R\d+) \[.*$", p.read_text(encoding="utf-8"), re.M)}
    op, sd = rule_lines(RULES), rule_lines(SEED)
    assert not (op.keys() - sd.keys()), f"시드에 누락된 규칙: {sorted(op.keys() - sd.keys())}"
    # 양방향 — 폐지된 규칙이 시드에만 남으면 새 설치가 죽은 규칙을 물려받는다
    assert not (sd.keys() - op.keys()), f"운영에서 폐지됐는데 시드에 남은 규칙: {sorted(sd.keys() - op.keys())}"
    drift = [r for r in op if op[r] != sd[r]]
    assert drift == [], f"본문 드리프트 — 운영본을 시드로 재동기화 필요: {drift}"


@pytest.mark.skipif(not (RULES.parent / "rules-history.md").exists(), reason="운영 경위 로그 없음 — 시드 단독 환경")
def test_seed_history_matches_operational_history():
    """경위 로그도 시드 ↔ 운영이 같은 절(`## R0NN`)을 가진다 — 시드에만 있으면 작성자 운영본의 결번이 죽은 참조가 되고,
    운영에만 있으면 설치자에게 경위가 도달하지 않는다('26.9.25 격리 설치 재현: 새 설치 자가진단이 결번 6건을 죽은
    참조로 경고 · 시드에 R048·R073, 운영에 R072·R087이 빠져 있었다)."""
    sec = lambda p: set(re.findall(r"^## (R\d+)\b", p.read_text(encoding="utf-8"), re.M))
    op, sd = sec(RULES.parent / "rules-history.md"), sec(SEED.parent / "rules-history.md")
    assert op == sd, f"운영에만: {sorted(op - sd)} · 시드에만: {sorted(sd - op)} — sync_rules.py --apply 또는 시드에 절 추가"


def test_no_stale_line_length_claim():
    """폐기된 '1줄 75자' 어림값이 규약 어디에도 유효 기준으로 남지 않는다 (R062)."""
    for p in (RULES, SEED, ROOT / "skills/report-pipeline/references/md-profile.md"):
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8")
        for m in re.finditer(r"[^\n]*75자[^\n]*", t):
            line = m.group(0)
            # 정정을 서술하는 문맥(R062 본문·표기 규약 안내)에서의 인용만 허용
            ok = any(k in line for k in ("R050", "정정", "→ R062", "오인"))
            assert ok, f"{p.name}에 폐기된 75자 기준이 유효 서술로 남아 있다: {line[:60]}"


# ---------------------------------------------------------------- 도식 배색 (R090)
_rd_spec = importlib.util.spec_from_file_location("rd_drift", ROOT / "skills/report-pipeline/scripts/render_diagram.py")
rd = importlib.util.module_from_spec(_rd_spec)
_rd_spec.loader.exec_module(rd)


def _palette_rows():
    """§8 도식 배색 표의 (상수, 값) — `STATUS.done`처럼 점 표기는 STATUS 사전의 채움 색."""
    sec = _profile_text().split("## 8. 도식 배색", 1)[1]
    return {m.group(1): m.group(2).upper()
            for m in re.finditer(r"^\|[^|]+\|\s*`([A-Z_.a-z]+)`\s*\|\s*(#[0-9A-Fa-f]{6})\s*\|", sec, re.M)}


def _code_color(name):
    if name.startswith("STATUS."):
        return rd.STATUS[name.split(".", 1)[1]][0].upper()
    return getattr(rd, name).upper()


def test_diagram_palette_matches_profile():
    rows = _palette_rows()
    assert len(rows) >= 14
    diff = {k: (v, _code_color(k)) for k, v in rows.items() if _code_color(k) != v}
    assert diff == {}, f"프로파일 ↔ render_diagram 배색 불일치: {diff}"


def _lum(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _contrast(a, b):
    la, lb = sorted([_lum(a), _lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_diagram_palette_contrast_and_grayscale():
    """글자를 얹는 조합은 4.5:1, 선·화살표는 흰 바탕 3:1, 비교·상태는 흑백에서도 갈린다(KRDS 원칙)."""
    white, navy = "#FFFFFF", rd.NAVY
    text_pairs = [(white, rd.BLUE_FILL), (white, rd.ACCENT), (navy, rd.HEAD), (navy, rd.HEAD_STRONG),
                  (rd.OLD_TEXT, rd.HEAD_OLD), (navy, rd.ACCENT_SOFT)] + [(fg, bg) for bg, fg, _ in rd.STATUS.values()]
    low = [(a, b, round(_contrast(a, b), 2)) for a, b in text_pairs if _contrast(a, b) < 4.5]
    assert low == [], f"글자 명도대비 4.5:1 미달: {low}"
    graphics = [rd.NAVY, rd.BLUE, rd.LINE, rd.ACCENT_LINE]
    assert all(_contrast(c, white) >= 3.0 for c in graphics)
    assert abs(_lum(rd.HEAD_OLD) - _lum(rd.HEAD_STRONG)) >= 0.15, "비교도 종전·개선 머리가 흑백에서 같아 보인다"
    shades = sorted(_lum(bg) for bg, _, _ in rd.STATUS.values())
    assert min(b - a for a, b in zip(shades, shades[1:])) >= 0.1, "일정 상태 3단계가 흑백에서 갈리지 않는다"


# ---------------------------------------------------------------- 도식 카드 내어쓰기 (R093)
def test_diagram_card_hang_matches_profile():
    sec = _profile_text().split("### 8-1. 도식 카드 본문", 1)[1]
    m = re.search(r"^\|[^|]+\|\s*`CARD_HANG`\s*\|\s*(\d+)\s*\|", sec, re.M)
    assert m, "format-profile §8-1에 CARD_HANG 행이 없다"
    spec = importlib.util.spec_from_file_location("dt_drift", ROOT / "skills/report-pipeline/scripts/diagram_table.py")
    dt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dt)
    assert int(m.group(1)) == dt.CARD_HANG, f"프로파일 {m.group(1)} ↔ diagram_table {dt.CARD_HANG}"
