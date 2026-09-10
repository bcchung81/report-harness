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

def test_revise_archives_set_and_versions_hwpx(tmp_path):
    """재변환 직전 — md 세트는 history로, 인도본은 final/에 판본 접두어로 남는다."""
    wd = build(tmp_path, hwpx="전파데이터 현황조사.hwpx")
    ar.snapshot(wd, "교차검증전")
    out = ar.revise(wd)
    assert out["next_version"] == 2
    arch = wd / "history" / out["archived"]
    assert sorted(p.name for p in arch.glob("*.md")) == ["20_draft.md", "40_prepared.md", "40_roundtrip.md"]
    assert (arch / "drafts").is_dir() and list((arch / "drafts").glob("*.md"))
    assert not list((wd / "history/drafts").glob("*.md")), "판본에 딸린 스냅샷이 _wip에 남았다"
    names = [p.name for p in (wd / "final").glob("*.hwpx")]
    assert names == ["r01_" + out["renamed"][0]["to"].split("_", 2)[1] + "_전파데이터 현황조사.hwpx"]


def test_revise_keeps_hwpx_in_final_and_accumulates(tmp_path):
    """인도본은 history로 옮기지 않고 final/에 판본별로 쌓인다(접두어로 즉시 판별)."""
    wd = build(tmp_path, hwpx="r01_20260907_보고.hwpx")
    ar.revise(wd)
    (wd / "20_draft.md").write_text("□ 개 요\n\n ㅇ 둘째 판\n", encoding="utf-8")
    (wd / "final" / "r02_20260910_보고.hwpx").write_bytes(b"hwpx2")
    out = ar.revise(wd)
    assert out["next_version"] == 3
    assert sorted(p.name for p in (wd / "final").glob("*.hwpx")) == [
        "r01_20260907_보고.hwpx", "r02_20260910_보고.hwpx"]
    assert not list((wd / "history").glob("**/*.hwpx")), "인도본이 이력으로 복사됐다"


def test_revise_is_idempotent_between_conversions(tmp_path):
    """변환 없이 다시 부르면 같은 판본을 또 내리지 않는다 — 판본 폴더가 분 단위로 늘어난다."""
    wd = build(tmp_path, hwpx="r01_20260907_보고.hwpx")
    first = ar.revise(wd)
    again = ar.revise(wd)
    assert again["skipped"] == "already_archived"
    assert again["archived"] == first["archived"]
    assert len([p for p in (wd / "history").iterdir() if p.is_dir() and p.name.startswith("r")]) == 1


def test_revise_on_first_conversion_is_noop(tmp_path):
    """인도본이 없으면 내릴 직전 판본도 없다 — 최초 변환은 r01이다."""
    wd = build(tmp_path)
    out = ar.revise(wd)
    assert out == {"archived": None, "next_version": 1, "renamed": [], "skipped": "no_delivered_hwpx"}


def test_current_version_reads_filenames_not_index(tmp_path):
    """판본의 진실은 파일 이름이다 — index가 지워져도 인도본만 있으면 복원된다."""
    wd = build(tmp_path, hwpx="r03_20260910_보고.hwpx")
    assert ar.current_version(wd) == 3


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
