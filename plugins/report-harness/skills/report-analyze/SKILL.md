---
name: report-analyze
description: "보고서 자료분석 — 제공자료·조사 산출물 종합 분석 (report-pipeline ②단계)"
---

# report-analyze — ② 자료분석 단계 입구

> 부르는 법 — Claude Code `/report-analyze [건명]` · Codex `$report-analyze [건명]`. 말로 "이 자료 분석해줘"도 같다.

같은 플러그인의 `report-pipeline` 스킬(이 SKILL.md가 있는 폴더의 형제 `../report-pipeline/SKILL.md`)을 읽고
**② analyze 단계**를 실행하라. §0 공통 준비부터 한다.

- 인자: `$ARGUMENTS` — 건명·주제로 쓴다(비었거나 치환되지 않은 자리표시자로 보이면 — Codex는 치환하지 않는다 —
  사용자가 스킬 이름 뒤에 쓴 말을 인자로 본다).
- 작업폴더에 `research/`가 있으면 활용하고, 없으면 "조사 없이 진행할까요?"만 묻는다.
- 입력은 제공자료(`research/provided/`) + 조사 결과(`research/fetched/`) + 기존 초안(고도화 시 `20_draft.md`),
  산출은 `05_analysis.md` — 논지 후보·총괄표 후보·근거 공백 목록을 정리한다.
