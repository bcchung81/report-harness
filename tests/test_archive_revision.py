"""작업폴더 이력 관리 회귀 (R086).

'26.9.10 실측에서 초안 판본 15개가 세 갈래 표기로 현행 파일 옆에 쌓여 있었고,
`final/`에 hwpx가 여럿인 건이 6건이라 현행본이 파일로 판별되지 않았다. 이 테스트가
지키는 것은 **현행 산출물과 이력이 절대 겹치지 않는 것**과 **판본이 파일 이름만으로
읽히는 것** 둘이다.
"""
import sys
import json
import pathlib
import importlib.util

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/report-pipeline/scripts"
sys.path.insert(0, str(SCRIPTS))
_spec = importlib.util.spec_from_file_location("archive_revision", SCRIPTS / "archive_revision.py")
ar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ar)


def build(tmp_path, draft="□ 개 요\n\n ㅇ 첫 판\n", hwpx=None):
    wd = tmp_path / "1200_시험건"
    (wd / "final").mkdir(parents=True)
    (wd / "20_draft.md").write_text(draft, encoding="utf-8")
    (wd / "40_prepared.md").write_text("prepared\n", encoding="utf-8")
    (wd / "40_roundtrip.md").write_text("roundtrip\n", encoding="utf-8")
    if hwpx:
        (wd / "final" / hwpx).write_bytes(b"hwpx")
    return wd


def index_rows(wd):
    return [json.loads(l) for l in (wd / "history/index.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


# --- 초안 스냅샷 -------------------------------------------------------------

def test_snapshot_copies_and_keeps_current(tmp_path):
    """스냅샷은 복사다 — 현행본이 제자리에 없으면 다음 단계가 읽을 것이 사라진다."""
    wd = build(tmp_path)
    row = ar.snapshot(wd, "교차검증전")
    assert (wd / "20_draft.md").is_file()
    snap = wd / "history" / row["file"]
    assert snap.is_file() and snap.read_text(encoding="utf-8") == (wd / "20_draft.md").read_text(encoding="utf-8")
    assert row["label"] == "교차검증전" and row["fingerprint"]


def test_snapshot_label_is_sanitised_and_required(tmp_path):
    """사유는 파일명에 들어가므로 경로 문자를 지운다 — 사유 없는 이력은 읽히지 않는다."""
    wd = build(tmp_path)
    row = ar.snapshot(wd, "수신처 반영/2차")
    assert "/" not in pathlib.Path(row["file"]).name
    assert "수신처-반영-2차" in row["file"]


def test_snapshot_never_touches_current_names(tmp_path):
    """이력이 현행 산출물 이름과 겹치지 않는다 — 작업폴더가 인터페이스라 겹치면 단계가 깨진다."""
    wd = build(tmp_path)
    before = {p.name for p in wd.glob("*.md")}
    ar.snapshot(wd, "1차")
    ar.snapshot(wd, "2차")
    assert {p.name for p in wd.glob("*.md")} == before


# --- 변환 판본 --------------------------------------------------------------

def test_begin_allocates_revision_folder(tmp_path):
    """변환 시작 시 판본 폴더를 선할당한다 — 파생물이 루트에 태어나지 않게 하는 장치."""
    wd = build(tmp_path)
    ar.snapshot(wd, "교차검증전")
    out = ar.begin(wd)
    assert out["rev"] == 1 and out["hwpx_prefix"].startswith("r01_")
    holder = pathlib.Path(out["dir"])
    assert holder.is_dir() and holder.name.startswith("r01_")
    assert (holder / "drafts").is_dir(), "그 판본에 딸린 스냅샷이 함께 내려가야 한다"
    assert not list((wd / "history/drafts").glob("*.md"))


def test_begin_counts_from_delivered_hwpx(tmp_path):
    """다음 판본 번호는 final/ 인도본에서 읽는다 — 이력이 지워져도 어긋나지 않는다."""
    wd = build(tmp_path, hwpx="r03_20260910_보고.hwpx")
    assert ar.begin(wd)["rev"] == 4


def test_begin_leaves_root_clean(tmp_path):
    """루트에는 사람이 고치는 파일만 남는다 — 낡을 파생물이 애초에 없다(R087)."""
    wd = build(tmp_path)
    before = {p.name for p in wd.glob("*.md")}
    ar.begin(wd)
    assert {p.name for p in wd.glob("*.md")} == before


# --- 초안↔인도본 대응 --------------------------------------------------------

def test_status_reports_draft_ahead(tmp_path):
    """초안을 고치고 재변환을 안 하면 인도본이 낡는다 — 이력 지문으로 판정한다."""
    wd = build(tmp_path)
    ar.begin(wd)
    assert ar.status(wd)["state"] == "current"
    (wd / "20_draft.md").write_text("□ 개 요\n\n ㅇ 고친 판\n", encoding="utf-8")
    st = ar.status(wd)
    assert st["state"] == "draft_ahead" and st["rev"] == 1 and st["detail"]


def test_status_before_first_export(tmp_path):
    assert ar.status(build(tmp_path))["state"] == "never_exported"


# --- 기존 폴더 1회 정리 -------------------------------------------------------

def test_migration_plans_three_legacy_notations(tmp_path):
    """`_vN`·`.날짜-사유`·`.이전판-설명` 세 갈래를 한 표기로 모은다."""
    wd = build(tmp_path)
    for name in ("20_draft_v2.md", "20_draft.20260907-교차검증전.md",
                 "20_draft.이전판-2종.md", "10_outline_v1.md"):
        (wd / name).write_text("x\n", encoding="utf-8")
    moves = {m["from"]: m["to"] for m in ar.migration_plan(wd)}
    assert set(moves) == {"20_draft_v2.md", "20_draft.20260907-교차검증전.md",
                          "20_draft.이전판-2종.md", "10_outline_v1.md"}
    assert moves["20_draft.20260907-교차검증전.md"].endswith("20_draft.20260907-0000.교차검증전.md")
    assert moves["20_draft_v2.md"].endswith(".v02.md")
    assert all(m.startswith("history/drafts/") for m in moves.values())


def test_migration_leaves_current_files_alone(tmp_path):
    wd = build(tmp_path)
    (wd / "20_draft_v1.md").write_text("x\n", encoding="utf-8")
    assert [m["from"] for m in ar.migration_plan(wd)] == ["20_draft_v1.md"]


def test_migration_dry_run_moves_nothing(tmp_path):
    """기본은 계획만 — 인도 완료 건의 파일 위치를 승인 없이 바꾸지 않는다."""
    wd = build(tmp_path)
    (wd / "20_draft_v1.md").write_text("x\n", encoding="utf-8")
    out = ar.migrate(wd, apply=False)
    assert out["applied"] is False and (wd / "20_draft_v1.md").is_file()
    out = ar.migrate(wd, apply=True)
    assert out["applied"] is True and not (wd / "20_draft_v1.md").exists()
    assert list((wd / "history/drafts").glob("*.md"))
    assert index_rows(wd)[-1]["kind"] == "migration"


def test_migration_relocates_derived_files(tmp_path):
    """루트에 남은 파생물 4종도 판본 폴더로 내린다 (R087 구조 전환)."""
    wd = build(tmp_path, hwpx="r02_20260910_보고.hwpx")
    for n in ("43_convert_input.md", "40_qa.md"):
        (wd / n).write_text("x\n", encoding="utf-8")
    out = ar.migrate(wd, apply=True)
    assert out["applied"]
    assert not [p.name for p in wd.glob("4*_*.md")], "파생물이 루트에 남았다"
    holder = next(p for p in (wd / "history").iterdir() if p.is_dir() and p.name.startswith("r02_"))
    assert sorted(p.name for p in holder.glob("*.md")) == [
        "40_prepared.md", "40_qa.md", "40_roundtrip.md", "43_convert_input.md"]
    kinds = [r["kind"] for r in index_rows(wd)]
    assert "revision" in kinds and kinds[-1] == "migration"
