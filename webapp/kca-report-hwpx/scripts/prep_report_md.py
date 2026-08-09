"""변환 전 정규화 — 내용 무손실 보장 (spec §6 '작성된 md 그대로'). stdlib-only.

무손실 안전장치는 '해시 자가증명'이 아니라 '모호한 입력 거부'로 구현한다.
해시 비교(fingerprint(prep(x)) == fingerprint(x))는 fingerprint 자신이 prep과
동일한 삭제 규칙으로 정규화되어 있으면 대수적으로 항상 참이 되는 무의미한
자가증명이었다. 대신:
  1. 삭제 대상(단일행 HTML 주석, 문맥상 명백한 구분선)만 스캔 단계에서
     명확히 식별하고, 식별할 수 없는 애매한 패턴(다중행 주석 스팬,
     Setext 제목처럼 보이는 `---`)은 조용히 처리하지 않고 PrepError로
     거부한다 — "모른다"를 명시적으로 실패시킨다.
  2. content_fingerprint()는 공백 정규화 + 각주 마커 표기(＊/*/\\*) 차이만
     무시하는 목적으로 축소한다 (더 이상 주석·구분선을 지우지 않음).
  3. prep_with_accounting()은 삭제된 문자 수를 실제 삭제 목록(제거된 단일행
     주석 길이 + 제거된 구분선 라인 길이 + 각주 이스케이프 정규화로 소실된
     백슬래시 등)과 대조해 불일치 시 PrepError를 낸다. 이는 향후 prep()에
     새 변환 규칙이 추가되었는데 회계가 갱신되지 않은 회귀를 잡기 위한
     트립와이어다.
"""
import sys, re, hashlib, argparse

SINGLELINE_COMMENT = re.compile(r"<!--(?:(?!-->).)*-->")  # 같은 라인 내 주석만
COMMENT_OPEN = re.compile(r"<!--")
COMMENT_CLOSE = re.compile(r"-->")
HR_LINE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")
FOOT = re.compile(r"^(\s*)\\?\*\s(?=\S)")   # 라인 선두 각주 마커 → ＊


class PrepError(Exception):
    def __init__(self, reason, line):
        self.reason = reason
        self.line = line
        super().__init__(f"{reason} at line {line}")


def _strip_singleline_comments(text):
    """같은 라인 안에서 열리고 닫히는 <!-- ... --> 만 제거.
    라인을 넘어가는 주석 스팬(여는 <!--와 닫는 -->가 다른 라인)은
    거부 대상이므로 여기서는 건드리지 않고 검사만 한다."""
    deleted = 0
    out_lines = []
    for line in text.splitlines(True):  # keepends
        stripped_line = SINGLELINE_COMMENT.sub("", line)
        deleted += len(line) - len(stripped_line)
        out_lines.append(stripped_line)
    return "".join(out_lines), deleted


def _check_no_multiline_comment_spans(text):
    """단일행으로 제거되지 않고 남은 <!-- 또는 --> 가 있으면
    다중행 주석 스팬이 존재한다는 뜻 — 거부."""
    for i, line in enumerate(text.splitlines(), 1):
        if COMMENT_OPEN.search(line) or COMMENT_CLOSE.search(line):
            raise PrepError("multiline-comment", i)


def _process_hr_and_footnotes(text):
    """구분선은 문맥(앞뒤 빈 줄 또는 문서 경계)이 확인된 경우에만 제거.
    문맥이 모호하면(Setext 제목 패턴처럼 직전 라인이 비어있지 않으면) 거부."""
    lines = text.splitlines()
    n = len(lines)
    out = []
    deleted = 0
    for i, line in enumerate(lines):
        if HR_LINE.match(line):
            prev_blank = (i == 0) or (lines[i - 1].strip() == "")
            next_blank = (i == n - 1) or (lines[i + 1].strip() == "")
            if not (prev_blank and next_blank):
                raise PrepError("setext-ambiguous", i + 1)
            deleted += len(line) + 1  # 라인 + 개행 1자
            continue
        new_line = FOOT.sub(r"\1＊ ", line)
        deleted += len(line) - len(new_line)  # 각주 이스케이프 `\*`→`＊` 시 백슬래시 소실분
        out.append(new_line)
    return out, deleted


def prep_with_accounting(text):
    """(정규화된 텍스트, 삭제된 문자 수) 를 반환. 모호한 입력은 PrepError."""
    no_comment, comment_deleted = _strip_singleline_comments(text)
    _check_no_multiline_comment_spans(no_comment)
    out_lines, hr_deleted = _process_hr_and_footnotes(no_comment)
    trailing_nl = text.endswith("\n")
    out = "\n".join(out_lines) + ("\n" if trailing_nl else "")
    return out, comment_deleted + hr_deleted


def prep(text):
    out, deleted = prep_with_accounting(text)
    # 회귀 트립와이어: 실제 길이차와 회계가 어긋나면(=새 삭제 규칙이 미회계
    # 상태로 추가됐다면) 무손실 보장이 깨진 것으로 간주해 거부한다.
    if len(text) - len(out) != deleted:
        raise PrepError("deletion-accounting-mismatch", 0)
    return out


def content_fingerprint(text):
    """공백 정규화 + 각주 마커 표기(＊/*/\\*) 차이만 무시하는 해시.
    주석·구분선은 더 이상 지우지 않는다 — prep()의 삭제 로직과 독립적으로
    유지해 자가증명(항상 참)이 되지 않도록 한다."""
    t = re.sub(r"[＊*\\]", "", text)
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha256(t.encode()).hexdigest()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("-o", required=True)
    a = ap.parse_args()
    src = open(a.src, encoding="utf-8").read()
    try:
        out = prep(src)
    except PrepError as e:
        print(f"FATAL: {e.reason} at line {e.line} — 모호한 입력 거부", file=sys.stderr)
        sys.exit(2)
    open(a.o, "w", encoding="utf-8").write(out)
    print(f"OK {a.o}")
