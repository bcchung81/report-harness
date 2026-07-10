#!/usr/bin/env python3
"""HWPX 본문에 PNG 그림(treatAsChar 인라인)을 주입한다.

참고양식이 기존에 담고 있던 로고 그림(hp:pic + hc:img + content.hpf opf:item)의
구조를 그대로 복제해, 새 PNG를 BinData/imageN.PNG로 추가하고 manifest에 등록한 뒤
지정 앵커 문단 뒤(또는 본문 끝)에 그림 문단을 삽입한다.

치명적 불변식: content.hpf opf:item id는 imageN(연속). 그림 id/instid는 문서 내 유일(결정론적·충돌검사).
사용: python3 inject_image.py <base.hwpx> <image.png> <out.hwpx>
        [--marker "도해"]   # 이 텍스트를 포함한 문단을 그림으로 '치환'(마커 위치에 정확 배치, 권장)
        [--anchor "텍스트"] # 이 텍스트 문단 '뒤'에 삽입(마커 없을 때 폴백)
        [--width-mm 170]
"""
import sys, os, re, zipfile, shutil, argparse, struct, hashlib

HWPUNIT_PER_PX = 100          # 로고 실측: 600px→60000
HWPUNIT_PER_MM = 283.465

def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        raise ValueError("PNG 아님: %s" % path)
    w, h = struct.unpack(">II", head[16:24])
    return w, h

def next_image_index(names):
    idx = 0
    for n in names:
        m = re.match(r"BinData/image(\d+)\.", n, re.I)
        if m:
            idx = max(idx, int(m.group(1)))
    return idx + 1

def _det_id(seed, taken):
    """결정론적(hashlib) 고유 id — 실행마다 동일, 기존 id와 충돌 시 증가."""
    base = 1000000000 + int(hashlib.md5(seed.encode()).hexdigest()[:8], 16) % 900000000
    while base in taken or (base + 1) in taken:
        base += 2
    taken.add(base); taken.add(base + 1)
    return base, base + 1

def build_pic_xml(img_id, org_w, org_h, disp_w, disp_h, taken_ids):
    """로고 pic 블록 구조를 복제한 그림 XML (imgClip=전체=무크롭)."""
    sca = round(disp_w / org_w, 6)
    pid, iid = _det_id(img_id, taken_ids)
    return (
        f'<hp:p id="0" paraPrIDRef="0" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0">'
        f'<hp:run charPrIDRef="0">'
        f'<hp:pic id="{pid}" zOrder="0" numberingType="PICTURE" textWrap="TOP_AND_BOTTOM" '
        f'textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" href="" groupLevel="0" instid="{iid}" reverse="0">'
        f'<hp:offset x="0" y="0"/>'
        f'<hp:orgSz width="{org_w}" height="{org_h}"/>'
        f'<hp:curSz width="{disp_w}" height="{disp_h}"/>'
        f'<hp:flip horizontal="0" vertical="0"/>'
        f'<hp:rotationInfo angle="0" centerX="{disp_w//2}" centerY="{disp_h//2}" rotateimage="1"/>'
        f'<hp:renderingInfo>'
        f'<hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
        f'<hc:scaMatrix e1="{sca}" e2="0" e3="0" e4="0" e5="{sca}" e6="0"/>'
        f'<hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/>'
        f'</hp:renderingInfo>'
        f'<hc:img binaryItemIDRef="{img_id}" bright="0" contrast="0" effect="REAL_PIC" alpha="0"/>'
        f'<hp:imgRect><hc:pt0 x="0" y="0"/><hc:pt1 x="{org_w}" y="0"/>'
        f'<hc:pt2 x="{org_w}" y="{org_h}"/><hc:pt3 x="0" y="{org_h}"/></hp:imgRect>'
        f'<hp:imgClip left="0" right="{org_w}" top="0" bottom="{org_h}"/>'
        f'<hp:inMargin left="0" right="0" top="0" bottom="0"/>'
        f'<hp:imgDim dimwidth="{org_w}" dimheight="{org_h}"/>'
        f'<hp:effects/>'
        f'<hp:sz width="{disp_w}" widthRelTo="ABSOLUTE" height="{disp_h}" heightRelTo="ABSOLUTE" protect="0"/>'
        f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" '
        f'holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="COLUMN" vertAlign="TOP" horzAlign="CENTER" '
        f'vertOffset="0" horzOffset="0"/>'
        f'<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
        f'<hp:shapeComment>워크플로우 도해</hp:shapeComment>'
        f'</hp:pic></hp:run></hp:p>'
    )

def existing_shape_ids(section_xml):
    """문서 내 기존 도형 id/instid 수집(충돌 회피용)."""
    ids = set()
    for m in re.finditer(r'\b(?:id|instid)="(\d{6,})"', section_xml):
        ids.add(int(m.group(1)))
    return ids

def replace_marker(section_xml, pic_xml, marker):
    """marker 텍스트를 포함한 hp:p를 pic 문단으로 '치환'(마커 위치에 정확 배치)."""
    for m in re.finditer(r'<hp:p\b.*?</hp:p>', section_xml, re.S):
        if marker in re.sub(r'<[^>]+>', '', m.group(0)):
            return section_xml[:m.start()] + pic_xml + section_xml[m.end():], True
    return section_xml, False   # 마커 못 찾음

def insert_after_anchor(section_xml, pic_xml, anchor):
    """anchor 텍스트를 포함한 hp:p 뒤에 pic 문단 삽입. 없으면 마지막 hp:p 뒤."""
    para_iter = list(re.finditer(r'<hp:p\b.*?</hp:p>', section_xml, re.S))
    target_end = None
    if anchor:
        for m in para_iter:
            if anchor in re.sub(r'<[^>]+>', '', m.group(0)):
                target_end = m.end()
                break
    if target_end is None and para_iter:
        target_end = para_iter[-1].end()   # 폴백: 본문 끝
    if target_end is None:
        raise ValueError("삽입 지점(hp:p)을 찾지 못함")
    return section_xml[:target_end] + pic_xml + section_xml[target_end:]

def repack(srcdir, out_path):
    """mimetype을 STORED로 먼저, 나머지는 DEFLATE로 재패킹."""
    if os.path.exists(out_path):
        os.remove(out_path)
    with zipfile.ZipFile(out_path, "w") as z:
        mp = os.path.join(srcdir, "mimetype")
        if os.path.exists(mp):
            z.write(mp, "mimetype", compress_type=zipfile.ZIP_STORED)
        for root, _, files in os.walk(srcdir):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, srcdir)
                if rel == "mimetype":
                    continue
                z.write(full, rel, compress_type=zipfile.ZIP_DEFLATED)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base"); ap.add_argument("png"); ap.add_argument("out")
    ap.add_argument("--marker", default=None)
    ap.add_argument("--anchor", default=None)
    ap.add_argument("--width-mm", type=float, default=170.0)
    a = ap.parse_args()

    px_w, px_h = png_size(a.png)
    org_w = px_w * HWPUNIT_PER_PX
    org_h = px_h * HWPUNIT_PER_PX
    disp_w = int(a.width_mm * HWPUNIT_PER_MM)
    disp_h = int(disp_w * px_h / px_w)

    work = a.out + ".unz"
    if os.path.exists(work):
        shutil.rmtree(work)
    with zipfile.ZipFile(a.base) as z:
        z.extractall(work)
        names = z.namelist()

    idx = next_image_index(names)
    img_id = "image%d" % idx
    # 1) BinData에 PNG 추가
    os.makedirs(os.path.join(work, "BinData"), exist_ok=True)
    shutil.copy(a.png, os.path.join(work, "BinData", img_id + ".PNG"))
    # 2) content.hpf manifest 등록
    hpf_path = os.path.join(work, "Contents", "content.hpf")
    hpf = open(hpf_path, encoding="utf-8").read()
    item = (f'<opf:item id="{img_id}" href="BinData/{img_id}.PNG" '
            f'media-type="image/png" isEmbeded="1"/>')
    hpf = hpf.replace("</opf:manifest>", item + "</opf:manifest>", 1)
    open(hpf_path, "w", encoding="utf-8").write(hpf)
    # 3) section0.xml에 그림 문단 배치 (마커 치환 우선 → 앵커 삽입 폴백)
    sec_path = os.path.join(work, "Contents", "section0.xml")
    sec = open(sec_path, encoding="utf-8").read()
    # 강건화: 그림 XML은 hc: 네임스페이스를 쓴다. 루트에 미선언이면(순수 generate_document 출력) 추가.
    if "xmlns:hc=" not in sec:
        sec = re.sub(r'(<[^>]*xmlns:hp="[^"]*")',
                     r'\1 xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"',
                     sec, count=1)
    taken = existing_shape_ids(sec)
    pic = build_pic_xml(img_id, org_w, org_h, disp_w, disp_h, taken)
    placed = "앵커"
    if a.marker:
        sec2, ok = replace_marker(sec, pic, a.marker)
        if ok:
            sec, placed = sec2, "마커치환(%r)" % a.marker
        else:
            print(f"  ⚠️ 마커 {a.marker!r} 미발견 → 앵커 폴백")
    if placed == "앵커":
        sec = insert_after_anchor(sec, pic, a.anchor)
        placed = "본문끝" if not a.anchor else "앵커뒤(%r)" % a.anchor
    open(sec_path, "w", encoding="utf-8").write(sec)
    # 4) 재패킹
    repack(work, a.out)
    shutil.rmtree(work)
    print(f"OK: {a.out}")
    print(f"  이미지 {img_id}.PNG ({px_w}x{px_h}px) org={org_w}x{org_h} disp={disp_w}x{disp_h} (~{a.width_mm}mm)")
    print(f"  배치={placed}")

if __name__ == "__main__":
    main()
