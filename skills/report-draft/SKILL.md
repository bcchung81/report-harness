---
name: report-draft
description: "보고서 초안작성 — Q&A 게이트⓪ → 아웃라인 게이트① → 초안 게이트② (report-pipeline ③단계)"
---

# report-draft — ③ 초안작성 단계 입구

> 부르는 법 — Claude Code `/report-draft [건명]` · Codex `$report-draft [건명]`. 말로 "초안 만들어줘"도 같다.

같은 플러그인의 `report-pipeline` 스킬(이 SKILL.md가 있는 폴더의 형제 `../report-pipeline/SKILL.md`)을 읽고
**③ draft 단계**를 실행하라. §0 공통 준비부터 한다.

- 인자: `$ARGUMENTS` — 건명·주제로 쓴다(비었거나 치환되지 않은 자리표시자로 보이면 — Codex는 치환하지 않는다 —
  사용자가 스킬 이름 뒤에 쓴 말을 인자로 본다).
- 작업폴더에 `05_analysis.md`와 `research/`가 있으면 활용하고, 없으면 "조사·분석 없이 진행할까요?"만 묻는다.
- 이 단계는 게이트 3개(⓪ Q&A → ① 아웃라인 승인 → ② 초안 승인 + 팩트체크)를 포함한다. 산출은 `10_outline.md`(목차·
  논지·근거·표·도식 설계) + `20_draft.md`(최종 초안)이다.
