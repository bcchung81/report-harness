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

사용: python3 prep_report_md.py <in.md> <out.md>
"""
import sys, re

def prep(md):
    # 각주 정의 줄: 선두 `* 용어: 정의` → `＊ 용어: 정의` (뒤에 "…: " 콜론 있는 줄만)
    md = re.sub(r'(?m)^\* (?=.+?: )', '＊ ', md)
    return md

def main():
    if len(sys.argv) != 3:
        sys.exit("usage: prep_report_md.py <in.md> <out.md>")
    src, dst = sys.argv[1], sys.argv[2]
    md = open(src, encoding="utf-8").read()
    n_before = len(re.findall(r'(?m)^\* (?=.+?: )', md))
    out = prep(md)
    open(dst, "w", encoding="utf-8").write(out)
    n_marker = len(re.findall(r'\[도해:', out))
    print(f"OK: {dst}")
    print(f"  각주 정의 ＊ 치환: {n_before}건 / 도해 마커 보존: {n_marker}건")

if __name__ == "__main__":
    main()
