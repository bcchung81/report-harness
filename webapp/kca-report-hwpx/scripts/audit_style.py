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
# 명사 자체가 함·임·음으로 끝나는 말은 종결어미가 아니다('26.9.1 교훈 — '위임'·'책임'을 위반으로 오검출).
# 목록에 든 명사만 통과시킨다 — '정함·전함·급함'(한 글자 줄기 ~하다 활용)·'안임'(명사 + 서술격)은 모양이 같아
# 음절 수로는 가를 수 없다('26.9.25 코드 리뷰). 목록 밖의 명사는 어순을 바꾸거나 목록에 더한다.
NOUN_ENDING_OK = {
    "포함", "불포함", "결함", "위임", "재위임", "책임", "모임", "부임", "선임", "연임", "재임", "겸임", "전임", "후임",
    "신임", "일임", "방임", "소임", "직임", "퇴임", "취임", "이임", "사임", "해임", "담임", "보임",
    "운임", "주임", "상임", "비상임", "적임", "중임", "유임", "초임", "특임", "역임",
    "보관함", "우편함", "사서함", "투표함", "잠수함", "군함",
    "게임", "프레임", "타임", "처음", "다음", "마음", "소음", "녹음", "발음", "모음", "이음", "얼음", "웃음", "믿음", "물음"}


def external_citation(line):
    """외부 자료를 인용한 줄인가 — 외부 주체(국가·국제기구·기관 약칭·자료명 「…」)와 근거어가 함께 있어야 한다.
    자료명은 법령명·짧은 강조(「잠정」)가 아닐 때만 주체로 보고, 근거어는 「…」 밖에서만 찾는다(제목 속 '기준'·'70%').
    한계: 기관 자체 문서도 「…」로 적고 근거어를 붙이면 외부 인용으로 본다 — 경고일 뿐이라 내부 문서면 넘긴다."""
    titles = [t for t in DOC_TITLE.findall(line) if len(t.strip()) >= 5 and not LAW_TITLE.search(t.strip())]
    rest = DOC_TITLE.sub(" ", line)
    return bool((titles or EXTERNAL_ENTITY.search(rest)) and EVIDENCE.search(rest))


def _title_overflows(title):
    """제목이 제목표 한 줄(24pt)에 들지 않는가 — 후처리·리뷰 화면과 같은 fit_title로 잰다. 변환 뒤에야 2쪽이 된 것을
    알고 승인된 초안을 줄이던 것을 집필 단계로 당긴다('26.9.25 하네스 실전 점검: 37자 제목이 2줄로 넘쳐 1쪽 초과).
    후처리 모듈을 못 읽는 환경이면 검사를 건너뛴다."""
    try:
        from postprocess_hwpx import fit_title, curly, TITLE_TEXT_WIDTH_HU
    except Exception:
        return False
    # 인도본 제목은 kordoc이 따옴표를 둥근따옴표(전각)로 바꾼 글자다 — 곧은따옴표(반각)로 재면 한 줄로 오판한다(리뷰 #4)
    return fit_title(curly(title.strip()), TITLE_TEXT_WIDTH_HU / 100.0)[2]


def _source_count(line):
    """출처 줄에 적힌 자료 수 — ';'로 나눈 칸과 「자료명」 수 중 큰 값."""
    body = SOURCE_LINE.sub("", line)
    return max(len([p for p in body.split(";") if p.strip()]), body.count("「"))


def bad_ending(body):
    """본문 종결이 ~함·~임·~음·~됨(style-guide §4 철칙 위반)인가 — 명사 자체의 받침 끝은 빼고 본다."""
    if not BAD_ENDING.search(body):
        return False
    m = ENDING_WORD.search(body)
    word = m.group(1) if m else ""
    return word not in NOUN_ENDING_OK
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
    r"개선\(안\)|계획|현황|지침|매뉴얼|질의(?:서)?|회신|요청(?:서)?|협조\s*요청)\s*(?:\(안\))?\s*$"
)
# ── style-guide §1 [철칙]: 제목 아래 발신 줄 ────────────────────────────────
SENDER = re.compile(r"^<\s*'\d{2}\.\s*\d{1,2}\.\s*\d{1,2}\.\(.+?\),.+>")

# ── style-guide §7: 절 제목 어휘 풀 (코퍼스 출현) ───────────────────────────
SECTION_POOL = {
    "추진 배경", "개 요", "개요", "검토 배경", "현황 및 문제점", "그간의 경과",
    "주요 내용", "추진 내용", "조사결과", "조사 결과", "검토 결과", "검토 사항",
    "개선 방안", "기대 효과", "시사점", "주요 시사점", "향후 계획", "향후 일정",
    "추진 일정", "추진 방법", "추진 체계", "추진 과제", "기관별 보유 자료",
    # 결과보고 절 구성 표준(R054: 추진 배경 → 추진 내용 → 추진 성과 → 운영 전환 → 향후 계획) — 규칙대로 쓴 초안을
    # 어휘 밖으로 잡았다('26.9.25 하네스 실전 점검)
    "추진 성과", "운영 전환",
    # 질의서·요청 문서 계열('26.9.1 교훈 — 단신 요약보고 어휘만 있어 질의서가 title-no-suffix·offpool 4건)
    "질의 배경", "질의 사항", "질의 내용", "요청 사항", "요청 내용", "협조 요청 사항", "협조 사항", "회신 요청",
}
# 절 제목에 붙는 (안)·번호 등을 떼고 비교한다.
SECTION_NUM = re.compile(r"^\s*[0-9IVXⅠ-Ⅹ]+\s*[.．]\s*")
SECTION_SUFFIX = re.compile(r"\s*[①-⑳]\s*(?:[:：].*)?$|\s*[:：].*$")
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
# R092 — 외부 자료 인용 ※ 줄은 출처 줄(`※ 자료: 기관, 「자료명」(연도), 쪽`)을 단다. '26.9.25 1127 검증에서 외부 인용 5건 중
# 규격 출처 줄이 0건이었다(METR·영국 정부는 기관명만, 정부 원문 산식은 출처 없음). 오탐 여지가 있어 warnings.
SOURCE_LINE = re.compile(r"^\s*※\s*(?:자료|출처)\s*:")
NOTE_LINE = re.compile(r"^\s*※\s*(?:주|단|참고|비고)\s*[:：,)]")   # 인용에 붙는 단서 줄 — 새 인용이 아니다
# 외부 인용 = 외부 주체 + 근거어, 두 신호가 함께 있을 때만('26.9.25 운영 초안 14건 재점검: 한 신호로 보면 내부 약호
# '(T3)'·'(REJ)', 법령명 「…법률」, 강조 괄호 「잠정」, 내부 문서 「… 방안」 참조, 국가명만 든 판단 문장까지 잡아 12건이 오탐)
EXTERNAL_ENTITY = re.compile(r"미국|영국|일본|독일|프랑스|캐나다|중국|호주|싱가포르|(?<![A-Za-z])(?:EU|OECD|UN|IMF)(?![A-Za-z])|"
                             r"세계은행|해외|국외|동종|(?:기관|기구|연구소|연구원|협회|위원회|대학|정부)\s*\([A-Z][A-Za-z0-9]{2,}\)|"
                             # 한글 이름 + 괄호 원어·약칭 — 맥킨지(McKinsey)·진흥원(NIA)·포럼(WEF). 내부 약호 (T3)는 숫자가 섞여
                             # 빠지고, (REJ)처럼 글자만인 약호는 근거어가 없으면 걸리지 않는다('26.9.25 코드 리뷰 #3)
                             r"[가-힣]{2,}\s*\([A-Z][A-Za-z&.\-]+(?:\s[A-Za-z&.\-]+)*\)")
EVIDENCE = re.compile(r"연구|조사|실험|통계|보고서|백서|논문|설문|발표|사례|실적|규칙|기준|방법론|가이드|평가|분석|추정|전망|"
                      r"\d+(?:\.\d+)?\s*(?:%|배)")
DOC_TITLE = re.compile(r"「([^」]+)」")
# 법령은 이름이 곧 출처다. '방법·기법·해법' 등으로 끝나는 자료명은 법령이 아니다('26.9.25 코드 리뷰 #3)
LAW_TITLE = re.compile(r"(?:(?<![방기해어문용화수필요비마편])법|법률|령|규칙|규정|지침|고시|훈령|예규|조례)$")
INLINE_SOURCE = re.compile(r"「[^」]+」.*'\d{2}.*\d+쪽")      # 문장 안에 자료명·연도·쪽이 모두 있으면 출처 줄로 본다
HIER_LEAD = re.compile(r"^\s*(□|ㅇ|○|-)\s")


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
    # R054 결과보고의 추진 성과·운영 전환은 내용 단계(3)로 둔다 — 효과(4)로 두면 결과보고의 자연스러운 흐름
    # '추진 성과 → 검토 결과(3)'를 역전으로 잡는다('26.9.25 하네스 실전 점검 채점). 같은 순위끼리는 순서를 따지지 않는다
    "추진 성과": 3, "운영 전환": 3,
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
        if _title_overflows(title):
            w.append({"line": 1, "rule": "title-two-lines",
                      "text": f"제목이 제목표 한 줄을 넘어 2줄로 조판된다 — 결론을 담은 채 줄인다(짧은 분량이면 쪽이 넘친다): {title[:40]}"})
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
            key = SECTION_SUFFIX.sub("", key).strip()       # '검토 결과 ① : 부제' → '검토 결과'(풀 어휘 + 번호·부제)
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

        if SOURCE_LINE.match(stripped):     # 출처 줄은 자료명(원어 제목·약칭)이라 쉬운 말·종결 검사 대상이 아니다
            continue
        if stripped.startswith("※") and external_citation(stripped) and not INLINE_SOURCE.search(stripped):
            sourced, later = False, 0
            for nxt in lines[i:]:           # 다음 ㅇ·□·대시 전까지(표·도식 캡션을 건너) 출처 줄을 찾는다
                s = nxt.strip()
                if SOURCE_LINE.match(s):
                    # 인용이 잇따르면 출처 줄 하나에 ';'로 함께 적는다 — 건너온 뒤 인용보다 자료가 많아야 이 인용 것도 있다
                    # (종전에는 다음 인용에서 멈춰 공유 출처 줄을 못 봤다 — '26.9.25 코드 리뷰 #2)
                    sourced = _source_count(s) > later
                    break
                if HIER_LEAD.match(s) or ANNEX_BANNER.match(s):
                    break
                if s.startswith("※") and external_citation(s) and not NOTE_LINE.match(s):
                    later += 1              # 뒤 인용 — 그 출처 줄이 이 인용 것까지 적었는지는 자료 수로 가린다
            if not sourced:
                w.append({"line": i, "rule": "source-line-missing",
                          "text": f"외부 자료 인용에 출처 줄 없음 — 아래에 '※ 자료: 기관, 「자료명」(연도), 쪽'(R092): {stripped[:40]}"})
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
            if bad_ending(body):
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


# ── R093: 도식 카드 문장 — 초안의 `도해: 슬러그`가 가리키는 figures/{슬러그}.json 명세 ─────────────
# 카드 안 문장도 본문과 같은 공문서 문장이다('26.9.25 게이트② f11·f12 — `처리시간 = …` 등호 정의식,
# `과제당 3개, 18건 54개` 숫자 나열). 오탐 여지가 있어 전부 warnings. 명세가 없는 환경(웹앱)에서는 아무것도 안 한다.
FIG_MARKER = re.compile(r"^\s*도[해식]:\s*(\S+)\s*$")
FIG_FORMULA = re.compile(r"=|\s\+\s|[×÷]")
FIG_FRAGMENT = re.compile(r"\d+\s*(?:개|건|칸|종|명|곳|회|%|개소|단계)\)?$")


def _card_texts(node):
    """명세 안 카드의 (머리·화살표 문구, 본문 항목) — `body`를 가진 노드면 어디에 있든 카드로 본다."""
    heads, bodies = [], []
    if isinstance(node, dict):
        if "body" in node:
            body = node["body"]           # 명세 오류(null·숫자)로 감사 전체가 멈추지 않게 — 문자열만 모은다
            bodies += [body] if isinstance(body, str) else \
                [b for b in body if isinstance(b, str)] if isinstance(body, (list, tuple)) else []
        heads += [node[k] for k in ("head", "arrow") if isinstance(node.get(k), str)]
        for k, v in node.items():
            if k != "body":
                h, b = _card_texts(v)
                heads += h
                bodies += b
    elif isinstance(node, list):
        for v in node:
            h, b = _card_texts(v)
            heads += h
            bodies += b
    return heads, bodies


def audit_figures(md_path, text):
    """초안이 부르는 도식 명세의 카드 문장 경고 — 산식 기호(`diagram-formula`)·숫자로 끝나는 나열(`diagram-fragment`)."""
    fig_dir = pathlib.Path(md_path).resolve().parent / "figures"
    w = []
    for i, line in enumerate(text.splitlines(), 1):
        m = FIG_MARKER.match(line)
        spec_path = fig_dir / f"{m.group(1)}.json" if m else None
        if not spec_path or not spec_path.is_file():
            continue
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        heads, bodies = _card_texts(spec)
        for t in heads + bodies:
            if FIG_FORMULA.search(t):
                w.append({"line": i, "rule": "diagram-formula",
                          "text": f"{m.group(1)}: '{t}' — 등호·산식 기호 없이 서술형으로, 산식은 1열 표로(R093)"})
        for t in bodies:
            if FIG_FRAGMENT.search(t.strip()):
                w.append({"line": i, "rule": "diagram-fragment",
                          "text": f"{m.group(1)}: '{t}' — 숫자로 끝나는 나열 대신 무엇을 하는지 동작명사로 끝맺는다(R093)"})
    return w


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
    try:
        warn += audit_figures(args[0], src)
    except Exception as e:                # 도식 명세 결함이 본문 감사 결과까지 삼키지 않게
        warn.append({"line": 0, "rule": "figure-audit-error", "text": f"도식 명세 감사 실패: {e}"[:120]})
    print(json.dumps({"violations": viol, "warnings": warn},
                     ensure_ascii=False, indent=1))
    sys.exit(1 if viol else 0)
