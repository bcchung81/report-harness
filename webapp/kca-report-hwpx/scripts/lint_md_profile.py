"""md-profile 결정론 린트 (spec §6 4단방어-①, AI 티 3중장치-①). stdlib-only.
개조식 기호(□ㅇ○-※＊)는 항목 '선두'에서만 합법. 그 외 위치의 마크다운 기호는 위반."""
import sys, json, re

ARROW = "\u2192"        # 수치 변화 표기 → (R065)
# 완성형(cp949) 미수용 유사 기호 — hwpx는 UTF-8이라 파일은 멀쩡하지만 본문을 완성형으로
# 뽑는 경로(자료교환 본문 검사·레거시 연계·euc-kr 적재)에서 깨진다. md-profile §1-3-2.
LOOKALIKE = {"\u2212": "-", "\u2024": "\u00b7", "\u2027": "\u00b7",
             "\u2010": "-", "\u2011": "-", "\ufe63": "-"}
FORMULA = re.compile(r"[^|]*=\s*[^=]*(?:[×÷−]|\s-\s)")  # 계층 문구 안 산식 (R064).
# 빼기는 하이픈 표기가 정본(md-profile §1-3-2 — U+2212는 완성형 미수용)이라
# 공백으로 감싼 하이픈도 산식 표지로 인정한다. U+2212는 구 문서 호환으로 남긴다.
LINE_CHARS = 35          # 휴먼명조 15pt·장평 95·본문폭 170mm 실측 1줄 글자수 (R062)
MAX_BODY_CHARS = 90      # 자간 -10·장평 90까지 조여 2줄에 들어가는 상한 (R062)
LEAD = re.compile(r"^\s*(□|ㅇ|○|-|※|＊|\d+\.|\[\d+\])\s")   # 항목 선두 허용 기호 (반각 * 제외 — 각주는 전각 ＊만 합법)
HIGHLIGHT_TOKEN = re.compile(r"==")  # `==특히 강조==` 하이라이트 마커(R040) — 짝수 개만 합법
TABLE = re.compile(r"^\s*\|")
BOLD = re.compile(r"\*\*[^*\n]+\*\*")
INLINE_BAD = re.compile(r"(?:\s-\s|(?<!\*)\*(?!\*)|`|^#{1,6}\s|\s>\s)")
NON_BOLD = re.compile(r"(?<!\*)\*(?!\*)[^*\n]+(?<!\*)\*(?!\*)|~~[^~\n]+~~")
TRIPLE_STAR = re.compile(r"\*{3,}")
# 실제 HTML 태그명 화이트리스트만 검출 — <AI 활용 방안> 같은 꺾쇠 라벨은 코퍼스 관례상 통과
HTML = re.compile(
    r"(?i)</?(br|div|span|table|thead|tbody|tr|td|th|img|em|strong|"
    r"hr|ul|ol|li|sub|sup|font|center|h[1-6])\b[^>]*>"
)
# R056: 표 캡션에 "표N." 일련번호를 붙이지 않는다 — 캡션은 표가 무엇을 보여주는지 서술한다.
CAPTION_NUM = re.compile(r"^\s*[\[<]\s*표\s*\d+\s*[.．]")
# R053: 본문에서 붙임으로 설명을 미루는 인라인 유보 표기. 맺음의 "※ 세부내용은 붙임 참조"는
# 코퍼스 합법 관례이므로 대상이 아니다 — "(상세 …붙임N…)" 형태의 괄호 유보만 잡는다.
ANNEX_DEFER = re.compile(r"[(（]\s*상세[^)）]*붙\s*임")
# R051: ㅇ 괄호 리드가 2음절 추상어인 경우. (품 질)·(배 포)처럼 벌려쓴 형태와 (품질) 형태 모두.
LEAD_SHORT = re.compile(r"^[ㅇ○]\s*\*{0,2}[(（]\s*([가-힣])\s*([가-힣])\s*[)）]")
FOOTNOTE_MAX = 4   # R052: 용어 각주(＊ 선두 문단) 문서당 상한 — 초과분은 용어 자체를 업무언어로 교체

# R046: 본문 날짜는 'yy.m월 월 단위. 4자리 연도 풀 표기를 금지한다.
# 예외 ①은 발신 줄(SENDING이 걸러냄), 예외 ②는 `'26.6.23(화)` 2자리 축약형이므로
# **4자리 연도만** 잡는다 — 축약형까지 잡으면 회의 개최일 같은 합법 표기가 오탐된다.
DATE_FULL = re.compile(r"\d{4}\.\s?\d{1,2}\.\s?\d{1,2}\.?")
SENDING = re.compile(r"^<\s*'?\d")          # < '26. 7. 30.(목), 본부 팀 >
# R044: 항목명을 가운뎃점으로 늘어놓고 "N단 구조" 류로 부르는 라벨 나열.
# 가운뎃점 나열과 라벨이 **같은 줄에** 있을 때만 잡는다 — 기술스택 사양 나열(Node.js 24.x ·
# Next.js 16.2)이나 조사 생략 병렬 압축(근거 소실·실적 누락)의 오탐을 피하기 위한 조건이다.
LABEL_COUNT = re.compile(r"\d+\s*(?:단\s*구조|중\s*차단|종\s*구현|단계로)")
MIDDOT_LIST = re.compile(r"[가-힣A-Za-z0-9]+(?:·[가-힣A-Za-z0-9]+){2,}")
# R029: ㅇ가 (괄호) 리드로 시작하면 그 블록의 하위 대시는 (괄호) 리드를 쓰지 않는다.
PAREN_LEAD_YO = re.compile(r"^[ㅇ○]\s*\*{0,2}\s*[(（]")
PAREN_LEAD_DASH = re.compile(r"^-\s*\*{0,2}\s*[(（]")
# R059: 향후 계획 절에서 주어를 드러내지 않는다 — 조직 주어 + 주격조사.
PLAN_SECTION = re.compile(r"^□.*향후\s*계획")
# 붙임·참고 배너 표도 절 경계다 — □가 다시 나오지 않는 붙임 구간으로 절 상태가 새면 안 된다
ANNEX_BANNER = re.compile(r"^\|\s*(붙\s*임|붙임\s*\d+|참고\s*\d*)\s*\|")
# 접미사는 오탐이 적은 것만 쓴다 — '과·실·처·원' 단독은 일반명사에 걸린다
# (`처리결과는`의 '과는', `확인사실이`의 '실이'). 재현율을 조금 잃더라도 오탐을 없앤다.
ORG_SUBJECT = re.compile(r"[가-힣]{2,}(?:본부|팀|센터|연구원|진흥원|위원회)(?:이|가|은|는)\s")
# R057: 한 절(□ 블록)에서 같은 연결어 3회 초과 금지. 시드에 열거된 후보만 센다 —
# 임의 어미까지 세면 오탐이 쏟아진다.
CONNECTIVES = ("하고", "하며", "하여", "해서", "도록", "하고자", "위해", "되어",
               "따라", "통해", "면서", "없이", "만큼", "시켜")
CONNECTIVE_MAX = 3


def lint_text(text):
    out, bullet_run = [], 0
    footnote_run = 0    # 문서 전체 ＊ 각주 문단 수 (R052)
    depth_base = None  # 현재 ㅇ/○/□ 블록에서 첫 대시의 들여쓰기(최상위 기준선)
    yo_paren_lead = False      # 현재 ㅇ 블록이 (괄호) 리드로 시작했는가 (R029)
    in_plan_section = False    # 현재 □ 블록이 '향후 계획'인가 (R059)
    conj = {}                  # 현재 □ 절의 연결어 카운트 (R057)
    conj_flagged = set()       # 절당 연결어별 1회만 보고

    def close_section():
        conj.clear()
        conj_flagged.clear()

    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        stripped_ = line.strip()
        _bad = sorted({c for c in line if c in LOOKALIKE})
        if _bad:
            out.append({"line": i, "rule": "lookalike-symbol",
                        "text": stripped_[:80],
                        "found": [f"U+{ord(c):04X}\u2192{LOOKALIKE[c]}" for c in _bad]})
        # --- 절·블록 상태 갱신 -------------------------------------------
        if stripped_.startswith("□") or ANNEX_BANNER.match(stripped_):
            close_section()
            in_plan_section = bool(PLAN_SECTION.match(stripped_))
            yo_paren_lead = False
        elif stripped_[:1] in ("ㅇ", "○"):
            yo_paren_lead = bool(PAREN_LEAD_YO.match(stripped_))
        # --- R046 날짜 풀 표기 (발신 줄 제외) ------------------------------
        if not SENDING.match(stripped_) and DATE_FULL.search(stripped_):
            out.append({"line": i, "rule": "date-full-form", "text": stripped_[:80]})
        # --- R044 라벨 나열 -------------------------------------------------
        if LABEL_COUNT.search(stripped_) and MIDDOT_LIST.search(stripped_):
            out.append({"line": i, "rule": "label-enumeration", "text": stripped_[:80]})
        # --- R029 리드 중복 계층 --------------------------------------------
        if yo_paren_lead and PAREN_LEAD_DASH.match(stripped_):
            out.append({"line": i, "rule": "nested-paren-lead", "text": stripped_[:80]})
        # --- R059 향후 계획 주어 --------------------------------------------
        if in_plan_section and stripped_[:1] in ("ㅇ", "○", "-"):
            if ORG_SUBJECT.search(stripped_):
                out.append({"line": i, "rule": "plan-subject", "text": stripped_[:80]})
        # --- R057 연결어 반복 (절 단위) --------------------------------------
        if stripped_[:1] in ("□", "ㅇ", "○", "-"):
            for c in CONNECTIVES:
                n = stripped_.count(c)
                if not n:
                    continue
                conj[c] = conj.get(c, 0) + n
                if conj[c] > CONNECTIVE_MAX and c not in conj_flagged:
                    conj_flagged.add(c)
                    out.append({"line": i, "rule": "connective-repeat",
                                "text": f"'{c}' {conj[c]}회 — {stripped_[:60]}"})
        # 캡션·붙임유보·괄호리드·각주 상한 (개선본 대조로 확정된 실무 관례)
        if CAPTION_NUM.match(line):
            out.append({"line": i, "rule": "caption-numbered", "text": line.strip()[:80]})
        if ANNEX_DEFER.search(line):
            out.append({"line": i, "rule": "annex-crossref", "text": line.strip()[:80]})
        if LEAD_SHORT.match(line.strip()):
            out.append({"line": i, "rule": "lead-too-short", "text": line.strip()[:80]})
        _b = line.strip()
        if _b[:1] in ("□", "ㅇ", "○", "-") and len(_b) > 2:
            _plain = _b.replace("**", "").replace("==", "")
            if FORMULA.search(_plain):
                out.append({"line": i, "rule": "formula-inline", "text": _b[:80]})
            if len(_plain) > MAX_BODY_CHARS:
                out.append({"line": i, "rule": "body-line-overflow", "text": _b[:80]})
            # 수치 변화(→)는 항목명 뒤 괄호 안에 넣는다 (R065) — 괄호 밖 화살표를 검출
            _depth, _bare = 0, False
            for _c in _plain:
                if _c == "(":
                    _depth += 1
                elif _c == ")":
                    _depth = max(0, _depth - 1)
                elif _c == ARROW and _depth == 0:
                    _bare = True
            if _bare:
                out.append({"line": i, "rule": "metric-unparenthesized", "text": _b[:80]})
        if line.strip().startswith("＊"):
            footnote_run += 1
            if footnote_run == FOOTNOTE_MAX + 1:
                out.append({"line": i, "rule": "footnote-overflow", "text": line.strip()[:80]})
        # `==` 하이라이트 마커(R040)는 한 줄 안에서 짝이 맞아야 한다 — 홀수면 잔존 위험
        if len(HIGHLIGHT_TOKEN.findall(line)) % 2 == 1:
            out.append({"line": i, "rule": "highlight-unpaired", "text": line.strip()[:80]})
        if TABLE.match(line):
            cols = len([c for c in line.strip().strip("|").split("|")])
            if cols > 6 and not set(line.strip()) <= set("|- :"):
                out.append({"line": i, "rule": "table-too-wide", "text": line.strip()[:80]})
            continue
        if HTML.search(line):
            out.append({"line": i, "rule": "html-tag", "text": line.strip()[:80]})
        stripped = line.strip()
        # 문장 중간(항목 선두가 아닌 위치)의 □ 검출.
        # ※는 인라인 후행 참조가 코퍼스 합법 관례이므로 제외, ㅇ은 오탐 위험으로 이번 범위 제외.
        # 선두 □가 합법인 줄에서도 같은 줄의 두 번째 □는 검출.
        if stripped.count("□") > (1 if stripped.startswith("□") else 0):
            out.append({"line": i, "rule": "misplaced-marker", "text": stripped[:80]})
        if stripped.startswith("ㅇ") or stripped.startswith("○") or stripped.startswith("□"):
            bullet_run = 0
            depth_base = None
        elif stripped.startswith("-"):
            leading_spaces = len(line) - len(line.lstrip())
            if depth_base is None:
                depth_base = leading_spaces
            if leading_spaces > depth_base:
                # 대시는 중첩 불가 — 기준선보다 더 들여쓴 대시는 깊이 초과 (4단은 ※/＊)
                out.append({"line": i, "rule": "depth-exceeded", "text": stripped[:80]})
            else:
                if leading_spaces < depth_base:
                    depth_base = leading_spaces
                bullet_run += 1
                # R045: 상위 계층 하나에 딸리는 하위 계층은 최대 2개 — 3개째부터 위반.
                # 초과분은 개수를 쳐내지 말고 성격이 가까운 항목끼리 통합 서술로 합친다.
                if bullet_run == 3:
                    out.append({"line": i, "rule": "bullet-overflow", "text": stripped[:80]})
        if TRIPLE_STAR.search(line):
            out.append({"line": i, "rule": "non-bold-markup", "text": stripped[:80]})
        body = LEAD.sub("", line, count=1)
        body_nobold = BOLD.sub("", body)
        if NON_BOLD.search(body_nobold):
            out.append({"line": i, "rule": "non-bold-markup", "text": stripped[:80]})
        if INLINE_BAD.search(body_nobold):
            out.append({"line": i, "rule": "inline-markdown", "text": stripped[:80]})
    return out

if __name__ == "__main__":
    # exit 계약: 0 통과 / 1 린트 위반 / 2 인자·파일 오류 — 크래시가 1로 새면
    # 호출자가 '위반 있음'으로 오독한다
    if len(sys.argv) != 2:
        print("usage: lint_md_profile.py <draft.md>", file=sys.stderr)
        sys.exit(2)
    try:
        text = open(sys.argv[1], encoding="utf-8").read()
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    v = lint_text(text)
    print(json.dumps({"violations": v}, ensure_ascii=False, indent=1))
    sys.exit(1 if v else 0)
