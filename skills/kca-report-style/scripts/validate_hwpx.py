#!/usr/bin/env python3
"""
HWPX 구조 무결성 검증 — "조용한 실패"(파싱 OK·렌더 깨짐)의 유일한 사전 방어선.

한컴 HWPX는 LibreOffice·QuickLook에서 렌더 불가라 육안 확인이 어렵다. 특히
paraPr/charPr/borderFill의 id를 배열 인덱스처럼 취급하므로, 큰 임의 id나 끊긴
id를 쓰면 IDRef가 기본값으로 조용히 폴백돼 간격·정렬·테두리가 화면에서 무시된다
(파싱은 통과). 이 스크립트는 그 부류의 오류를 기계적으로 잡는다.

검사 항목:
  1) header의 각 스타일 컬렉션(paraPr·charPr·borderFill·fontface 그룹별)
     itemCnt == 실제 원소 수, id가 0..N-1 연속인지
  2) section의 모든 *IDRef(paraPrIDRef·charPrIDRef·borderFillIDRef·styleIDRef 등)가
     해당 컬렉션의 존재 id 범위 안인지 (dangling 참조 탐지)
  3) zip 무결성(testzip) + mimetype 무압축(STORED) 여부
  4) 모든 XML 파트 well-formed
  5) 표 행 폭 합계 == 표 폭 (span 없는 표, 열 폭 재분배 회귀 방어)

사용:
  python3 validate_hwpx.py <파일.hwpx>                 # 검증(비정상 시 exit 1)
  python3 validate_hwpx.py <파일.hwpx> --dump-styles   # charPr(크기·글꼴) 덤프(양식 재측정용)
"""
import sys, re, zipfile
import xml.etree.ElementTree as ET

HEADER = "Contents/header.xml"


def load(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        data = {n: z.read(n) for n in names}
    return names, data


def _collections(header):
    """(라벨, 원소태그로컬명, itemCnt, [id...]) 목록. fontface는 lang별 그룹마다 하나."""
    out = []
    for coll, el in [("paraProperties", "paraPr"), ("charProperties", "charPr"),
                     ("borderFills", "borderFill")]:
        m = re.search(r'<hh:%s\b[^>]*itemCnt="(\d+)"[^>]*>(.*?)</hh:%s>' % (coll, coll), header, re.S)
        if not m:
            continue
        ids = [int(x) for x in re.findall(r'<hh:%s\b[^>]*?\bid="(\d+)"' % el, m.group(2))]
        out.append((coll, el, int(m.group(1)), ids))
    # fontface: lang별 그룹 각각 검사
    for fm in re.finditer(r'<hh:fontface\b[^>]*lang="([^"]*)"[^>]*itemCnt="(\d+)"[^>]*>(.*?)</hh:fontface>',
                          header, re.S):
        ids = [int(x) for x in re.findall(r'<hh:font\b[^>]*?\bid="(\d+)"', fm.group(3))]
        out.append((f'fontface[{fm.group(1)}]', "font", int(fm.group(2)), ids))
    return out


def check_collections(header, errs, warns):
    # 진짜 불변식은 "빈틈·중복 없는 연속"이며 시작 번호는 컬렉션마다 다르다:
    # paraPr·charPr·fontface는 0-based(0..N-1), borderFill은 1-based(1..N). base 무관하게 검사.
    ranges = {}
    for label, el, itemcnt, ids in _collections(header):
        if len(ids) != itemcnt:
            errs.append(f"[{label}] itemCnt={itemcnt} 이지만 실제 원소={len(ids)}개 (불일치)")
        if ids:
            lo = min(ids)
            if sorted(ids) != list(range(lo, lo + len(ids))):
                span = set(range(lo, max(ids) + 1))
                gaps = sorted(span - set(ids))
                dups = sorted({i for i in ids if ids.count(i) > 1})
                msg = f"[{label}] id가 연속이 아님(시작 {lo})"
                if gaps: msg += f" / 빈 id={gaps[:10]}"
                if dups: msg += f" / 중복 id={dups[:10]}"
                errs.append(msg)
            expected_base = 1 if el == "borderFill" else 0
            if lo != expected_base:
                warns.append(f"[{label}] 시작 id={lo} (통상 {expected_base}-based) — 양식 확인 권장")
        if el in ("paraPr", "charPr", "borderFill"):
            ranges[el] = set(ids)
    return ranges


IDREF_TO_COLL = {
    "paraPrIDRef": "paraPr", "charPrIDRef": "charPr", "borderFillIDRef": "borderFill",
}


def check_idrefs(section, ranges, errs):
    for attr, el in IDREF_TO_COLL.items():
        valid = ranges.get(el)
        if valid is None:
            continue
        for m in re.finditer(attr + r'="(\d+)"', section):
            rid = int(m.group(1))
            if rid not in valid:
                errs.append(f"section: {attr}={rid} → {el} 컬렉션에 없는 id (dangling 참조 → 조용한 폴백)")
                break  # 종류별 첫 건만 보고(노이즈 방지)


def check_table_widths(section, errs):
    """span 없는 표: 각 행의 cellSz 합 == 표 폭(±2). 열 폭 재분배 회귀 방어."""
    for tm in re.finditer(r'<hp:tbl\b[^>]*>.*?</hp:tbl>', section, re.S):
        tbl = tm.group(0)
        if re.search(r'(?:colSpan|rowSpan)="(?:[2-9]|\d{2,})"', tbl):
            continue
        sz = re.search(r'<hp:sz width="(\d+)"', tbl)
        cc = re.search(r'colCnt="(\d+)"', tbl)
        if not sz or not cc:
            continue
        total, colcnt = int(sz.group(1)), int(cc.group(1))
        for rm in re.finditer(r'<hp:tr\b[^>]*>(.*?)</hp:tr>', tbl, re.S):
            ws = [int(x) for x in re.findall(r'<hp:cellSz width="(\d+)"', rm.group(1))]
            if len(ws) != colcnt:
                continue
            if abs(sum(ws) - total) > 2:
                errs.append(f"section: 표 행 폭 합({sum(ws)}) ≠ 표 폭({total}) "
                            f"— 열 폭 재분배 오류 의심")
                return   # 첫 건만 보고(노이즈 방지)


def check_xml(data, errs):
    for n, b in data.items():
        if n.endswith(".xml") or n.endswith(".hpf") or n.endswith(".hml"):
            try:
                ET.fromstring(b)
            except ET.ParseError as e:
                errs.append(f"{n}: XML not well-formed ({e})")


def check_zip(path, names, data, errs, warns):
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            errs.append(f"zip 손상: {bad}")
        if "mimetype" in names:
            info = z.getinfo("mimetype")
            if info.compress_type != zipfile.ZIP_STORED:
                errs.append("mimetype이 무압축(STORED)이 아님 → 한글이 인식 못할 수 있음")
            if data["mimetype"].strip() != b"application/hwp+zip":
                warns.append(f"mimetype 내용 예상과 다름: {data['mimetype'][:40]!r}")
        else:
            warns.append("mimetype 파트 없음")


def dump_styles(header):
    fonts = {m.group(1): m.group(2)
             for m in re.finditer(r'<hh:font\b[^>]*id="(\d+)"[^>]*face="([^"]*)"', header)}
    print("charPr id → 크기 / 한글글꼴")
    for m in re.finditer(r'<hh:charPr\b[^>]*\bid="(\d+)".*?</hh:charPr>', header, re.S):
        blk = m.group(0)
        h = re.search(r'height="(\d+)"', blk)
        fr = re.search(r'<hh:fontRef\b[^>]*hangul="(\d+)"', blk)
        sz = f"{int(h.group(1))/100}pt" if h else "?"
        face = fonts.get(fr.group(1), "?") if fr else "?"
        print(f"  charPr {m.group(1):>3}: {sz:>7}  {face}")


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    path = sys.argv[1]
    names, data = load(path)
    header = data.get(HEADER, b"").decode("utf-8", "replace")

    if "--dump-styles" in sys.argv:
        dump_styles(header)
        return

    errs, warns = [], []
    ranges = check_collections(header, errs, warns)
    for n in names:
        if re.match(r"Contents/section\d+\.xml$", n):
            sec = data[n].decode("utf-8", "replace")
            check_idrefs(sec, ranges, errs)
            check_table_widths(sec, errs)
    check_xml(data, errs)
    check_zip(path, names, data, errs, warns)

    for w in warns:
        print(f"  ⚠️  {w}")
    if errs:
        print(f"\n✗ 검증 실패 — {len(errs)}건")
        for e in errs:
            print(f"  ✗ {e}")
        sys.exit(1)
    print(f"✓ 구조 검증 통과 (스타일 id 연속·IDRef 범위·zip/xml 무결성){' — 경고 %d건' % len(warns) if warns else ''}")


if __name__ == "__main__":
    main()
