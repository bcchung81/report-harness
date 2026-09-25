"""원문 인용 블록(```text) — 린트·감사·prep·변환 입력·후처리·대조·리뷰가 같은 경계로 '글자 그대로' 다룬다('26.9.24)."""
import sys, pathlib, re
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import xml.etree.ElementTree as ET
import lint_md_profile as lint
import audit_style
import prep_report_md as prep
import to_kordoc_input as tki
import postprocess_hwpx as ph
import validate_hwpx as vh
import render_review_html as rr
from test_postprocess_hwpx import HEADER_XML, _fit_section

DOC = """시험 보고

< '26. 9. 24.(목), 경영기획본부 AI디지털심화팀 >

□ 개 요

ㅇ **(지시문 구성)** 담당자가 코드 에이전트에 그대로 붙여 넣는 지시문으로, 처리 조건만 기입해 모든 시스템에 공통 적용

[ 지시문 원문(발췌) ]

```text
역할: 표준 로그를 추출한다. 스키마 변경·데이터 수정은 하지 않는다.
[처리 조건 — 담당자가 채운다]
- 추출 기간: [YYYY-MM-DD] ~ [YYYY-MM-DD]

* 별표 줄
```

※ 전문은 별도 배포본으로 제공
"""


def test_lint_and_audit_skip_inside_and_check_fence():
    assert lint.lint_text(DOC) == []                       # 안쪽 줄표(—)·대시·별표는 린트 대상이 아니다
    assert audit_style.audit_text(DOC)[0] == []
    long = DOC.replace("* 별표 줄", "\n".join(f"줄 {i}" for i in range(lint.QUOTE_MAX_LINES)))
    assert [v["rule"] for v in lint.lint_text(long)] == ["quote-block-too-long"]
    assert [v["rule"] for v in lint.lint_text(DOC.replace("```text", "```python"))] == ["quote-block-lang"]
    assert lint.mask_fences(DOC).count("\n") == DOC.count("\n")   # 줄 번호 보존


def test_prep_keeps_quote_verbatim_and_converter_marks_lines():
    out = prep.prep(DOC)
    assert "* 별표 줄" in out and "＊ 별표 줄" not in out    # 인용 안 별표는 각주로 바꾸지 않는다
    conv, _ = tki.convert(out)
    assert "⁠- 추출 기간: [YYYY-MM-DD] ~ [YYYY-MM-DD]" in conv and "⁠\n" in conv   # 빈 줄도 표식
    assert "    - 추출 기간" not in conv                       # 대시로 바꾸지 않는다


def test_postprocess_boxes_quote_lines_and_is_idempotent():
    mark = ph.QUOTE_MARK
    paras = "".join(f'<hp:p paraPrIDRef="0" styleIDRef="0"><hp:run charPrIDRef="0"><hp:t>{t}</hp:t></hp:run></hp:p>'
                    for t in (f"{mark}- 추출 기간: [YYYY]", f"{mark}[처리 조건 — 담당자]", mark))
    sec = _fit_section(paras)
    header = ET.fromstring(HEADER_XML.encode("utf-8"))
    ph.refresh_quote_paraprs(header)
    ps = [p for p in sec.iter(ph.qn("hp", "p")) if mark in ph.para_text(p)]
    assert [ph.classify(p) for p in ps] == ["quote"] * 3      # 대시·캡션·빈 문단으로 읽지 않는다
    r = ph.apply_quote_block(header, [sec])
    assert (r["lines"], r["changed"], r["face"]) == (3, 3, ph.QUOTE_FACE)
    assert all(mark not in ph.para_text(p) for p in ps)
    h, _, _ = ph._charpr_metrics(header, ps[0].find(ph.qn("hp", "run")).get("charPrIDRef"))
    assert h == ph.QUOTE_SIZE_PT
    ph.refresh_quote_paraprs(header)                          # 재실행 — 표식 없이 상자 paraPr로 알아본다
    assert [ph.classify(p) for p in ps] == ["quote"] * 3
    assert ph.apply_quote_block(header, [sec])["changed"] == 0
    assert ph.transition_for("caption", "quote") == ph.transition_for("caption", "table")
    assert ph.transition_for("quote", "quote") is None


def test_compare_ignores_quote_markup_but_catches_lost_lines():
    rt = ("# 시험 보고\n\n< ’26. 9. 24.(목), 경영기획본부 AI디지털심화팀 >\n\n□ 개 요\n\n ㅇ **(지시문 구성)** 담당자가 코드 에이전트에 그대로 붙여 넣는 지시문으로, 처리 조건만 기입해 모든 시스템에 공통 적용\n\n"
          "[ 지시문 원문(발췌) ]\n\n역할: 표준 로그를 추출한다. 스키마 변경·데이터 수정은 하지 않는다.\n\n[처리 조건 — 담당자가 채운다]\n\n"
          "- 추출 기간: [YYYY-MM-DD] ~ [YYYY-MM-DD]\n\n* 별표 줄\n\n※ 전문은 별도 배포본으로 제공\n")
    rules = [i["rule"] for i in vh.compare_texts(DOC, rt)]
    assert not any(r.startswith("count-mismatch") for r in rules)
    lost = vh.compare_texts(DOC, rt.replace("* 별표 줄\n\n", ""))
    assert any(i["rule"] == "content-dropped" and "* 별표 줄" in i["values"] for i in lost)


def test_review_draws_quote_box_with_address():
    blocks = rr.address(rr.parse(DOC))
    q = next(b for b in blocks if b["kind"] == "quote")
    assert q["addr"] == "□1-인용1" and len(q["lines"]) == 5
    doc, _ = rr.render(DOC)
    assert '<pre class="quote">' in doc and "- 추출 기간: [YYYY-MM-DD]" in doc and "pre.quote" in doc
