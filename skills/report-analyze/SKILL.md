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
- 입력·산출은 report-pipeline SKILL **② analyze 절**을 그대로 따른다 — 여기서 경로·절 목록을 따로 적지 않는다
  (이중 서술은 낡는다: '26.11.14 검토에서 옛 `research/provided/`·3절 서술이 남아 있었다. 현행은 `research/`의
  `{시각}_제공-…` 평면 파일, 산출 `05_analysis.md` 네 절 — 논지 후보·총괄표 후보·근거 공백·인용 재료 목록(R092)).
