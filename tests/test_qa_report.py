"""변환 QA 기록·인도 판정 (qa_report.py).

종전에는 구조 오류만 exit 1이라 내용 대조 실패나 검증 단계 누락이 '성공'으로 읽혔다(astra 검토 A14).
Codex에는 안전망 훅이 없으므로 이 판정이 실행기 공통 인도 게이트다.
"""
import sys, json, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import qa_report as qa

OK = {"postprocess": {"spacing": {"inserted": 3}, "layout": {"pages_by_part": [1], "est_pt": 600},
                      "line_fit": {"overflow": 0, "overflow_detail": []}},
      "structural": {"errors": []}, "compare": {"issues": []}, "numbers": {"issues": []}}


def _run(tmp_path, results, hwpx=True):
    args = []
    for k, v in results.items():
        p = tmp_path / f"{k}.json"
        p.write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
        args += [f"--{k}", str(p)]
    h = tmp_path / "r01_보고.hwpx"
    if hwpx:
        h.write_bytes(b"PK")
    out = tmp_path / "40_qa.md"
    code = qa.main(args + ["--hwpx", str(h), "-o", str(out)])
    return code, out.read_text(encoding="utf-8")


def test_all_checks_pass_is_deliverable(tmp_path):
    code, text = _run(tmp_path, OK)
    assert code == 0 and "인도 가능" in text


def test_compare_mismatch_blocks_delivery(tmp_path):
    bad = dict(OK, compare={"issues": [{"rule": "content-dropped", "values": ["MCP"]}]})
    code, text = _run(tmp_path, bad)
    assert code == 1 and "인도 보류" in text and "내용 대조 불일치" in text


def test_missing_required_stage_blocks_delivery(tmp_path):
    partial = {k: v for k, v in OK.items() if k != "compare"}
    code, text = _run(tmp_path, partial)
    assert code == 1 and "내용 대조 결과 없음" in text


def test_numbers_are_optional_but_unsourced_numbers_block(tmp_path):
    assert _run(tmp_path, {k: v for k, v in OK.items() if k != "numbers"})[0] == 0   # 팩트체크 생략은 허용
    code, text = _run(tmp_path, dict(OK, numbers={"issues": [{"rule": "numbers-unsourced"}]}))
    assert code == 1 and "근거 없는 수치" in text


def test_missing_hwpx_blocks_delivery(tmp_path):
    code, text = _run(tmp_path, OK, hwpx=False)
    assert code == 1 and "인도본 파일 없음" in text


def test_line_overflow_is_reported_not_blocking(tmp_path):
    over = json.loads(json.dumps(OK))
    over["postprocess"]["line_fit"] = {"overflow": 1, "overflow_detail": [{"text": "긴 문단", "chars": 90, "lines": 3}]}
    code, text = _run(tmp_path, over)
    assert code == 0 and "2줄 넘침" in text and "3줄 추정" in text
