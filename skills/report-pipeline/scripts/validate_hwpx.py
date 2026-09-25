"""hwpx 구조 검증 + md↔되읽기 왕복 대조 (spec §6-4, AI 티 3중장치-③). stdlib-only."""
import sys, json, re, zipfile, pathlib, xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lint_md_profile import quote_blocks, mask_fences   # noqa: E402  (인용 블록 경계 단독 출처)

NUM = re.compile(r"\d+(?:[.,]\d+)*")
# 개조식 항목 선두 합법 기호 (lint_md_profile.LEAD와 동일 어휘) — 잔재 검사 전에 벗겨낸다.
LEAD = re.compile(r"^\s*(□|ㅇ|○|-|※|＊|\d+\.|\[\d+\])\s")
HEADING = re.compile(r"^#{1,6}\s")
HR = re.compile(r"^-{3,}$")
STRIKE = re.compile(r"~~[^~\n]+~~")
ITALIC = re.compile(r"(?<!\*)\*(?!\*)[^*\n]+(?<!\*)\*(?!\*)")
INLINE_DASH = re.compile(r"\s-\s")

MIMETYPE_HWPX = b"application/hwp+zip"
# 반입 판별 필수 멤버 — version.xml이 hwpx 확정 마커(부재 시 일반 OCF/EPUB류와 지문 동일)
PACKAGE_REQUIRED = ("version.xml", "META-INF/container.xml",
                    "Contents/content.hpf", "Contents/header.xml")

def structural_check(path):
    errs = []
    try:
        raw = pathlib.Path(path).read_bytes()
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad:
                errs.append(f"zip corrupt: {bad}")
            for n in z.namelist():
                if n.endswith(".xml"):
                    try:
                        ET.fromstring(z.read(n))
                    except ET.ParseError as e:
                        errs.append(f"{n}: {e}")
            # --- 반입 판별(OCF 시그니처 + 패키지 완결성, R043) ---
            infos = z.infolist()
            names = [i.filename for i in infos]
            first = infos[0] if infos else None
            if first is None or first.filename != "mimetype":
                errs.append("ocf: first entry must be 'mimetype'")
            else:
                if first.compress_type != zipfile.ZIP_STORED:
                    errs.append("ocf: mimetype must be STORED (uncompressed)")
                if first.header_offset != 0:
                    errs.append("ocf: mimetype local header must be at offset 0")
                if first.extra:
                    errs.append("ocf: mimetype must not carry an extra field")
                if z.read("mimetype") != MIMETYPE_HWPX:
                    errs.append(f"ocf: mimetype content must be {MIMETYPE_HWPX.decode()}")
                elif not errs and raw[38:38 + len(MIMETYPE_HWPX)] != MIMETYPE_HWPX:
                    errs.append("ocf: signature string not at byte offset 38")
            for req in PACKAGE_REQUIRED:
                if req not in names:
                    errs.append(f"package: missing required member {req}")
            if not any(re.match(r"Contents/section\d+\.xml$", n) for n in names):
                errs.append("package: no Contents/sectionN.xml")
            dirs = [n for n in names if n.endswith("/")]
            if dirs:
                errs.append(f"package: directory entries present: {dirs}")
    except (zipfile.BadZipFile, FileNotFoundError) as e:
        errs.append(str(e))
    return errs

# 그림 — 초안의 `도해:` 마커는 변환에서 그림으로 바뀐다(R088). 글자 대조에서는 빼고 개수로 대조한다.
# 되읽기 첫 줄의 머리말 배너 그림(kcaHdr*)은 양식 자산이라 세지 않는다.
FIG_MARKER = re.compile(r"^\s*도[해식]:\s*\S")
FIG_IMAGE = re.compile(r"!\[[^\]]*\]\((?!kcaHdr)[^)]*\)")


HDR_IMAGE = re.compile(r"!\[[^\]]*\]\(kcaHdr[^)]*\)")


def _figure_count(lines):
    """본문 그림 수 — `끝.` 뒤는 세지 않는다. 되읽기는 머리말 배너 BinData를 문서 끝에 한 번 더
    내보낸다(인도본 r02 실측 — `끝.` 뒤 image_001.png·image_002.bmp). `끝.`이 없는 문서(붙임 없는 결과 보고 등)는
    문서 끝의 그림 줄을 머리말 그림 수(`kcaHdr…`)만큼 뺀다 — 종전에는 머리말 두 장을 본문 그림으로 세어
    count-mismatch:figures(0→2)가 났다('26.9.25 하네스 실전 점검)."""
    ends = [i for i, l in enumerate(lines) if l.strip() == "끝."]
    if ends:
        body = lines[:ends[-1]]
    else:
        body, dump = list(lines), sum(len(HDR_IMAGE.findall(l)) for l in lines)
        while body and dump and (not body[-1].strip() or FIG_IMAGE.fullmatch(body[-1].strip())):
            dump -= bool(body[-1].strip())
            body.pop()
    return sum(bool(FIG_MARKER.match(l)) for l in body) + sum(len(FIG_IMAGE.findall(l)) for l in body)


# 병합 표 — 되읽기(kordoc)는 병합이 있는 표를 GFM 대신 HTML <table>(rowspan·colspan)로 돌려준다.
# 초안 쪽 병합 표기(머리글 `A > B`, 칸 `〃`)와 맞춰 세지 않으면 표·칸 글자가 통째로 누락으로 잡힌다.
HTML_TABLE = re.compile(r"<table>(.*?)</table>", re.S)
HTML_ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
HTML_CELL = re.compile(r"<t[hd]([^>]*)>(.*?)</t[hd]>", re.S)
COLSPAN = re.compile(r'colspan="(\d+)"')
MERGE_SPLIT = " > "
DITTO = "〃"


def _html_tables(text):
    """HTML 표마다 (최대 열 수, 칸 글자 목록)."""
    out = []
    for m in HTML_TABLE.finditer(text):
        widths, cells = [], []
        for row in HTML_ROW.findall(m.group(1)):
            w = 0
            for attrs, body in HTML_CELL.findall(row):
                cs = COLSPAN.search(attrs)
                w += int(cs.group(1)) if cs else 1
                cells.append(re.sub(r"<[^>]+>", "", body).strip())
            widths.append(w)
        out.append((max(widths, default=0), cells))
    return out


def _strip_preamble(lines):
    """되읽기 머리 블록 — MCP 되읽기의 `📑 문서 구조:` 목록(`- {제목}` 줄)은 본문이 아니다.
    대시로 세면 `count-mismatch:subs`가 매번 1 늘어난다('26.9.3 실측)."""
    out, skip = [], False
    for l in lines:
        s = l.strip()
        if s.startswith("📑"):
            skip = True
            continue
        if skip and (not s or s.startswith("-")):
            if not s:
                skip = False
            continue
        skip = False
        out.append(l)
    return out


def _table_groups(lines):
    """연속된 `|` 줄 묶음마다 (열 수, 구분선 뺀 행 수)."""
    groups, cur = [], []
    for l in lines + [""]:
        if l.strip().startswith("|"):
            cur.append(l.strip())
        elif cur:
            rows = [r for r in cur if not set(r) <= set("|- :")]
            groups.append((max(len(r.strip("|").split("|")) for r in cur), len(rows)))
            cur = []
    return groups


def _is_box(cols, rows):
    """1칸 상자(산식 박스 등) — 되읽기가 표 대신 문단으로 돌려주는 경우가 있어 표로 세지 않는다('26.9.24 r02 실측).
    글자는 문장 대조(content-dropped)가 따로 본다."""
    return cols == 1 and 0 < rows <= 1


def _is_blank(rows):
    """글자가 한 칸도 없는 표(서명란·그림만 든 표) — 표 수와 따로 센다. 웹앱 되읽기는 머리말 배너를 그림이 빠진
    빈 2칸 표로 돌려줘 표 수가 매번 1 늘었다('26.9.25). 되읽기 쪽에 느는 빈 표는 잡음이지만 원본의 빈 표가 빠진 것은
    손실이라, compare는 빈 표가 줄어든 경우만 본다('26.9.25 코드 리뷰 — 한데 빼면 빈 서명란 누락을 못 잡는다)."""
    return rows == 0


def profile_counts(text):
    html = _html_tables(text)
    numbers_src = re.sub(r"<[^>]+>", " ", text)          # 표 안 숫자도 센다 — 태그만 지운다
    text = HTML_TABLE.sub("", text)
    lines = _strip_preamble(text.splitlines())
    groups = [(c, r) for c, r in _table_groups(lines) if not _is_box(c, r)]
    html = [(w, len([c for c in cells if c])) for w, cells in html]
    html = [(w, r) for w, r in html if not _is_box(w, r)]
    blank = sum(_is_blank(r) for _, r in groups + html)
    groups = [(c, r) for c, r in groups if not _is_blank(r)]
    html = [(w, r) for w, r in html if not _is_blank(r)]
    tables = len(groups)
    return {
        "sections": sum(l.strip().startswith("□") for l in lines),
        "points": sum(l.strip()[:1] in ("ㅇ", "○") for l in lines),
        "subs": sum(l.strip().startswith("-") and not set(l.strip()) <= set("|- :") for l in lines if not l.strip().startswith("|")),
        "footnotes": sum(l.strip().startswith("＊") for l in lines),
        "tables": tables + len(html),
        "blank_tables": blank,
        "figures": _figure_count(lines),
        "max_cols": max([c for c, _ in groups] + [w for w, _ in html], default=0),
        "numbers": set(NUM.findall(numbers_src)),
    }

def normalize_num(s):
    """콤마 제거 + 소수 끝자리 0 제거. float 변환 불가하면 원문 그대로(비교 실패로 손실 검출)."""
    t = s.replace(",", "")
    try:
        float(t)
    except ValueError:
        return s
    if "." in t:
        t = t.rstrip("0")
        if t.endswith("."):
            t = t[:-1]
    return t

PAIRED_BOLD = re.compile(r"\*\*[^*\n]+?\*\*")


def has_markdown_leftover(line, title=None, src_pieces=frozenset()):
    """되읽기 줄에 마크다운 기호가 문자로 남았는가.

    되읽기(kordoc)가 원래 그렇게 돌려주는 것은 잔재가 아니다('26.7~9월 같은 오탐 5회 — 매번 hwpx XML을 열어
    무해 판정했다): ① 짝이 맞는 `**…**` — 글자 모양(charPr) 볼드를 마크다운으로 되쓴 것, ② 첫 줄 `# 제목` —
    제목을 h1로 넘겨(R010) 제목 박스가 헤딩으로 돌아온 것(원문 제목과 같을 때만), ③ 원문에도 있는 ` - `
    (산식 뺄셈 등). 실제 hwpx 안에 기호가 남았는지는 `compare --hwpx`의 `literal-markup`이 XML에서 직접 센다."""
    stripped = line.strip()
    if not stripped:
        return False
    if HR.match(stripped):
        return True
    if HEADING.match(stripped):
        return not (title and stripped.startswith("# ") and _piece(stripped) == title)
    body = LEAD.sub("", line, count=1)  # 항목 선두 합법 기호(-, ㅇ 등)는 잔재 판정에서 제외
    plain = PAIRED_BOLD.sub(lambda m: m.group(0)[2:-2], body)
    if "`" in body:
        return True
    if "**" in plain:                   # 짝 없는 `**`만 — 짝 맞는 것은 볼드 재직렬화
        return True
    if STRIKE.search(body):
        return True
    if ITALIC.search(plain):
        return True
    if INLINE_DASH.search(body) and _piece(stripped) not in src_pieces:
        return True
    if "==" in body:  # 하이라이트 마커(R040) 잔존 — postprocess 치환 실패 검출
        return True
    return False

# 되읽기가 붙이는 마크다운 이스케이프(`~` → `\~` 등)와 생성기 머리말. 문장 대조 전에
# 걷어내지 않으면 멀쩡한 문장이 통째로 '소실'로 잡힌다('26.9.10 실측 — 4건에서 47조각).
UNESCAPE = re.compile(r"\\([~*_`#\[\]])")
RT_PREAMBLE = re.compile(r"^(?:\[포맷:|📑|!\[)")
SENT_LEAD = re.compile(r"^\s*(?:[□ㅇ○▪·ㆍ＊※☞]|-|\*|\d+[.)])\s*")
RIGHT_TAG = re.compile(r"</?right>")


QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
HEAD_MARK = re.compile(r"^#{1,6}\s+")


def _norm(x):
    """대조 정규화 — 공백, 굽은 따옴표(되읽기가 곧은 따옴표를 ’로 바꾼다 — '26.9.24 가짜 손실 15건), 수치 표기
    (1,234 ≡ 1234 · 23.70 ≡ 23.7 — numbers 대조와 같은 규칙이어야 한쪽만 오탐을 내지 않는다)."""
    x = re.sub(r"\s+", " ", x.translate(QUOTES)).strip()
    return NUM.sub(lambda m: normalize_num(m.group()), x)


def _piece(line):
    """표가 아닌 한 줄의 알맹이 — 헤딩·계층 기호·강조·정렬 래퍼·이스케이프를 벗긴다."""
    s = UNESCAPE.sub(r"\1", RIGHT_TAG.sub("", line.strip()))
    s = HEAD_MARK.sub("", s.replace("**", "").replace("`", "").replace("==", ""))
    return _norm(SENT_LEAD.sub("", s))


def content_pieces(text):
    """문장 단위 대조용 조각 — 계층 기호·강조·정렬 래퍼·이스케이프를 벗긴 알맹이.

    개조식 변환은 마크다운 `- `를 `ㅇ `·`□ `로 바꾸므로 선두 기호는 대조 대상이 아니다.
    표는 셀 단위로 펴서 행 구성이 달라져도 내용 손실만 잡는다.
    """
    pieces = [_norm(c) for _, cells in _html_tables(text) for c in cells if c]
    text = HTML_TABLE.sub("", text)
    for line in _strip_preamble(text.splitlines()):
        s = line.strip()
        if not s or set(s) <= set("|- :") or RT_PREAMBLE.match(s) or FIG_MARKER.match(s):
            continue
        if s.startswith("|"):
            s = UNESCAPE.sub(r"\1", RIGHT_TAG.sub("", s)).replace("**", "").replace("`", "").replace("==", "")
            for cell in (c.strip() for c in s.strip("|").split("|")):
                cell = re.sub(r"\s+", " ", cell)
                if not cell or set(cell) <= set("- :") or cell == DITTO:
                    continue                          # `〃`는 위 칸과 병합돼 사라지는 표기
                pieces.extend(_norm(x) for x in cell.split(MERGE_SPLIT))   # `A > B` → 2단 머리행 두 칸
            continue
        s = _piece(s)
        if s:
            pieces.append(s)
    return pieces


def _quote_norm(line):
    t = UNESCAPE.sub(r"\1", line).replace("\u2060", "").strip()
    t = t.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'}))
    return re.sub(r"\s+", " ", t)


def split_quotes(src, rt):
    """원문 인용 블록 — 초안에서는 울타리째 가리고, 되읽기본에서는 그 줄들을 뺀다(개수·문장 대조가 인용 줄의
    `- `·`[ ]`를 대시·캡션으로 세지 않게). 인용 줄 자체는 되읽기본에 그대로 있는지 따로 본다."""
    lines = src.split("\n")
    quote = [_quote_norm(lines[k]) for start, end, _, _ in quote_blocks(src) if end
             for k in range(start, end - 1) if lines[k].strip()]
    qset = set(quote)
    rt_kept = "\n".join(l for l in rt.split("\n") if _quote_norm(l) not in qset or not l.strip())
    rt_all = {_quote_norm(l) for l in rt.split("\n")}
    return mask_fences(src), rt_kept, [q for q in quote if q not in rt_all]


def compare_texts(src, rt):
    src, rt, quote_lost = split_quotes(src, rt)
    a, b = profile_counts(src), profile_counts(rt)
    issues = []
    keys = ["sections", "points", "subs", "footnotes", "tables", "figures", "max_cols"]
    if b["figures"] < a["figures"]:
        # 도식이 표로 바뀌었다(R089 diagram_table) — 그림 수·표 수를 따로 세면 둘 다 어긋나므로 합으로 대조하고,
        # 도식 표는 좌표 격자라 열이 많으니 최대 열 수는 줄어든 경우만 본다
        keys = [k for k in keys if k not in ("tables", "figures", "max_cols")]
        if a["tables"] + a["figures"] != b["tables"] + b["figures"]:
            issues.append({"rule": "count-mismatch:tables+figures", "src": a["tables"] + a["figures"],
                           "roundtrip": b["tables"] + b["figures"]})
        if b["max_cols"] < a["max_cols"]:
            issues.append({"rule": "count-mismatch:max_cols", "src": a["max_cols"], "roundtrip": b["max_cols"]})
    for k in keys:
        if a[k] != b[k]:
            issues.append({"rule": f"count-mismatch:{k}", "src": a[k], "roundtrip": b[k]})
    if b["blank_tables"] < a["blank_tables"]:
        issues.append({"rule": "count-mismatch:blank_tables", "src": a["blank_tables"], "roundtrip": b["blank_tables"]})
    a_num = {normalize_num(n) for n in a["numbers"]}
    b_num = {normalize_num(n) for n in b["numbers"]}
    lost = a_num - b_num
    if lost:
        issues.append({"rule": "numbers-lost", "values": sorted(lost)[:20]})
    src_pieces = content_pieces(src)
    src_set = frozenset(src_pieces)
    first = next((l for l in src.splitlines() if l.strip()), "")
    title = _piece(first) if not first.strip().startswith("|") else None
    for i, line in enumerate(rt.splitlines(), 1):
        if not line.strip().startswith("|") and has_markdown_leftover(line, title, src_set):
            issues.append({"rule": "markdown-leftover", "line": i, "text": line.strip()[:80]})
    # 문장 자체가 바뀐 경우 — 개수·수치가 맞으면 통과하던 구멍을 막는다('26.9.10 신설).
    # 개수 대조는 "몇 개인가"만 보므로 문장이 통째로 갈려도 총량이 같으면 지나갔다.
    have = set(content_pieces(rt))
    dropped = [x for x in src_pieces if x not in have] + quote_lost
    if dropped:
        issues.append({"rule": "content-dropped", "count": len(dropped),
                       "values": [x[:120] for x in dropped[:10]]})
    return issues

def _is_signal_number(normed):
    """연도 표기('25 등) 같은 1~2자리 정수는 노이즈로 제외 — 소수 또는 3자리 이상 정수만 신호로 본다."""
    if "." in normed:
        return True
    return len(normed) >= 3

def _extract_number_set(text):
    # 날짜 패턴 제거: 아포스트로피 날짜('26.7월, '26. 1. 13) 및 월(月)이 붙은 날짜
    masked = re.sub(r"['']\d{2}\.\s?\d{1,2}(?:\.\s?\d{1,2})?\.?(?:月|월|日|일)?", "", text)
    masked = re.sub(r"\d{1,2}\.\d{1,2}(?=月|월)", "", masked)
    normed = (normalize_num(n) for n in NUM.findall(masked))
    return {n for n in normed if _is_signal_number(n)}

def numbers_check(draft_text, research_dir):
    """경량 팩트체크: 초안 수치가 research_dir 어딘가(.md/.txt/.json/.jsonl)에 근거를 갖는지
    정규화 대조로 결정론 판정한다(spec 경량 팩트체크). 근거 없는 수치만 반환."""
    draft_nums = _extract_number_set(draft_text)
    research_nums = set()
    rdir = pathlib.Path(research_dir)
    if rdir.is_dir():
        for ext in ("*.md", "*.txt", "*.json", "*.jsonl"):
            for f in rdir.rglob(ext):
                try:
                    research_nums |= _extract_number_set(f.read_text(encoding="utf-8"))
                except OSError:
                    continue
    unsourced = draft_nums - research_nums
    if not unsourced:
        return []
    return [{"rule": "numbers-unsourced", "values": sorted(unsourced)}]

FIGURE_LAYOUT_KEYS = {"span", "width_mm", "task_ratio", "highlight", "type", "render", "tone", "status", "src",
                      "source", "kind", "numbered", "emphasis"}


def figure_numbers_text(fig_dir):
    """도식 명세(figures/*.json)의 글자·차트 값 — 경량 팩트체크가 도식 안 수치도 근거와 대조하게 한다(R092).
    배치용 값(span·width_mm 등)은 수치 인용이 아니므로 뺀다."""
    out = []

    def walk(obj, key=None):
        if key in FIGURE_LAYOUT_KEYS:
            return
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, k)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, key)
        elif isinstance(obj, str) or (key == "values" and isinstance(obj, (int, float))):
            out.append(str(obj))
    d = pathlib.Path(fig_dir)
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            walk(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return "\n".join(out)


def freshness_check(draft_text, prepared_text):
    """저장된 40_prepared가 **현재** 20_draft에서 나온 것인가 (R004 계열 — '26.9.10 신설).

    작업폴더가 인터페이스인데 산출물끼리 어느 초안에서 나왔는지를 기록하지 않는다.
    초안을 고치고 재변환을 안 하면 인도본이 조용히 낡고, 사용자는 "초안대로 안 담겼다"로
    본다. 실측('26.9.10): 인도 건 4개 중 3개에서 20_draft가 40_prepared보다 최신이었고
    (최대 12일) 본문 수치까지 달랐다 — 초안 `KCA·CRMS 16건` vs 인도본 `17건`.

    새 산출물을 만들지 않고 **현재 초안을 다시 정규화해** 저장본과 대조한다.
    """
    try:
        from prep_report_md import prep, content_fingerprint
    except ImportError as e:      # 같은 scripts/ 폴더 전제 — 웹앱 사본도 동일 구성
        return [{"rule": "freshness-unavailable", "detail": str(e)}]
    expected = prep(draft_text)
    if content_fingerprint(expected) == content_fingerprint(prepared_text):
        return []
    have = set(content_pieces(prepared_text))
    drifted = [x for x in content_pieces(expected) if x not in have]
    return [{"rule": "prepared-stale", "drifted": len(drifted),
             "detail": "20_draft가 40_prepared 이후 바뀌었다 — 변환을 다시 돌려야 인도본이 초안과 맞는다",
             "values": [x[:120] for x in drifted[:10]]}]


LITERAL_MARKS = ("**", "==", "`", "~~")


def quote_texts(src):
    """초안의 원문 인용 블록(```text) 줄 — 원문 그대로라 기호(백틱 등)가 들어 있어도 잔재가 아니다."""
    lines = src.split("\n")
    return [_quote_norm(lines[k]) for start, end, _, _ in quote_blocks(src) if end
            for k in range(start, end - 1) if lines[k].strip()]


def _core(text):
    """기호를 뺀 글자 — 기호뿐인 조각(`**`)은 어느 인용 줄과도 겹쳐 보이므로 면제 판단에 쓰지 않는다."""
    for mark in LITERAL_MARKS:
        text = text.replace(mark, "")
    return text.strip()


def _outside_quotes(norm, allowed):
    """글자 조각에서 원문 인용 부분을 뺀 나머지. 조각이 인용 줄의 일부이면(글자가 있을 때만) 빈 문자열, 인용 줄을
    품은 조각이면 그 줄만 지운다 — 기호뿐인 잔재 조각이나 인용 줄 + 본문이 한 <hp:t>에 든 경우도 잔재를 본다
    ('26.9.25 코드 리뷰: 한 방향 포함 검사는 `**` 조각을 면제하고 인용 줄 + 본문 조각은 통째로 잡았다)."""
    if _core(norm) and any(norm in a for a in allowed):
        return ""
    for a in allowed:
        if a in norm:
            norm = norm.replace(a, " ")
    return norm


def literal_markup(hwpx_path, allowed=()):
    """hwpx 본문 글자(<hp:t>)에 마크다운 기호가 문자 그대로 남았는가 — 되읽기의 볼드 재직렬화와 달리 이것은
    진짜 잔재다(postprocess 치환 실패 등). 되읽기만으로는 둘을 가를 수 없어 XML에서 직접 센다.
    allowed(원문 인용 블록 줄)에 든 글자는 원문 그대로라 빼다('26.9.25 실변환: 지시문 원문의 백틱 2건)."""
    allowed = sorted({a for a in allowed if _core(a)}, key=len, reverse=True)
    found = {}
    with zipfile.ZipFile(hwpx_path) as z:
        for name in sorted(n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n)):
            root = ET.fromstring(z.read(name))
            for t in root.iter("{http://www.hancom.co.kr/hwpml/2011/paragraph}t"):
                text = "".join(t.itertext())
                rest = _outside_quotes(_quote_norm(text), allowed)
                for mark in LITERAL_MARKS:
                    if mark in rest:
                        found.setdefault(mark, []).append(text.strip()[:60])
    return [{"rule": "literal-markup", "mark": m, "count": len(v), "values": v[:5]} for m, v in found.items()]


USAGE = ("usage: validate_hwpx.py structural <path.hwpx> | "
         "validate_hwpx.py compare <src.md> <rt.md> [--hwpx <path.hwpx>] | "
         "validate_hwpx.py numbers <draft.md> <research_dir> | "
         "validate_hwpx.py freshness <draft.md> <prepared.md>")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        if mode == "structural":
            if len(sys.argv) < 3:
                raise IndexError
            errs = structural_check(sys.argv[2])
            print(json.dumps({"errors": errs}, ensure_ascii=False))
            sys.exit(1 if errs else 0)
        elif mode == "compare":
            if len(sys.argv) < 4:
                raise IndexError
            src = open(sys.argv[2], encoding="utf-8").read()
            rt = open(sys.argv[3], encoding="utf-8").read()
            issues = compare_texts(src, rt)
            if "--hwpx" in sys.argv[4:]:
                issues += literal_markup(sys.argv[sys.argv.index("--hwpx") + 1], quote_texts(src))
            print(json.dumps({"issues": issues}, ensure_ascii=False, indent=1))
            sys.exit(1 if issues else 0)
        elif mode == "freshness":
            if len(sys.argv) < 4:
                raise IndexError
            draft = open(sys.argv[2], encoding="utf-8").read()
            prepared = open(sys.argv[3], encoding="utf-8").read()
            issues = freshness_check(draft, prepared)
            print(json.dumps({"issues": issues}, ensure_ascii=False, indent=1))
            sys.exit(1 if issues else 0)
        elif mode == "numbers":
            if len(sys.argv) < 4:
                raise IndexError
            draft = open(sys.argv[2], encoding="utf-8").read()
            # 도식 명세의 수치도 초안 수치로 본다 — 도식에만 있는 숫자가 근거 없이 인도되지 않게(R092)
            draft += "\n" + figure_numbers_text(pathlib.Path(sys.argv[2]).parent / "figures")
            issues = numbers_check(draft, sys.argv[3])
            print(json.dumps({"issues": issues}, ensure_ascii=False, indent=1))
            sys.exit(1 if issues else 0)
        else:
            print(USAGE, file=sys.stderr)
            sys.exit(2)
    except IndexError:
        print(USAGE, file=sys.stderr)
        sys.exit(2)
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
