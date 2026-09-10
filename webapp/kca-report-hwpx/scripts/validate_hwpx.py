"""hwpx 구조 검증 + md↔되읽기 왕복 대조 (spec §6-4, AI 티 3중장치-③). stdlib-only."""
import sys, json, re, zipfile, pathlib, xml.etree.ElementTree as ET

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

def profile_counts(text):
    lines = text.splitlines()
    tbl_rows = [l for l in lines if l.strip().startswith("|")]
    tables = 0
    prev = False
    for l in lines:
        cur = l.strip().startswith("|")
        if cur and not prev:
            tables += 1
        prev = cur
    return {
        "sections": sum(l.strip().startswith("□") for l in lines),
        "points": sum(l.strip()[:1] in ("ㅇ", "○") for l in lines),
        "subs": sum(l.strip().startswith("-") and not set(l.strip()) <= set("|- :") for l in lines if not l.strip().startswith("|")),
        "footnotes": sum(l.strip().startswith("＊") for l in lines),
        "tables": tables,
        "max_cols": max([len(r.strip().strip("|").split("|")) for r in tbl_rows], default=0),
        "numbers": set(NUM.findall(text)),
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

def has_markdown_leftover(line):
    stripped = line.strip()
    if not stripped:
        return False
    if HR.match(stripped):
        return True
    if HEADING.match(stripped):
        return True
    body = LEAD.sub("", line, count=1)  # 항목 선두 합법 기호(-, ㅇ 등)는 잔재 판정에서 제외
    if "`" in body:
        return True
    if "**" in body:
        return True
    if STRIKE.search(body):
        return True
    if ITALIC.search(body):
        return True
    if INLINE_DASH.search(body):
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


def content_pieces(text):
    """문장 단위 대조용 조각 — 계층 기호·강조·정렬 래퍼·이스케이프를 벗긴 알맹이.

    개조식 변환은 마크다운 `- `를 `ㅇ `·`□ `로 바꾸므로 선두 기호는 대조 대상이 아니다.
    표는 셀 단위로 펴서 행 구성이 달라져도 내용 손실만 잡는다.
    """
    pieces = []
    for line in text.splitlines():
        s = line.strip()
        if not s or set(s) <= set("|- :") or RT_PREAMBLE.match(s):
            continue
        s = UNESCAPE.sub(r"\1", RIGHT_TAG.sub("", s))
        s = s.replace("**", "").replace("`", "").replace("==", "")
        if s.startswith("|"):
            for cell in (c.strip() for c in s.strip("|").split("|")):
                cell = re.sub(r"\s+", " ", cell)
                if cell and not set(cell) <= set("- :"):
                    pieces.append(cell)
            continue
        s = re.sub(r"\s+", " ", SENT_LEAD.sub("", s)).strip()
        if s:
            pieces.append(s)
    # 수치 표기 정규화(1,234 ≡ 1234 · 23.70 ≡ 23.7)는 손실이 아니다 — numbers 대조와
    # 같은 규칙을 태워야 한쪽만 오탐을 낸다
    return [NUM.sub(lambda m: normalize_num(m.group()), x) for x in pieces]


def compare_texts(src, rt):
    a, b = profile_counts(src), profile_counts(rt)
    issues = []
    for k in ("sections", "points", "subs", "footnotes", "tables", "max_cols"):
        if a[k] != b[k]:
            issues.append({"rule": f"count-mismatch:{k}", "src": a[k], "roundtrip": b[k]})
    a_num = {normalize_num(n) for n in a["numbers"]}
    b_num = {normalize_num(n) for n in b["numbers"]}
    lost = a_num - b_num
    if lost:
        issues.append({"rule": "numbers-lost", "values": sorted(lost)[:20]})
    for i, line in enumerate(rt.splitlines(), 1):
        if not line.strip().startswith("|") and has_markdown_leftover(line):
            issues.append({"rule": "markdown-leftover", "line": i, "text": line.strip()[:80]})
    # 문장 자체가 바뀐 경우 — 개수·수치가 맞으면 통과하던 구멍을 막는다('26.9.10 신설).
    # 개수 대조는 "몇 개인가"만 보므로 문장이 통째로 갈려도 총량이 같으면 지나갔다.
    have = set(content_pieces(rt))
    dropped = [x for x in content_pieces(src) if x not in have]
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


USAGE = ("usage: validate_hwpx.py structural <path.hwpx> | "
         "validate_hwpx.py compare <src.md> <rt.md> | "
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
