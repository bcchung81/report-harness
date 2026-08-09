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

USAGE = ("usage: validate_hwpx.py structural <path.hwpx> | "
         "validate_hwpx.py compare <src.md> <rt.md> | "
         "validate_hwpx.py numbers <draft.md> <research_dir>")

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
