---
description: "보고서 hwpx 변환 — 팩트체크 ∥ 검증 → 최종 문서 생성 (report-pipeline ④단계)"
---

report-pipeline 스킬을 로드하고 **④ export 단계**를 실행하라. 게이트② 승인된 `20_draft.md` 파일이 필수이며, 없으면 "초안이 없습니다. 먼저 draft를 실행하세요."라고 알린다. 팩트체크(전수/경량/생략 선택) ∥ 회귀검사를 병렬 실행 후, hwpx-recipe 절차로 변환한다(prep 정규화→kordoc 생성→이미지 규격 판정→**양식 정합 후처리 `postprocess_hwpx.py --all`**→검증). 산출은 `final/{제목}.hwpx` + `40_qa.md`이다. 팩트체크 선택사항이 게이트②에서 결정되었으면 그 값을 따른다.
