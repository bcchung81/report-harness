"""style-guide 결정론 감사 (spec §6 4단방어-①의 보완). stdlib-only.

`lint_md_profile.py`는 **마크다운 문법·계층 구조·밀도**만 본다(md-profile §4가 종결어미·
절 제목·문서 제목을 "스코프 아웃 — 스타일 감사가 2차 방어"로 넘겨 두었다). 그 2차 방어를
사람 판단에만 맡겼더니 실제로 통째로 누락되는 사고가 났다('26.8.15 3기관 협의자료 —
전 문장이 `~함/~됨` 종결로 작성됐으나 린트 통과, R074·R075).

이 스크립트는 그중 **정규식으로 안전하게 판정되는 항목만** 골라 결정론화한다. 오탐 위험이
있는 항목은 `violations`가 아니라 `warnings`로 내보내 사람이 판단하게 한다.

- violations (exit 1): style-guide 철칙 위반이면서 오탐이 거의 없는 것
- warnings  (exit 0): 문서 유형에 따라 합법일 수 있어 사람 확인이 필요한 것
"""
import sys, json, re

# ── style-guide §2: 계층 부호 ────────────────────────────────────────────────
LEAD = re.compile(r"^\s*(□|ㅇ|○|-|※|＊)\s")
BODY_LEAD = re.compile(r"^\s*(ㅇ|○|-|※)\s")     # 종결어미 검사 대상 계층
SECTION = re.compile(r"^\s*□\s*(.+?)\s*$")
TABLE = re.compile(r"^\s*\|")

# ── style-guide §4 [철칙]: "~함/~임/~음" 종결은 본문에서 쓰지 않는다 ──────────
# 예외는 RFP("~하여야 함")와 붙임 회의록("~답변함")뿐이므로, 그 두 형태는 제외한다.
BAD_ENDING = re.compile(r"(?:함|임|음|됨)$")
ENDING_EXEMPT = re.compile(r"(?:하여야\s*함|답변함|질의함|설명함|보고함)$")
# 인용부호 안에서 끝나는 경우(원문 인용)는 대상이 아니다.
QUOTED_TAIL = re.compile(r"[\"”』」]\s*$")

# ── style-guide §1 [철칙]: 문서 제목 = 명사구 + 문서유형 접미 ────────────────
TITLE_SUFFIX = re.compile(
    r"(?:보고|검토\s*결과|계획\(안\)|추진계획\(안\)|결과\s*보고|방안(?:\(안\))?|"
    r"개선\(안\)|계획|현황|지침|매뉴얼)\s*(?:\(안\))?\s*$"
)
# ── style-guide §1 [철칙]: 제목 아래 발신 줄 ────────────────────────────────
SENDER = re.compile(r"^<\s*'\d{2}\.\s*\d{1,2}\.\s*\d{1,2}\.\(.+?\),.+>")

# ── style-guide §7: 절 제목 어휘 풀 (코퍼스 출현) ───────────────────────────
SECTION_POOL = {
    "추진 배경", "개 요", "개요", "검토 배경", "현황 및 문제점", "그간의 경과",
    "주요 내용", "추진 내용", "조사결과", "조사 결과", "검토 결과", "검토 사항",
    "개선 방안", "기대 효과", "시사점", "주요 시사점", "향후 계획", "향후 일정",
    "추진 일정", "추진 방법", "추진 체계", "추진 과제", "기관별 보유 자료",
}
# 절 제목에 붙는 (안)·번호 등을 떼고 비교한다.
SECTION_NUM = re.compile(r"^\s*[0-9IVXⅠ-Ⅹ]+\s*[.．]\s*")
# 붙임 배너(style-guide §8, 3열 표) 이후의 □는 붙임 내부 구조라 본문 절 어휘 풀 대상이 아니다.
ANNEX_BANNER = re.compile(r"^\s*\|\s*붙\s*임")

# ── 조문 표기: § 기호 대신 한국식 전체 표기 (R075) ──────────────────────────
ARTICLE_SYMBOL = re.compile(r"§\s*\d")


def _strip_markup(text: str) -> str:
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"\[(?:확정|추정)[^\]]*\]", "", text)
    return text.strip()


def audit_text(text: str):
    """(violations, warnings) 두 목록을 돌려준다."""
    lines = text.split("\n")
    v, w = [], []
    in_annex = False

    # 1. 문서 제목·발신 줄 (파일 선두 5줄 안)
    head = [l for l in lines[:6] if l.strip()]
    if head:
        title = _strip_markup(head[0])
        if not TITLE_SUFFIX.search(title):
            v.append({"line": 1, "rule": "title-no-suffix", "text": title[:80]})
        if len(head) < 2 or not SENDER.match(head[1].strip()):
            w.append({"line": 2, "rule": "sender-line-missing",
                      "text": (head[1][:80] if len(head) > 1 else "")})

    # 2. 절 제목·종결어미·조문 표기
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if ANNEX_BANNER.match(stripped):
            in_annex = True
        if not stripped or TABLE.match(stripped):
            continue

        m = SECTION.match(stripped)
        if m:
            raw = _strip_markup(m.group(1))
            if SECTION_NUM.match(raw):
                v.append({"line": i, "rule": "section-numbered", "text": raw[:80]})
            key = SECTION_NUM.sub("", raw)
            key = re.sub(r"\(안\)\s*$", "", key).strip()
            if not in_annex and key not in SECTION_POOL:
                w.append({"line": i, "rule": "section-title-offpool", "text": raw[:80]})
            continue

        if ARTICLE_SYMBOL.search(stripped):
            v.append({"line": i, "rule": "article-symbol", "text": stripped[:80]})

        if BODY_LEAD.match(stripped):
            # 계층 문구는 이어지는 줄까지 하나의 문장이므로 다음 선두 전까지 이어 붙인다.
            buf = stripped
            for nxt in lines[i:]:
                s = nxt.strip()
                if not s or TABLE.match(s) or LEAD.match(s):
                    break
                buf += " " + s
            body = _strip_markup(buf)
            if QUOTED_TAIL.search(body) or ENDING_EXEMPT.search(body):
                continue
            if BAD_ENDING.search(body):
                v.append({"line": i, "rule": "ending-forbidden", "text": body[-60:]})
    return v, w


if __name__ == "__main__":
    # exit 계약: 0 통과(경고만 있어도 0) / 1 철칙 위반 / 2 인자·파일 오류
    if len(sys.argv) != 2:
        print("usage: audit_style.py <draft.md>", file=sys.stderr)
        sys.exit(2)
    try:
        src = open(sys.argv[1], encoding="utf-8").read()
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    viol, warn = audit_text(src)
    print(json.dumps({"violations": viol, "warnings": warn},
                     ensure_ascii=False, indent=1))
    sys.exit(1 if viol else 0)
