"""자가진단 미조치 lesson — kind·resolved_by로 센다('26.9.25 스키마; 종전 fix 키워드 판정은 끝난 조치까지 셌다)."""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import doctor


def test_classify_counts_only_unresolved_defects_and_features():
    rows = [
        {"date": "2026-09-24", "kind": "defect", "fix": "게이트② 뒤 정비"},                            # 미해결
        {"date": "2026-09-25", "kind": "feature", "fix": "요청", "resolved_by": "abc1234"},            # 해결
        {"date": "2026-09-20", "kind": "content", "fix": "초안 보강 필요"},                            # 내용 교훈
        {"date": "2026-09-01", "harness_defect": True, "fix": "훅 대상 정비"},                         # 옛 결함 표시
        {"date": "2026-08-01", "fix": "추가 검토 필요"},                                               # 옛 기록(참고)
        {"date": "2026-08-02", "fix": "보강 — 적용 완료", "resolved_by": "R074"},                      # 옛 기록·해결
        {"date": "2026-08-03", "kind": "defect", "fix": "…", "promoted": True},                        # 규칙으로 승격
    ]
    open_, legacy = doctor.classify_lessons(rows)
    assert [r["date"] for r in open_] == ["2026-09-24", "2026-09-01"]
    assert [r["date"] for r in legacy] == ["2026-08-01"]


def test_pending_check_reports_warn_only_for_open_items(tmp_path):
    p = tmp_path / "lessons.jsonl"
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"date": "2026-09-24", "kind": "defect", "fix": "x"},
        {"date": "2026-08-01", "fix": "보강 필요"}]) + "\n", encoding="utf-8")
    out = doctor.pending_lessons_check(p)
    assert out["상태"] == doctor.WARN and "미해결 결함·기능 1건" in out["값"] and "참고" in out["값"]
    p.write_text(json.dumps({"date": "2026-09-24", "kind": "defect", "fix": "x", "resolved_by": "eb88d24"}) + "\n",
                 encoding="utf-8")
    assert doctor.pending_lessons_check(p)["상태"] == doctor.OK
    assert doctor.pending_lessons_check(tmp_path / "없음.jsonl")["값"].startswith("축적본 없음")
