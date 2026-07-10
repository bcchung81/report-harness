#!/usr/bin/env python3
"""
참고양식(KCA 공식 레터헤드) 기반 HWPX 생성 — 마스터 템플릿 병합 방식

참고양식 HWPX를 베이스로 삼아 레터헤드(로고·슬로건 이미지)·제목 그라데이션 표·
페이지 설정·계층별 글꼴 스타일을 '그대로' 유지하고, generate_document로 만든
개조식 본문만 참고양식의 기존 스타일 ID로 재지정해 주입한다.

즉 이미지·그라데이션을 새로 그리지 않고 원본을 그대로 사용한다.

사용:
  python3 build_from_template.py <generate_document_본문.hwpx> <출력.hwpx> \
          --title "제목" --date "< '26. 7. 3.(목), 부서명 >" [--template 참고양식.hwpx]

전제: 참고양식(assets/reference-form-교육계획안.hwpx)의 스타일 ID 매핑(아래 REF_*)은
      해당 파일 실측값. 참고양식 교체 시 refstyles 재측정 필요.
"""
import sys, os, re, zipfile, shutil, tempfile, argparse
import xml.etree.ElementTree as ET

NS = {
    "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
    "hh": "http://www.hancom.co.kr/hwpml/2011/head",
    "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    "hs": "http://www.hancom.co.kr/hwpml/2011/section",
}
for k, v in NS.items():
    ET.register_namespace(k, v)
HP = "{%s}" % NS["hp"]

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TEMPLATE = os.path.join(SKILL_DIR, "assets", "reference-form-교육계획안.hwpx")

# 계층별 charPr(참고양식 실측). paraPr은 문단 간격 위해 런타임에 순차 신규 id 할당.
# ※=49(12pt 맑은고딕) — 사용자 지정 12pt. 캡션=42(12pt 휴먼명조) — 사용자 지정 12pt.
REF_CHAR = {"□": "56", "ㅇ": "21", "-": "21", "※": "49", "캡션": "42"}
# 본문 데이터표(원본 커리큘럼 표 스타일 재현): 헤더행 음영+KoPub Bold, 본문 KoPub Medium
# 표 바깥 좌우 세로선 제거 → 첫 열 left=NONE, 마지막 열 right=NONE, 중간열은 4방 SOLID.
REF_TABLE_BF = "4"           # 중간열 본문셀(4방 SOLID)
TBL_HEADER_BF = "25"         # 중간열 헤더셀(4방 SOLID + #FFF7CC 음영)
TBL_HEADER_CHARPR = "77"     # 12pt KoPub돋움체 Bold
TBL_BODY_CHARPR = "8"        # 11pt KoPub돋움체 Medium

# 런타임에 신규 순차 id로 채움: 좌/우 끝열용 borderFill
BF = {}  # {"HL","HR","BL","BR"} -> borderFill id


def _tbl_bf(bid, left, right, shade):
    fill = ('<hc:fillBrush><hc:winBrush faceColor="#FFF7CC" hatchColor="#000000" alpha="0"/></hc:fillBrush>'
            if shade else '')
    return (
        f'<hh:borderFill id="{bid}" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
        '<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
        f'<hh:leftBorder type="{left}" width="0.12 mm" color="#000000"/>'
        f'<hh:rightBorder type="{right}" width="0.12 mm" color="#000000"/>'
        '<hh:topBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>' + fill + '</hh:borderFill>'
    )


def add_table_borderfills(header):
    """표 좌/우 끝열용 borderFill(바깥 세로선 제거) 신규 추가. 반환 (header, {key:id})."""
    ids = [int(x) for x in re.findall(r'<hh:borderFill\b[^>]*\bid="(\d+)"', header)]
    nid = max(ids) + 1
    defs = [("HL", "NONE", "SOLID", True), ("HR", "SOLID", "NONE", True),
            ("BL", "NONE", "SOLID", False), ("BR", "SOLID", "NONE", False)]
    add, idmap = "", {}
    for key, l, r, shade in defs:
        add += _tbl_bf(nid, l, r, shade)
        idmap[key] = str(nid)
        nid += 1
    header = header.replace("</hh:borderFills>", add + "</hh:borderFills>", 1)
    header = re.sub(r'(<hh:borderFills[^>]*itemCnt=")(\d+)(")',
                    lambda m: m.group(1) + str(int(m.group(2)) + len(defs)) + m.group(3), header, count=1)
    return header, idmap
REF_TITLE_TEXT = "2026년도 AI·데이터 활용을 위한 맞춤형 교육 계획(안)"

# 계층별 선두 공백(참고양식 실측): □0 · ㅇ1 · -3 · ※1
LEAD = {"□": 0, "ㅇ": 1, "-": 3, "※": 1, "캡션": 0}

# 신규 paraPr 정의: 논리키 -> (복제 base paraPr, 위 간격 HWPUNIT(1pt=100), 정렬, intent오버라이드)
# base는 참고양식의 계층별 paraPr(계층 hanging intent 보존): □42·ㅇ38·※86
SPACING_DEFS = [
    ("□", "42", 1000, "LEFT", None),    # □ 앞 10pt
    ("ㅇ", "38", 600, None, None),       # □↔ㅇ 6pt
    ("-", "73", 300, None, None),        # ㅇ↔- 3pt (참고 '-' paraPr, intent 보존)
    ("※", "86", 300, None, None),        # -↔※ 3pt (참고 본문 ※ paraPr)
    ("표", "38", 0, "CENTER", 0),        # 표/캡션 가운데, hanging 제거(intent 0)
]

# 런타임 채움 (main에서 설정): 계층 -> (paraPr, charPr), 표 paraPr
REF = {}
REF_TABLE_PP = None


def add_spacing_paraprs(header):
    """참고양식 paraPr을 복제해 문단 간격/정렬 신규 paraPr 추가.
    ⚠️ HWPX는 id를 0-based 연속 인덱스로 취급 → 반드시 max+1부터 순차 id 부여.
    반환: (header, {논리키: 신규 paraPr id})."""
    ids = [int(x) for x in re.findall(r'<hh:paraPr\b[^>]*\bid="(\d+)"', header)]
    nid = max(ids) + 1
    additions, idmap = "", {}
    for key, base, prev, align, intent in SPACING_DEFS:
        m = re.search(r'<hh:paraPr\b[^>]*\bid="' + base + r'".*?</hh:paraPr>', header, re.S)
        blk = re.sub(r'\bid="' + base + '"', f'id="{nid}"', m.group(0), count=1)
        if "<hc:prev" in blk:
            blk = re.sub(r'(<hc:prev value=")-?\d+(")', r'\g<1>' + str(prev) + r'\g<2>', blk, count=1)
        else:
            blk = blk.replace("</hh:margin>", f'<hc:prev value="{prev}" unit="HWPUNIT"/></hh:margin>', 1)
        if intent is not None:
            blk = re.sub(r'(<hc:intent value=")-?\d+(")', r'\g<1>' + str(intent) + r'\g<2>', blk, count=1)
        if align:
            blk = re.sub(r'(<hh:align\b[^>]*horizontal=")[^"]*(")', r'\g<1>' + align + r'\g<2>', blk, count=1)
        additions += blk
        idmap[key] = str(nid)
        nid += 1
    header = header.replace("</hh:paraProperties>", additions + "</hh:paraProperties>", 1)
    header = re.sub(r'(<hh:paraProperties[^>]*itemCnt=")(\d+)(")',
                    lambda m: m.group(1) + str(int(m.group(2)) + len(SPACING_DEFS)) + m.group(3), header, count=1)
    return header, idmap


def read_all(path):
    with zipfile.ZipFile(path) as z:
        return {n: z.read(n) for n in z.namelist()}, z.namelist()


def classify(t):
    t = t.lstrip()
    t = re.sub(r'^[○ㅇ\-□]\s*(?=※)', '', t)   # "○ ※" → "※"
    if t.startswith("["):        return "캡션"
    if t.startswith("※"):        return "※"
    if t.startswith("＊"):        return "※"   # ＊ 용어 각주 → ※와 동일 각주 스타일(맑은고딕12). *는 MD 불릿이라 builder가 ＊로 치환해 넘김
    if t.startswith("□"):        return "□"
    if t[:1] in ("○", "ㅇ"):     return "ㅇ"
    if t.startswith("-"):        return "-"
    return None


def first_text(p):
    for t in p.iter(HP + "t"):
        if t.text and t.text.strip():
            return t.text
    return ""


def remap_paragraph(p):
    """generate 본문 문단을 참고양식 스타일 ID로 재지정."""
    tbls = p.findall(".//" + HP + "tbl")
    if tbls:
        # 본문 데이터표: 원본 커리큘럼 표 스타일(헤더행 음영+KoPub Bold, 본문 KoPub Medium),
        # 표 가운데 정렬. 헤더행(rowAddr=0)과 본문행을 구분 적용.
        p.set("paraPrIDRef", REF_TABLE_PP)   # 표 객체 담은 문단 가운데
        for tbl in tbls:
            tbl.set("borderFillIDRef", REF_TABLE_BF)
            ncol = int(tbl.get("colCnt", "1"))
            pos = tbl.find(HP + "pos")
            if pos is not None:
                pos.set("horzAlign", "CENTER")
            for tc in tbl.iter(HP + "tc"):
                addr = tc.find(HP + "cellAddr")
                is_header = addr is not None and addr.get("rowAddr") == "0"
                col = int(addr.get("colAddr")) if addr is not None else 0
                # 바깥 좌우 세로선 제거: 첫 열/마지막 열은 전용 borderFill
                if is_header:
                    bf = BF["HL"] if col == 0 else BF["HR"] if col == ncol - 1 else TBL_HEADER_BF
                else:
                    bf = BF["BL"] if col == 0 else BF["BR"] if col == ncol - 1 else REF_TABLE_BF
                tc.set("borderFillIDRef", bf)
                for cp in tc.iter(HP + "p"):
                    cp.set("paraPrIDRef", REF_TABLE_PP)   # 셀 텍스트 가운데
                for run in tc.iter(HP + "run"):
                    if run.get("charPrIDRef") is not None:
                        run.set("charPrIDRef", TBL_HEADER_CHARPR if is_header else TBL_BODY_CHARPR)
        return True
    # 텍스트 문단
    txt = first_text(p)
    key = classify(txt)
    if not key:
        return False
    pp, cp = REF[key]
    p.set("paraPrIDRef", pp)
    for run in p.iter(HP + "run"):
        if run.get("charPrIDRef") is not None:
            run.set("charPrIDRef", cp)
    # 첫 텍스트: 이중기호(○ ※) 정리 + 마커 정규화 + 계층별 선두 공백 삽입(참고양식 실측)
    for t in p.iter(HP + "t"):
        if t.text:
            cleaned = re.sub(r'^\s*[○ㅇ\-□]\s*(?=※)', '', t.text).lstrip()
            if key == "ㅇ":
                cleaned = re.sub(r'^[○◦∘]', 'ㅇ', cleaned)  # 원본 마커 'ㅇ'(U+3147)로
            t.text = " " * LEAD.get(key, 0) + cleaned
            break
    return True


def extract_body(gen_section_bytes):
    """generate 산출물 section에서 본문 문단(제목 문단 제외)을 참고 스타일로 remap해 문자열 리스트로."""
    sec = ET.fromstring(gen_section_bytes)
    # 최상위 hp:p 자식들
    ps = sec.findall(HP + "p")
    out = []
    for i, p in enumerate(ps):
        if i == 0:
            continue  # 제목(+secPr) 문단 제외 — secPr은 참고양식 것 사용
        if remap_paragraph(p):
            out.append(ET.tostring(p, encoding="unicode"))
    return out


def replace_text_once(section, old_inner_regex, new_text):
    """<hp:t>...</hp:t> 안의 특정 텍스트를 new_text로 1회 치환."""
    return re.sub(r'<hp:t>' + old_inner_regex + r'</hp:t>',
                  '<hp:t>' + new_text + '</hp:t>', section, count=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("body_hwpx")
    ap.add_argument("output")
    ap.add_argument("--title", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--template", default=DEFAULT_TEMPLATE)
    a = ap.parse_args()

    files, names = read_all(a.template)
    gen_files, _ = read_all(a.body_hwpx)

    # 문단 간격/정렬용 신규 paraPr + 표 좌/우 끝열 borderFill 추가 (순차 id)
    global REF, REF_TABLE_PP, BF
    header, idmap = add_spacing_paraprs(files["Contents/header.xml"].decode("utf-8"))
    header, BF = add_table_borderfills(header)
    files["Contents/header.xml"] = header.encode("utf-8")
    REF = {
        "□":   (idmap["□"], REF_CHAR["□"]),
        "ㅇ":  (idmap["ㅇ"], REF_CHAR["ㅇ"]),
        "-":   (idmap["-"], REF_CHAR["-"]),  # '-' paraPr(intent 보존) + 위 3pt, 선두공백 3
        "※":   (idmap["※"], REF_CHAR["※"]),
        "캡션": (idmap["표"], REF_CHAR["캡션"]),
    }
    REF_TABLE_PP = idmap["표"]

    section = files["Contents/section0.xml"].decode("utf-8")
    body_paras = extract_body(gen_files["Contents/section0.xml"])

    # 1) 제목 텍스트 교체 (참고양식 제목 셀)
    section = replace_text_once(section, re.escape(REF_TITLE_TEXT), a.title)

    # 2) 날짜 텍스트 교체 (< ... > 발신정보) — &lt; 로 시작하는 첫 <hp:t>
    date_esc = a.date.replace("<", "&lt;").replace(">", "&gt;")
    section = re.sub(r'<hp:t>&lt;[^<]*&gt;</hp:t>',
                     '<hp:t>' + date_esc + '</hp:t>', section, count=1)

    # 3) 참고양식 본문 제거 후 새 본문 주입
    #    본문 시작 = 첫 "□ 추진 배경" 문단, 끝 = </hs:sec> 직전
    m = re.search(r'□\s*추진\s*배경', section)
    if not m:
        m = re.search(r'□', section)
    body_start = section.rfind("<hp:p ", 0, m.start())
    sec_end = section.rfind("</hs:sec>")
    new_body = "".join(body_paras)
    section = section[:body_start] + new_body + section[sec_end:]

    files["Contents/section0.xml"] = section.encode("utf-8")

    # 4) 재패킹 (참고양식 파일 세트 유지 = 이미지·content.hpf·header 그대로)
    if os.path.exists(a.output):
        os.remove(a.output)
    with zipfile.ZipFile(a.output, "w", zipfile.ZIP_DEFLATED) as z:
        if "mimetype" in names:
            z.writestr("mimetype", files["mimetype"], compress_type=zipfile.ZIP_STORED)
        for n in names:
            if n != "mimetype":
                z.writestr(n, files[n])
    print(f"✓ 참고양식 기반 생성 완료 → {a.output}")


if __name__ == "__main__":
    main()
