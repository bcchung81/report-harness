#!/usr/bin/env python3
"""
KCA 보고서 HWPX 후처리 (하이브리드 C안 · 계층별 글꼴 적용)

generate_document(preset="보고서")로 만든 HWPX를 열어 프리셋이 못 잡는
서식(제목 박스·계층별 글꼴/크기·이중 기호)을 참고양식대로 교정한다.
본문 개조식 구조(□/ㅇ/- 매핑)는 유지하고 문체는 건드리지 않는다.

참고양식(2026 교육계획안) 실측 기준:
  제목        18pt / HY헤드라인M   + 테두리 박스
  발신 < >    12pt / 휴먼명조
  □ 섹션      15pt / HY헤드라인M
  ㅇ · - 본문  15pt / 휴먼명조
  ※ 주석      12pt / 맑은 고딕
  [ 캡션 ]    13pt / 휴먼명조
  표 내부      11pt / 휴먼명조
  이중 기호 "○ ※" → "※"

사용:  python3 postprocess.py <입력.hwpx> [출력.hwpx]
출력 미지정 시 제자리 교정(.bak 백업). 실행 후 parse_document로 재검증할 것.
"""
import sys, os, re, zipfile, shutil, tempfile

HEADER = "Contents/header.xml"
SECTION = "Contents/section0.xml"

# 주입할 한글 글꼴 (참고양식 사용 글꼴)
FONTS = ["휴먼명조", "HY헤드라인M", "맑은 고딕"]

# 계층별 스타일: (height 1/100pt, 글꼴명)
STYLE = {
    "title":   (1800, "HY헤드라인M"),
    "date":    (1200, "휴먼명조"),
    "square":  (1500, "HY헤드라인M"),   # □
    "dot":     (1500, "휴먼명조"),      # ㅇ / ○ / -
    "note":    (1200, "맑은 고딕"),     # ※
    "caption": (1300, "휴먼명조"),      # [ ... ]
    "table":   (1100, "휴먼명조"),
}
BORDERFILL_ID = "90"   # 제목 박스용 (충돌 피해 큰 값)
RIGHT_PARAPR_ID = "91" # 발신정보 우측정렬용

# 페이지 여백 (참고양식 실측, HWPUNIT). 공문서 표준: 좌우 15mm·상하 10mm.
PAGE_MARGIN = dict(left="4251", right="4251", top="2834", bottom="2834",
                   header="4251", footer="2834", gutter="0")


def add_fonts(h):
    """HANGUL fontface 그룹에 FONTS를 추가하고 name→id 매핑 반환."""
    grp = re.search(r'(<hh:fontface\b[^>]*lang="HANGUL"[^>]*>)(.*?)(</hh:fontface>)', h, re.S)
    body = grp.group(2)
    existing = dict((m.group(2), m.group(1))
                    for m in re.finditer(r'<hh:font\b[^>]*id="(\d+)"[^>]*face="([^"]*)"', body))
    ids = [int(m) for m in re.findall(r'<hh:font\b[^>]*id="(\d+)"', body)]
    nextid = max(ids) + 1
    base = re.search(r'<hh:font\b[^>]*id="0".*?</hh:font>', body, re.S)
    base = base.group(0) if base else re.search(r'<hh:font\b[^>]*id="0"[^>]*/>', body).group(0)
    name2id = dict(existing)
    added = 0
    for face in FONTS:
        if face in name2id:
            continue
        blk = re.sub(r'\bid="0"', f'id="{nextid}"', base, count=1)
        blk = re.sub(r'face="[^"]*"', f'face="{face}"', blk, count=1)
        body += blk
        name2id[face] = str(nextid)
        nextid += 1
        added += 1
    newgrp = grp.group(1) + body + grp.group(3)
    # fontCnt 갱신
    newgrp = re.sub(r'(fontCnt=")(\d+)(")',
                    lambda m: m.group(1) + str(int(m.group(2)) + added) + m.group(3), newgrp, count=1)
    h = h[:grp.start()] + newgrp + h[grp.end():]
    return h, name2id


def add_charprs(h, name2id):
    """STYLE별 charPr를 charPr id=0 기반으로 추가하고 key→charPrId 매핑 반환."""
    base = re.search(r'<hh:charPr\b[^>]*\bid="0".*?</hh:charPr>', h, re.S).group(0)
    ids = [int(x) for x in re.findall(r'<hh:charPr\b[^>]*\bid="(\d+)"', h)]
    nextid = max(ids) + 1
    additions = ""
    key2cp = {}
    for key, (height, face) in STYLE.items():
        fid = name2id[face]
        blk = re.sub(r'\bid="0"', f'id="{nextid}"', base, count=1)
        blk = re.sub(r'height="\d+"', f'height="{height}"', blk, count=1)
        # fontRef의 hangul/hanja/latin 모두 대상 글꼴로
        blk = re.sub(r'(<hh:fontRef\b[^>]*?)hangul="\d+"', r'\1hangul="' + fid + '"', blk, count=1)
        blk = re.sub(r'(<hh:fontRef\b[^>]*?)hanja="\d+"', r'\1hanja="' + fid + '"', blk, count=1)
        additions += blk
        key2cp[key] = str(nextid)
        nextid += 1
    h = h.replace("</hh:charProperties>", additions + "</hh:charProperties>", 1)
    h = re.sub(r'(<hh:charProperties[^>]*itemCnt=")(\d+)(")',
               lambda m: m.group(1) + str(int(m.group(2)) + len(STYLE)) + m.group(3), h, count=1)
    return h, key2cp


# 제목 표 borderFill id (충돌 회피 큰 값)
BF_OUTER = "90"    # 표 외곽 얇은 실선 박스
BF_TOPGRAD = "92"  # 상단 그라데이션 바 (#3057B9 → #DFE6F7)
BF_TITLE = "93"    # 제목 셀 (테두리·채움 없음)
BF_BOTGRAD = "94"  # 하단 그라데이션 바 (#DFE6F7 → #3057B9)

# 참고양식 그라데이션 색상
GRAD_DARK = "#3057B9"
GRAD_LIGHT = "#DFE6F7"


def _grad_bf(bid, c1, c2):
    return (
        f'<hh:borderFill id="{bid}" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
        '<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:leftBorder type="NONE" width="0.1 mm" color="#000000"/><hh:rightBorder type="NONE" width="0.1 mm" color="#000000"/>'
        '<hh:topBorder type="NONE" width="0.1 mm" color="#000000"/><hh:bottomBorder type="NONE" width="0.1 mm" color="#000000"/>'
        '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>'
        '<hc:fillBrush><hc:gradation type="LINEAR" angle="90" centerX="0" centerY="0" step="255" '
        f'colorNum="2" stepCenter="50" alpha="0"><hc:color value="{c1}"/><hc:color value="{c2}"/></hc:gradation></hc:fillBrush>'
        '</hh:borderFill>'
    )


def add_title_borderfills(h):
    outer = (
        f'<hh:borderFill id="{BF_OUTER}" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
        '<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:leftBorder type="SOLID" width="0.12 mm" color="#000000"/><hh:rightBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:topBorder type="SOLID" width="0.12 mm" color="#000000"/><hh:bottomBorder type="SOLID" width="0.12 mm" color="#000000"/>'
        '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/></hh:borderFill>'
    )
    title = (
        f'<hh:borderFill id="{BF_TITLE}" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0">'
        '<hh:slash type="NONE" Crooked="0" isCounter="0"/><hh:backSlash type="NONE" Crooked="0" isCounter="0"/>'
        '<hh:leftBorder type="NONE" width="0.1 mm" color="#000000"/><hh:rightBorder type="NONE" width="0.1 mm" color="#000000"/>'
        '<hh:topBorder type="NONE" width="0.1 mm" color="#000000"/><hh:bottomBorder type="NONE" width="0.1 mm" color="#000000"/>'
        '<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/></hh:borderFill>'
    )
    add = outer + _grad_bf(BF_TOPGRAD, GRAD_DARK, GRAD_LIGHT) + title + _grad_bf(BF_BOTGRAD, GRAD_LIGHT, GRAD_DARK)
    h = h.replace("</hh:borderFills>", add + "</hh:borderFills>", 1)
    h = re.sub(r'(<hh:borderFills[^>]*itemCnt=")(\d+)(")',
               lambda m: m.group(1) + str(int(m.group(2)) + 4) + m.group(3), h, count=1)
    return h


def _title_cell(bid, height, parapr, charpr, text=""):
    inner = f'<hp:t>{text}</hp:t>' if text else '<hp:t></hp:t>'
    return (
        f'<hp:tr><hp:tc name="" header="0" hasMargin="0" protect="0" editable="0" dirty="0" borderFillIDRef="{bid}">'
        '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="CENTER" linkListIDRef="0" '
        'linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">'
        f'<hp:p paraPrIDRef="{parapr}" styleIDRef="0"><hp:run charPrIDRef="{charpr}">{inner}</hp:run></hp:p>'
        '</hp:subList><hp:cellAddr colAddr="0" rowAddr="{r}"/><hp:cellSpan colSpan="1" rowSpan="1"/>'
        f'<hp:cellSz width="50624" height="{height}"/><hp:cellMargin left="141" right="141" top="141" bottom="141"/></hp:tc></hp:tr>'
    )


def build_title_table(title_text, cp_title):
    # 3행1열: 상단 그라데이션 바 / 제목 / 하단 역그라데이션 바 (treatAsChar 인라인)
    open_tag = (
        '<hp:tbl id="1001" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" '
        'lock="0" dropcapstyle="None" pageBreak="NONE" repeatHeader="0" rowCnt="3" colCnt="1" cellSpacing="0" '
        f'borderFillIDRef="{BF_OUTER}" noAdjust="0">'
        '<hp:sz width="50624" widthRelTo="ABSOLUTE" height="3406" heightRelTo="ABSOLUTE" protect="0"/>'
        '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" '
        'vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="CENTER" vertOffset="0" horzOffset="0"/>'
        '<hp:outMargin left="0" right="0" top="0" bottom="0"/><hp:inMargin left="140" right="140" top="140" bottom="140"/>'
    )
    r0 = _title_cell(BF_TOPGRAD, 380, "0", "0").replace('rowAddr="{r}"', 'rowAddr="0"')
    r1 = _title_cell(BF_TITLE, 2646, "1", cp_title, title_text).replace('rowAddr="{r}"', 'rowAddr="1"')
    r2 = _title_cell(BF_BOTGRAD, 380, "0", "0").replace('rowAddr="{r}"', 'rowAddr="2"')
    return open_tag + r0 + r1 + r2 + "</hp:tbl>"


def discover_level_paras(s):
    """section에서 마커별 문단의 paraPrIDRef 수집(표 밖). {level: set(pid)}"""
    res = {"□": set(), "ㅇ": set(), "-": set(), "발신": set()}
    outside = re.sub(r'<hp:tbl\b.*?</hp:tbl>', '', s, flags=re.S)
    for m in re.finditer(r'<hp:p\b[^>]*paraPrIDRef="(\d+)"[^>]*>(.*?)</hp:p>', outside, re.S):
        tm = re.search(r'<hp:t>(.*?)</hp:t>', m.group(2), re.S)
        if not tm:
            continue
        t = tm.group(1).lstrip()
        if t.startswith("&lt;"):        res["발신"].add(m.group(1))
        elif t.startswith("□"):         res["□"].add(m.group(1))
        elif t[:1] in ("○", "ㅇ"):      res["ㅇ"].add(m.group(1))
        elif t.startswith("-"):         res["-"].add(m.group(1))
    return res


def set_para(h, pid, align=None, flush=True):
    """paraPr(pid)의 정렬·여백을 제자리 수정. flush면 left/intent=0."""
    def fix(m):
        blk = m.group(0)
        if align:
            blk = re.sub(r'(<hh:align\b[^>]*horizontal=")[^"]*(")', r'\g<1>' + align + r'\g<2>', blk, count=1)
        if flush:
            blk = re.sub(r'(<hc:left value=")-?\d+(")', r'\g<1>0\g<2>', blk, count=1)
            blk = re.sub(r'(<hc:intent value=")-?\d+(")', r'\g<1>0\g<2>', blk, count=1)
        return blk
    return re.sub(r'<hh:paraPr\b[^>]*\bid="' + pid + r'".*?</hh:paraPr>', fix, h, count=1, flags=re.S)


def apply_layout(h, s):
    """참고양식 정합: □ 좌측+flush, ㅇ/- flush, 발신 우측정렬(신규 paraPr)."""
    levels = discover_level_paras(s)
    for pid in levels["□"]:
        h = set_para(h, pid, align="LEFT", flush=True)
    for pid in levels["ㅇ"] | levels["-"]:
        h = set_para(h, pid, align="JUSTIFY", flush=True)
    # 발신정보 우측정렬: paraPr 0은 공유되므로 클론 신규 생성 후 그 문단만 재지정
    base = re.search(r'<hh:paraPr\b[^>]*\bid="0".*?</hh:paraPr>', h, re.S).group(0)
    blk = re.sub(r'\bid="0"', f'id="{RIGHT_PARAPR_ID}"', base, count=1)
    if "<hh:align" in blk:
        blk = re.sub(r'(<hh:align\b[^>]*horizontal=")[^"]*(")', r'\g<1>RIGHT\g<2>', blk, count=1)
    h = h.replace("</hh:paraProperties>", blk + "</hh:paraProperties>", 1)
    h = re.sub(r'(<hh:paraProperties[^>]*itemCnt=")(\d+)(")',
               lambda m: m.group(1) + str(int(m.group(2)) + 1) + m.group(3), h, count=1)
    return h


def fix_page_margin(s):
    def fix(m):
        blk = m.group(0)
        for k, v in PAGE_MARGIN.items():
            blk = re.sub(r'(\b' + k + r'=")[^"]*(")', r'\g<1>' + v + r'\g<2>', blk, count=1)
        return blk
    # pagePr 내부 <hp:margin .../>
    return re.sub(r'<hp:pagePr\b.*?</hp:pagePr>',
                  lambda mm: re.sub(r'<hp:margin\b[^>]*/>', fix, mm.group(0), count=1),
                  s, count=1, flags=re.S)


def edit_section(s, cp):
    # 발신정보 문단 → 우측정렬 paraPr 재지정
    def right_align(m):
        run = m.group(0)
        tm = re.search(r'<hp:t>(.*?)</hp:t>', run, re.S)
        if tm and tm.group(1).lstrip().startswith("&lt;"):
            return re.sub(r'(<hp:p\b[^>]*)paraPrIDRef="\d+"', r'\1paraPrIDRef="' + RIGHT_PARAPR_ID + '"', run, count=1)
        return run
    s = re.sub(r'<hp:p\b[^>]*>.*?</hp:p>', right_align, s, count=0, flags=re.S)

    s = fix_page_margin(s)
    # 이중 기호 제거
    s = re.sub(r'(<hp:t>)\s*[○ㅇ\-□]\s*※', r'\1※', s)

    # 표 내부: 모든 run → table charPr
    def shrink(m):
        return re.sub(r'(<hp:run charPrIDRef=")\d+(")', r'\g<1>' + cp["table"] + r'\g<2>', m.group(0))
    s = re.sub(r'<hp:tbl\b.*?</hp:tbl>', shrink, s, flags=re.S)

    # 계층 마커별 run 재지정 (표 밖). run의 첫 <hp:t> 텍스트로 판별.
    # 마커 없는 첫 텍스트 run = 제목(secPr가 끼어 있어도 <hp:t>로 판별).
    title_done = [False]
    def repoint(m):
        run = m.group(0)
        tm = re.search(r'<hp:t>(.*?)</hp:t>', run, re.S)
        if not tm or not tm.group(1).strip():
            return run
        t = tm.group(1).lstrip()
        if t.startswith("&lt;"):          key = "date"
        elif t.startswith("["):           key = "caption"
        elif t.startswith("※"):           key = "note"
        elif t.startswith("＊"):           key = "note"   # ＊ 용어 각주 → ※와 동일 각주 스타일(맑은고딕12). 폴백 경로 동기화
        elif t.startswith("□"):           key = "square"
        elif t[:1] in ("○", "ㅇ"):        key = "dot"
        elif t.startswith("-"):           key = "dot"
        elif not title_done[0]:           key = "title"; title_done[0] = True
        else:                             return run
        return re.sub(r'charPrIDRef="\d+"', 'charPrIDRef="' + cp[key] + '"', run, count=1)
    # 표 블록은 이미 처리했으니, 표 밖 구간만 마커 재지정
    parts = re.split(r'(<hp:tbl\b.*?</hp:tbl>)', s, flags=re.S)
    for i in range(0, len(parts), 2):   # 짝수 인덱스 = 표 밖
        parts[i] = re.sub(r'<hp:run\b[^>]*charPrIDRef="\d+"[^>]*>.*?</hp:run>', repoint, parts[i], flags=re.S)
    s = "".join(parts)

    # 제목 → 3행1열 그라데이션 표로 치환 (첫 문단의 secPr 보존)
    mp = re.search(r'<hp:p\b[^>]*>.*?</hp:p>', s, re.S)
    if mp:
        p0 = mp.group(0)
        mt = re.search(r'<hp:t>(.*?)</hp:t>', p0, re.S)
        if mt:
            table = build_title_table(mt.group(1), cp["title"])
            p0n = p0.replace(mt.group(0), "", 1)  # 제목 텍스트 제거(secPr 유지)
            p0n = p0n.replace("</hp:p>", f'<hp:run charPrIDRef="0">{table}</hp:run></hp:p>', 1)
            s = s[:mp.start()] + p0n + s[mp.end():]
    return s


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else src
    if dst == src:
        shutil.copy(src, src + ".bak")

    tmp = tempfile.mkdtemp()
    with zipfile.ZipFile(src) as z:
        names = z.namelist()
        z.extractall(tmp)

    hp, sp = os.path.join(tmp, HEADER), os.path.join(tmp, SECTION)
    h = open(hp, encoding="utf-8").read()
    s = open(sp, encoding="utf-8").read()

    h, name2id = add_fonts(h)
    h, cp = add_charprs(h, name2id)
    h = add_title_borderfills(h)
    h = apply_layout(h, s)
    s = edit_section(s, cp)

    open(hp, "w", encoding="utf-8").write(h)
    open(sp, "w", encoding="utf-8").write(s)

    if os.path.exists(dst):
        os.remove(dst)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        if "mimetype" in names:
            z.write(os.path.join(tmp, "mimetype"), "mimetype", compress_type=zipfile.ZIP_STORED)
        for n in names:
            if n != "mimetype":
                z.write(os.path.join(tmp, n), n)
    shutil.rmtree(tmp)
    print(f"✓ 후처리 완료(계층별 글꼴 적용) → {dst}")


if __name__ == "__main__":
    main()
