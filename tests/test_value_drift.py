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
