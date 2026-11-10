---
name: report-export
description: "보고서 hwpx 변환 — 팩트체크 ∥ 검증 → 최종 문서 생성 (report-pipeline ④단계)"
---

# report-export — ④ hwpx 변환 단계 입구

> 부르는 법 — Claude Code `/report-export [건명]` · Codex `$report-export [건명]`. 말로 "hwpx로 변환해줘"도 같다.

같은 플러그인의 `report-pipeline` 스킬(이 SKILL.md가 있는 폴더의 형제 `../report-pipeline/SKILL.md`)을 읽고
**④ export 단계**를 실행하라. §0 공통 준비부터 한다.

- 인자: `$ARGUMENTS` — 어느 건인지(건명·슬러그 일부·경로)로 쓴다(비었거나 치환되지 않은 자리표시자로 보이면 — Codex는
  치환하지 않는다 — 사용자가 스킬 이름 뒤에 쓴 말을 인자로 본다). 없으면 가장 최근 작업폴더다.
- 게이트② 승인된 `20_draft.md`가 필수다. 없으면 "초안이 없습니다. 먼저 draft를 실행하세요."라고 알린다.
- 팩트체크(전수/경량/생략) ∥ 회귀검사를 병렬로 돌린 뒤 `references/hwpx-recipe.md` 절차로 변환한다(prep 정규화 → kordoc
  생성 → 이미지 규격 판정 → **양식 정합 후처리 `postprocess_hwpx.py --all`** → 검증). 산출은 `final/{제목}.hwpx` +
  `40_qa.md`. 팩트체크 선택이 게이트②에서 정해졌으면 그 값을 따른다.
