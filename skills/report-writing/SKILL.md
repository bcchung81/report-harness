---
name: report-writing
description: "공공·기관 보고서를 잘 쓰는 설계 지침 — 목적·결재자 결정·예상 결론·상황 전제를 먼저 정하고(context), 제목=결론·피라미드·절별 So What·구성요소 대조로 세우고(outline), 흔한 실수 점검표로 초안을 감사한다(draft). '보고서 잘 쓰는 법'·'보고서 설계 점검해줘'·'이 아웃라인 괜찮아?'·'초안 논리 점검' 같은 요청에 사용한다. report-pipeline은 각 단계에서 같은 지침을 자동으로 따른다."
---

# report-writing — 보고서 설계 지침

지침 본문은 한 곳에만 있다: **`$SKILL_DIR/../report-pipeline/references/report-craft.md`** (단일 출처 — 이 스킬은
그 문서를 읽고 따르게 하는 입구다). 문서가 없으면 report-pipeline이 설치되지 않은 것이니 그 사실을 알리고 멈춘다.

## 쓰는 법

1. `report-craft.md`를 읽는다. 문장 규칙이 필요하면 같은 폴더의 `style-guide.md`도 읽는다 — 둘이 부딪히면
   기관 규정(`style-guide.md`)이 이긴다.
2. 요청에 맞는 절만 적용한다.

| 요청 | 적용 | 산출 |
|---|---|---|
| 보고서를 새로 설계한다 | §1 → §2 | `## 보고 설계` 블록, `## 설계 점검` 블록 |
| 아웃라인·목차를 점검한다 | §2 | 빠진 칸·약한 So What·겹치는 근거를 짚는다 |
| 초안 논리를 점검한다 | §3 점검표 | 걸린 항목만 주소(□N-ㅇM)와 함께 |

3. 판단이 갈리는 지점은 정하지 말고 선택지로 묻는다(§4).
4. report-pipeline 작업폴더에서 쓰는 중이면 칸 검사를 돌린다:

   ```
   python3 "$SKILL_DIR/../report-pipeline/scripts/check_craft.py" context {work_dir}
   python3 "$SKILL_DIR/../report-pipeline/scripts/check_craft.py" outline {work_dir}
   ```

   exit 1이면 JSON `missing`의 칸을 채운다. 칸의 존재만 보는 검사다 — 내용이 좋은지는 사용자가 본다.
