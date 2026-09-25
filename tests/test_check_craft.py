"""보고서 설계 칸 검사(R094) — report-craft.md §1·§2 칸이 산출물에 있는지만 본다."""
import sys, json, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import check_craft as cc

CONTEXT_OK = """# 00_context

- 요구: 요약본

## 보고 설계
- 보고 목적: AI 성과 측정 체계를 결재받는다
- 결재자·수신자: 소속 부서장
- 결재자가 내릴 결정: 측정 체계 승인
- 예상 결론: 검수 시간을 포함한 실측만 인정하는 체계 마련
- 상황 전제: 없음(확인함)
"""

OUTLINE_OK = """# 10_outline

## 1. 목차
### □1 개 요
### □2 주요 내용

## 설계 점검
- 제목(결론): 검수 시간을 포함한 AI 성과 측정 체계 마련 방안
- 핵심 메시지: 실측만 인정해 착시를 막는다
- 근거 구조: ① 착시 사례 ② 산식 재정의 ③ 표준 기록 (겹침 없음)
- 절별 So What:
  - □ 개 요 — 결론과 흐름을 먼저 준다
  - □ 주요 내용 — 무엇을 어떻게 재는지 정한다
- 구성요소: 목적 O · 현황 O · 핵심 메시지 O · 대안 X(단일안 보고) · 결론 O · 향후계획 O
- 상위 계획 대응: 없음(확인함)
"""


def _w(tmp_path, name, text):
    (tmp_path / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_context_block_complete_passes(tmp_path):
    assert cc.check("context", _w(tmp_path, "00_context.md", CONTEXT_OK)) == []


def test_context_missing_block_or_empty_field(tmp_path):
    assert "블록 없음" in cc.check("context", _w(tmp_path, "00_context.md", "# 00_context\n- 요구: 요약\n"))[0]
    text = (CONTEXT_OK.replace("- 상황 전제: 없음(확인함)\n", "- 상황 전제: {의사결정 전/후}\n")
            .replace("- 예상 결론: 검수 시간을 포함한 실측만 인정하는 체계 마련\n", ""))
    missing = cc.check("context", _w(tmp_path, "00_context.md", text))
    assert any(m.startswith("상황 전제 — 비어") for m in missing)        # 자리표시만 있으면 빈 칸
    assert any(m.startswith("예상 결론 — 칸 없음") for m in missing)


def test_outline_block_complete_passes(tmp_path):
    assert cc.check("outline", _w(tmp_path, "10_outline.md", OUTLINE_OK)) == []


def test_outline_so_what_must_cover_every_section(tmp_path):
    text = OUTLINE_OK.replace("### □2 주요 내용\n", "### □2 주요 내용\n### □3 향후 계획\n")
    assert any("절 3개 중 2개" in m for m in cc.check("outline", _w(tmp_path, "10_outline.md", text)))


def test_outline_parts_must_all_be_compared(tmp_path):
    text = OUTLINE_OK.replace(" · 대안 X(단일안 보고)", "")
    assert any(m.startswith("구성요소 — 대안") for m in cc.check("outline", _w(tmp_path, "10_outline.md", text)))


def test_cli_exit_codes(tmp_path, capsys):
    _w(tmp_path, "00_context.md", CONTEXT_OK)
    assert cc.main(["context", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert cc.main(["outline", str(tmp_path)]) == 2                    # 10_outline.md 없음
    assert cc.main(["draft", str(tmp_path)]) == 2
