#!/usr/bin/env python3
"""개조식 MD를 HWPX 변환 직전에 결정론적으로 전처리한다.

generate_document(kordoc) 호출 '전에' 반드시 실행. 에이전트가 정규식을 기억할
필요 없이 스크립트가 강제한다(각주 렌더 취약 커플링 제거).

처리:
  1) 각주 정의 줄 선두 `* ` → 전각 `＊ `  — `*`는 MD 불릿이라 generate_document가
     `□`(섹션 표제)로 오매핑한다. `＊`는 plain 문단으로 살아남고 build_from_template/
     postprocess의 classify가 ※와 동일 각주 스타일(맑은고딕12·charPr49)로 재지정한다.
     본문 내 `단어*` 인라인 표시는 건드리지 않는다(정의 줄만).
  2) 워크플로우 도해 마커 `[도해: …]`는 '그대로 둔다' — inject_image.py --marker "도해"가
     그 문단을 그림으로 치환해 마커 위치에 정확히 배치한다.
  3) 표 폭 지시자 `[ 캡션 | 폭 2:1:1:3 ]` → 캡션에서 지시자를 제거해 `[ 캡션 ]`으로
     정리하고, {표순번: [비율]}을 사이드카 JSON(3번째 인자)으로 추출한다.
     adjust_table_widths.py --widths가 이 JSON을 읽어 해당 표에 비율을 적용한다.

사용: python3 prep_report_md.py <in.md> <out.md> [<widths.json>]
"""
import sys, re, json

def prep(md):
    # 각주 정의 줄: 선두 `* 용어: 정의` → `＊ 용어: 정의` (뒤에 "…: " 콜론 있는 줄만)
    md = re.sub(r'(?m)^\* (?=.+?: )', '＊ ', md)
    return md

_DIRECTIVE = re.compile(r'^\[\s*([^|\]]+?)\s*\|\s*폭\s*([^|\]]+?)\s*\]\s*$')

def extract_widths(md):
    """[ 캡션 | 폭 2:1:1:3 ] 지시자를 캡션에서 제거하고 {표순번: [비율]}을 수집.
    표 순번은 GFM 표(| 로 시작하는 연속 블록) 등장 순서, 0-based.
    비율 형식 오류면 지시자만 버리고 캡션은 정리한다(빌드 중단 없음)."""
    lines, widths = [], {}
    pending, tbl_idx, in_tbl = None, -1, False
    for ln in md.split("\n"):
        m = _DIRECTIVE.match(ln)
        if m:
            try:
                pending = [float(x) for x in m.group(2).split(":")]
            except ValueError:
                pending = None                      # 비율 형식 오류 → 지시자 무시
            lines.append(f"[ {m.group(1)} ]")
            continue
        is_tbl = ln.lstrip().startswith("|")
        if is_tbl and not in_tbl:
            tbl_idx += 1
            if pending:
                widths[tbl_idx] = pending
                pending = None
        in_tbl = is_tbl
        lines.append(ln)
    return "\n".join(lines), widths

def main():
    if len(sys.argv) not in (3, 4):
        sys.exit("usage: prep_report_md.py <in.md> <out.md> [<widths.json>]")
    src, dst = sys.argv[1], sys.argv[2]
    md = open(src, encoding="utf-8").read()
    n_before = len(re.findall(r'(?m)^\* (?=.+?: )', md))
    out, widths = extract_widths(prep(md))
    open(dst, "w", encoding="utf-8").write(out)
    n_marker = len(re.findall(r'\[도해:', out))
    print(f"OK: {dst}")
    print(f"  각주 정의 ＊ 치환: {n_before}건 / 도해 마커 보존: {n_marker}건")
    if len(sys.argv) == 4 and widths:
        json.dump({str(k): v for k, v in widths.items()},
                  open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False)
        print(f"  표 폭 지시자: {len(widths)}건 → {sys.argv[3]}")
    elif widths:
        print(f"  ⚠️  표 폭 지시자 {len(widths)}건 발견했으나 widths.json 경로 미지정 — 무시됨")

if __name__ == "__main__":
    main()
