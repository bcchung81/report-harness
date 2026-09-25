#!/usr/bin/env python3
"""보고서 설계 칸 검사 — `references/report-craft.md` §1·§2의 칸이 산출물에 있는지만 본다(R094).

칸에 쓴 판단이 좋은지는 게이트에서 사용자가 본다. 여기서는 빠진 칸·빈 칸만 결정론으로 잡는다 —
목적을 잊은 채 자료를 늘어놓거나, 착수 뒤에야 상황 전제가 드러나 논지를 버리는 일을 막으려는 것이다.

    check_craft.py context {work_dir}   # 00_context.md의 `## 보고 설계`
    check_craft.py analysis {work_dir}  # 05_analysis.md의 4개 절 — 논지 후보·총괄표 후보·근거 공백·인용 재료 목록
    check_craft.py outline {work_dir}   # 10_outline.md의 `## 설계 점검` (절별 So What은 □ 절 수만큼)

exit 0: 칸 모두 있음 | exit 1: 빠진 칸 있음(JSON `missing`) | exit 2: 인자·파일 오류
"""
import json
import pathlib
import re
import sys

CONTEXT = ("00_context.md", "보고 설계",
           ("보고 목적", "결재자·수신자", "결재자가 내릴 결정", "예상 결론", "상황 전제"))
OUTLINE = ("10_outline.md", "설계 점검",
           ("제목(결론)", "핵심 메시지", "근거 구조", "절별 So What", "구성요소", "상위 계획 대응"))
PARTS = ("목적", "현황", "핵심 메시지", "대안", "결론", "향후계획")
# 분석 문서의 절 — 제목에 이 말이 들어간 헤딩이 있어야 한다(SKILL.md ② analyze 2, R092 인용 재료 목록)
ANALYSIS = ("논지 후보", "총괄표", "근거 공백", "인용 재료")
SECTION_HEAD = re.compile(r"^#{2,4}\s*□\s*\d*\s*\S")          # 아웃라인의 절 제목 줄(`### □1 개 요`)
PLACEHOLDER = re.compile(r"^\{.*\}$|^…$|^\.\.\.$")


def block(text, title):
    """`## {title}` 블록 본문 — 다음 `## ` 제목 전까지. 없으면 None."""
    m = re.search(rf"^##\s*{re.escape(title)}\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    return m.group(1) if m else None


def fields(body):
    """`- 칸: 값` 줄 → {칸: 값}. 값이 다음 줄 하위 목록으로 이어지면 그 줄들을 값으로 모은다."""
    out, cur = {}, None
    for line in body.splitlines():
        m = re.match(r"^-\s*([^:：]+?)\s*[:：]\s*(.*)$", line)
        if m:
            cur = m.group(1).strip()
            out[cur] = m.group(2).strip()
        elif cur and re.match(r"^\s{2,}-\s*\S", line):
            out[cur] = (out[cur] + "\n" + line.strip()).strip()
    return out


def check(kind, work_dir):
    if kind == "analysis":
        text = (pathlib.Path(work_dir) / "05_analysis.md").read_text(encoding="utf-8")
        heads = [l for l in text.splitlines() if l.lstrip().startswith("#")]
        return [f"`{k}` 절 없음 — 05_analysis.md에 제목을 둔다(SKILL ② analyze)"
                for k in ANALYSIS if not any(k in h for h in heads)]
    name, title, need = CONTEXT if kind == "context" else OUTLINE
    path = pathlib.Path(work_dir) / name
    text = path.read_text(encoding="utf-8")
    body = block(text, title)
    if body is None:
        return [f"`## {title}` 블록 없음 — report-craft.md §{1 if kind == 'context' else 2} 형식으로 덧붙인다"]
    got = fields(body)
    missing = [f"{k} — 칸 없음" for k in need if k not in got]
    missing += [f"{k} — 비어 있음" for k in need if k in got and (not got[k] or PLACEHOLDER.match(got[k]))]
    if kind == "outline":
        sowhat = [l for l in got.get("절별 So What", "").splitlines() if l.lstrip("- ").startswith("□")]
        sections = [l for l in text.splitlines() if SECTION_HEAD.match(l)]
        if got.get("절별 So What") and not sowhat:
            missing.append("절별 So What — □ 절마다 한 줄씩 적는다")
        elif sowhat and sections and len(sowhat) < len(sections):
            missing.append(f"절별 So What — 절 {len(sections)}개 중 {len(sowhat)}개만 있음")
        parts = got.get("구성요소", "")
        absent = [p for p in PARTS if p not in parts]
        if parts and absent:
            missing.append(f"구성요소 — {'·'.join(absent)} 대조 누락(빠지면 X와 사유)")
    return missing


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2 or args[0] not in ("context", "analysis", "outline"):
        print("usage: check_craft.py {context|analysis|outline} {work_dir}", file=sys.stderr)
        return 2
    try:
        missing = check(args[0], args[1])
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps({"kind": args[0], "ok": not missing, "missing": missing}, ensure_ascii=False, indent=1))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
