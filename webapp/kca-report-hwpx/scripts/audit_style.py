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
import sys, json, re, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lint_md_profile import mask_fences   # noqa: E402  (인용 블록 경계 단독 출처)

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

# ── style-guide §4 [철칙] 보완(R080): 같은 종결 명사를 절 안에서 되풀이하지 않는다 ──
# 동작명사 종결이 표준이므로 종결 자체는 금지할 수 없다 — 반복만 검출한다.
ENDING_REPEAT_FAIL = 3     # 절 안 3회 이상 → violation
ENDING_REPEAT_WARN = 2     # 2회 → warning
ENDING_WORD = re.compile(r"([가-힣A-Za-z]+)\s*$")   # "…을 확인" → "확인"

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

# ── R003: 신뢰도 태깅은 작업 표기 — 인도본 본문에 노출하지 않는다 ──────────
CONFIDENCE_TAG = re.compile(r"\[(?:확정|추정)[^\]]*\]")

# ── R077: 본문에 조문 번호를 나열하지 않는다(붙임 대조표로 배출) ────────────
ARTICLE_NO = re.compile(r"제\d+조(?:의\d+)?(?:제\d+항)?(?:제\d+호(?:의\d+)?)?")

# ── R091: 쉬운 말·두괄식 (style-guide §11 — 국어기본법 제14조, 국립국어원 「쉬운 공문서 쓰기 길잡이」) ──
# 용어표·허용 약어는 style-guide.md가 단일 출처다(웹앱 사본에도 같은 파일이 실린다). 전부 warnings —
# 문맥상 합법일 수 있어 사람이 판단한다. 대상은 본문(붙임 앞) 계층 문구뿐이다.
STYLE_GUIDE = pathlib.Path(__file__).resolve().parent.parent / "references" / "style-guide.md"
ABBR = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9&]+(?![A-Za-z0-9])")
# 연결 어미(절 이음) — 쉼표 없이 잇는 경우가 많아 어미로 센다. '보고·참고'처럼 명사로 끝나는 말은 걸리지 않게
# 동사 어미 형태(…하고·…해·…쳐·한 뒤)만 본다
CLAUSE = re.compile(r"[가-힣]+(?:하고|하며|하여|되어|되고|되며|이며|으며|하되|지만|는데|면서|거나)(?=[\s,])"
                    r"|[가-힣]{2,}해(?=[\s,])|[가-힣]+쳐(?=[\s,])|한 뒤|마친 뒤")
HISTORY = re.compile(r"그간|그동안|기존에는|당초|거쳐|되짚어|한 뒤|마친 뒤|경위")
BACKGROUND_START = re.compile(r"^(?:그간|그동안|기존|최근|현재|종전|당초|지난|앞서)")
BACKGROUND_CLAUSE = re.compile(r"에 따라|에 따른|을 위해|를 위해|위하여|관련하여|과 관련|와 관련")
NOUN_TOKEN = re.compile(r"^[가-힣0-9·]{2,}$")
NOT_BARE = ("을", "를", "이", "가", "은", "는", "의", "에", "로", "와", "과", "도", "만", "서", "고", "며", "해",
            "여", "게", "지", "한", "할", "된", "될", "인", "적", "등", "함", "음", "임", "됨", "및", "며")
NOUN_CHAIN = 5
LEAD_PAREN = re.compile(r"^\s*(?:ㅇ|○|-|※)\s*(?:\([^)]*\)\s*)?")


def load_plain_words(path=STYLE_GUIDE):
    """style-guide §11 용어표·허용 약어 — ({쓰지 않을 말: 바꿀 말}, 허용 약어 집합). 파일이 없으면 빈 값."""
    try:
        t = pathlib.Path(path).read_text(encoding="utf-8")
    except OSError:
        return {}, set()
    words = {}
    m = re.search(r"<!-- plain-words -->(.*?)<!-- /plain-words -->", t, re.S)
    if m:
        for row in re.finditer(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", m.group(1), re.M):
            k, v = row.group(1), row.group(2)
            if k != "쓰지 않을 말" and not set(k) <= set("-: "):
                words[k] = v
    a = re.search(r"^허용 약어:\s*(.+)$", t, re.M)
    return words, ({x.strip() for x in a.group(1).split(",")} if a else set())


PLAIN_WORDS, ABBR_OK = load_plain_words()


def _noun_run(text):
    """조사·어미 없이 이어진 명사 어절의 최장 구간(길잡이 49쪽 '명사 나열')."""
    best, cur = [], []
    for tok in text.split():
        bare = NOUN_TOKEN.match(tok) and not tok.endswith(NOT_BARE)
        cur = cur + [tok] if bare else []
        if len(cur) > len(best):
            best = cur
    return best


def _plain_checks(i, body, w, words_seen, abbr_seen):
    """R091 — 한 계층 문구(이어진 줄 포함)의 쉬운 말 검사. 용어·약어는 문서 단위로 모아 끝에서 1건씩."""
    text = LEAD_PAREN.sub("", body)
    for k in PLAIN_WORDS:
        n = text.count(k)
        if n:
            words_seen.setdefault(k, [i, 0])[1] += n
    for m in ABBR.finditer(text):
        ab = m.group(0)
        if ab in ABBR_OK or ab in abbr_seen:
            continue
        before, after = text[:m.start()], text[m.end():]
        explained = bool(re.search(r"[가-힣]\s*\(\s*$", before) and after.lstrip().startswith(")")) \
            or bool(re.match(r"\s*\([가-힣]", after))
        abbr_seen[ab] = (i, explained)
    n = len(CLAUSE.findall(text)) + len(re.findall(r"\s및\s", text))
    if n >= 2:
        w.append({"line": i, "rule": "clause-chain", "text": f"한 문장에 이음 {n + 1}개 — 나눠 쓴다: {text[:50]}"})
    run = _noun_run(text)
    if len(run) >= NOUN_CHAIN:
        w.append({"line": i, "rule": "noun-chain", "text": " ".join(run)[:60]})
    h = HISTORY.search(text)
    if h:
        w.append({"line": i, "rule": "history-narration", "text": f"'{h.group(0)}' — 경위보다 결과·판단을: {text[:50]}"})


def skeleton(text):
    """되말하기 점검용 뼈대 — 본문 □ 제목과 각 절 첫 ㅇ(R091, 길잡이 56쪽 환언 검사)."""
    out, cur = [], None
    for i, line in enumerate(mask_fences(text).split("\n"), 1):
        s = line.strip()
        if ANNEX_BANNER.match(s):
            break
        m = SECTION.match(s)
        if m:
            cur = {"section": _strip_markup(m.group(1)), "line": i, "first": ""}
            out.append(cur)
        elif cur is not None and not cur["first"] and re.match(r"^(ㅇ|○)\s", s):
            cur["first"] = _strip_markup(s)
    return out


# ── R076: 절 서사 순위 — 앞 순위가 뒤 순위보다 뒤에 오면 역전 ──────────────
SECTION_RANK = {
    "추진 배경": 1, "검토 배경": 1, "개 요": 1, "개요": 1,
    "현황 및 문제점": 2, "그간의 경과": 2, "조사결과": 2, "조사 결과": 2,
    "기관별 보유 자료": 2,
    "주요 내용": 3, "추진 내용": 3, "추진 과제": 3, "개선 방안": 3,
    "검토 결과": 3, "검토 사항": 3,
    "기대 효과": 4, "시사점": 4, "주요 시사점": 4,
    "추진 방법": 5, "추진 체계": 5,
    "향후 계획": 6, "향후 일정": 6, "추진 일정": 6,
}


def _strip_markup(text: str) -> str:
    text = re.sub(r"\*\*", "", text)
    text = re.sub(r"\[(?:확정|추정)[^\]]*\]", "", text)
    return text.strip()


def _flush_endings(section_endings, v, w):
    """R080 — 한 절(□ 블록)이 끝날 때 종결 명사 반복을 판정한다.

    3회 이상은 violation, 2회는 warning. 같은 말로 문장을 닫는 습관은 판단이 아니라
    관찰만 늘어놓게 만들어 문서를 딱딱하게 한다('26.9.6 사용자 반려 — 절 안 `확인` 3회,
    문서 전체 `필요` 6회·상태명사 종결 9회)."""
    for word, hits in section_endings.items():
        n = len(hits)
        if n >= ENDING_REPEAT_FAIL:
            v.append({"line": hits[ENDING_REPEAT_FAIL - 1], "rule": "ending-repeat",
                      "text": f"절 안에서 '{word}' 종결 {n}회 — 판단·행위 명사로 갈아 쓴다"})
        elif n >= ENDING_REPEAT_WARN:
            w.append({"line": hits[-1], "rule": "ending-repeat",
                      "text": f"절 안에서 '{word}' 종결 {n}회"})


def audit_text(text: str):
    """(violations, warnings) 두 목록을 돌려준다. 원문 인용 블록(```text) 안은 원문 그대로라 감사하지 않는다."""
    text = mask_fences(text)
    lines = text.split("\n")
    v, w = [], []
    in_annex = False
    ranks = []          # R076: (line, 절제목, 서사순위)
    article_hits = []   # R077: 본문 조문 인용 위치

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
    section_endings = {}
    words_seen, abbr_seen = {}, {}      # R091 — 문서 단위로 모아 끝에서 1건씩
    first_yo = False                    # R091 — 절 첫 ㅇ 두괄식 검사 대기
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if ANNEX_BANNER.match(stripped):
            in_annex = True
        if not stripped or TABLE.match(stripped):
            continue

        m = SECTION.match(stripped)
        if m:
            _flush_endings(section_endings, v, w)
            section_endings = {}
            raw = _strip_markup(m.group(1))
            if SECTION_NUM.match(raw):
                v.append({"line": i, "rule": "section-numbered", "text": raw[:80]})
            key = SECTION_NUM.sub("", raw)
            key = re.sub(r"\(안\)\s*$", "", key).strip()
            if not in_annex and key not in SECTION_POOL:
                w.append({"line": i, "rule": "section-title-offpool", "text": raw[:80]})
            if not in_annex and key in SECTION_RANK:
                ranks.append((i, key, SECTION_RANK[key]))
            first_yo = not in_annex
            continue

        if ARTICLE_SYMBOL.search(stripped):
            v.append({"line": i, "rule": "article-symbol", "text": stripped[:80]})

        if not in_annex and CONFIDENCE_TAG.search(stripped):
            v.append({"line": i, "rule": "confidence-tag-in-body", "text": stripped[:80]})

        if not in_annex and ARTICLE_NO.search(stripped):
            article_hits.append(i)

        if BODY_LEAD.match(stripped):
            # 계층 문구는 이어지는 줄까지 하나의 문장이므로 다음 선두 전까지 이어 붙인다.
            buf = stripped
            for nxt in lines[i:]:
                s = nxt.strip()
                if not s or TABLE.match(s) or LEAD.match(s):
                    break
                buf += " " + s
            body = _strip_markup(buf)
            if not in_annex:
                _plain_checks(i, body, w, words_seen, abbr_seen)
                if first_yo and re.match(r"^(ㅇ|○)\s", stripped):
                    first_yo = False
                    lead = LEAD_PAREN.sub("", body)
                    if BACKGROUND_START.match(lead) or BACKGROUND_CLAUSE.search(lead.split(",")[0][:25]):
                        w.append({"line": i, "rule": "lead-not-conclusion",
                                  "text": f"절 첫 ㅇ가 배경·경위로 시작 — 결론을 먼저: {lead[:50]}"})
            if QUOTED_TAIL.search(body) or ENDING_EXEMPT.search(body):
                continue
            if BAD_ENDING.search(body):
                v.append({"line": i, "rule": "ending-forbidden", "text": body[-60:]})
            em = ENDING_WORD.search(body)          # R080: 종결 명사 집계
            if em and not in_annex:
                # 붙임(회의록·대조표·전수 데이터)은 본문 산문 규칙의 대상이 아니다 —
                # confidence-tag-in-body·article-in-body와 같은 층위의 제외다. 붙임에서
                # 같은 종결이 겹치는 것은 자료 성격이지 문장 습관이 아니다.
                section_endings.setdefault(em.group(1), []).append(i)
    _flush_endings(section_endings, v, w)
    for k, (line, n) in words_seen.items():            # R091 — 용어별 1건
        w.append({"line": line, "rule": "plain-word", "text": f"'{k}' {n}회 → '{PLAIN_WORDS[k]}'"})
    for ab, (line, explained) in abbr_seen.items():
        if not explained:
            w.append({"line": line, "rule": "abbr-unexplained", "text": f"'{ab}' — 처음 한 번 우리말로 풀어 쓴다"})
    # R076: 서사 순위 역전
    for (l1, k1, r1), (l2, k2, r2) in zip(ranks, ranks[1:]):
        if r2 < r1:
            v.append({"line": l2, "rule": "section-order",
                      "text": f"{k1}(순위 {r1}) 뒤에 {k2}(순위 {r2})"})
    # R077: 본문 조문 나열 — 3개소 이상이면 붙임으로 배출할 신호
    if len(article_hits) >= 3:
        v.append({"line": article_hits[0], "rule": "article-in-body",
                  "text": f"본문 조문 인용 {len(article_hits)}개소 — 붙임 대조표로 배출"})
    return v, w


if __name__ == "__main__":
    # exit 계약: 0 통과(경고만 있어도 0) / 1 철칙 위반 / 2 인자·파일 오류
    args = [a for a in sys.argv[1:] if a != "--skeleton"]
    if len(args) != 1:
        print("usage: audit_style.py <draft.md> [--skeleton]", file=sys.stderr)
        sys.exit(2)
    try:
        src = open(args[0], encoding="utf-8").read()
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    if "--skeleton" in sys.argv:        # 되말하기 점검용 뼈대(R091) — 감사 없이 출력만
        print(json.dumps({"skeleton": skeleton(src)}, ensure_ascii=False, indent=1))
        sys.exit(0)
    viol, warn = audit_text(src)
    print(json.dumps({"violations": viol, "warnings": warn},
                     ensure_ascii=False, indent=1))
    sys.exit(1 if viol else 0)
