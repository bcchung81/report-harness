---
name: kca-report-orchestrator
description: "KCA 개조식 보고서를 5-에이전트 하네스(기획→작성→문체감사→렌더→산출물QA)로 조율해 최종 HWPX까지 생산하는 오케스트레이터. 'KCA 보고서 써줘', '개조식으로 정리', '추진배경/추진내용/향후계획으로 문서화', '이 초안 보고서체로 변환', '공문서/계획서 hwpx로 만들어', '전략보고서', '하네스로 보고서 작성' 요청 시 사용. 후속 작업도 처리 — '표만 다시', '향후계획 보완', '문체만 재검수', 'HWPX만 다시 뽑아', '이전 결과 개선', '재실행'. 짧은 1페이지 보고서는 기존 kca-report-style 단일 스킬로 위임."
---

# KCA 보고서 하네스 오케스트레이터

개조식 보고서를 **작성·검증·렌더링을 분리한 에이전트 팀**으로 생산한다. 단일 주체가 다 하던 기존 방식의 자기검증 편향·원인 격리 실패를 제거하고, 부분 재실행을 가능케 한다.

**팀(5):** kca-planner(기획·자료) → kca-writer(작성) ⇄ kca-style-auditor(문체 감사) → kca-builder(HWPX) ⇄ kca-hwpx-qa(산출물 QA). `⇄`는 생성-검증 반려 루프.

**아키텍처:** 파이프라인 + 생성-검증 하이브리드.

## Phase 0: 컨텍스트 확인 + 라우팅

1. **규모 라우팅 (이중 트랙):**
   - **짧은 1페이지·단순 보고서** → 하네스는 과설계. 기존 `kca-report-style` 단일 스킬로 위임하고 종료. (팀 조율 오버헤드 > 이득)
   - **다면·전략·대규모 보고서**(추진배경/내용/향후계획 다수 섹션, 표·근거 수집 필요, 전략 종합보고서) → 하네스 전체 실행.
   판단이 애매하면 사용자에게 규모를 확인한다.
2. **실행 모드 결정:**
   - 기본값 = **서브에이전트 파이프라인** (Agent 도구 직접 호출). 실험 플래그 불필요, 어디서나 동작.
   - `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`이 켜져 있고 사용자가 실시간 협업을 원하면 → 에이전트 팀 모드(TeamCreate+SendMessage+TaskCreate).
3. **재실행 판별** (`_workspace/` 확인):
   - `_workspace/` 없음 → **초기 실행** (Phase 1부터)
   - `_workspace/` 있음 + 부분 수정 요청 → **부분 재실행** (해당 에이전트만 재호출, 아래 매트릭스)
   - `_workspace/` 있음 + 새 입력 → **새 실행** (기존을 `_workspace_prev/`로 이동)

**부분 재실행 매트릭스:**
| 요청 | 재호출 에이전트 | 재사용 산출물 |
|------|----------------|---------------|
| "표만 다시" / "향후계획 보완" | writer → style-auditor → builder → hwpx-qa | 01 outline |
| "문체만 재검수" | style-auditor (→ 반려 시 writer) | 02 draft |
| "HWPX만 다시 뽑아" / "폰트 틀어졌어" | builder → hwpx-qa | 02 draft |
| "근거·수치 보강" | planner → writer → … | — |

## Phase 1: 기획·자료 (kca-planner)

`Agent(subagent_type 기반, model:"opus")`로 planner 호출. 주제/초안 + 근거 소스 지정 전달. 산출물 `_workspace/01_planner_outline.md`. planner가 반환한 **미확정·플레이스홀더 목록**을 사용자에게 확인받는다(핵심 수치가 비면 여기서 되묻기).

## Phase 2: 작성 ⇄ 문체 감사 (생성-검증 루프)

1. `Agent(kca-writer, model:"opus")` → `02_writer_draft.md`.
2. `Agent(kca-style-auditor, model:"opus")` → `03_auditor_report.md`.
3. `판정: 반려`면 writer 재호출(지적 항목만 수정) → 재감사. **최대 3회**, 이후 사용자 에스컬레이션(무한 루프 방지).
4. `판정: 통과`면 Phase 3.

> writer와 auditor는 **반드시 다른 에이전트 호출**이어야 한다. 같은 컨텍스트가 쓰고 검증하면 자기검증 편향이 되살아난다.

## Phase 3: 렌더 ⇄ 산출물 QA (생성-검증 루프)

1. `Agent(kca-builder, model:"opus")` → `_workspace/04_final.hwpx` (generate_document + build_from_template.py).
2. `Agent(kca-hwpx-qa, model:"opus")` → `05_qa_report.md` (validate_hwpx.py + parse_document 교차검증).
3. `판정: 반려`면 qa의 **원인 추정**에 따라 라우팅:
   - 원인=렌더링 → builder 재빌드
   - 원인=문체/MD → Phase 2(writer)로 되돌림
   최대 3회, 이후 에스컬레이션.
4. `판정: 통과`면 `04_final.hwpx`를 사용자 지정 경로로 산출.

## Phase 4: 완료 + 진화

1. 최종 HWPX 경로·QA 요약·미확정/플레이스홀더 잔여 항목을 사용자에게 보고.
2. **피드백 요청**: "개선할 부분이 있나요?" 피드백 유형별 반영:
   - 결과 품질 → 해당 에이전트 스킬/references
   - 역할·워크플로우 → 에이전트 정의 / 이 오케스트레이터
   - 트리거 누락 → 해당 스킬 description
3. 변경 시 이 하네스의 변경 이력에 기록(날짜·변경·대상·사유).

## 데이터 전달 프로토콜

- **파일 기반**(주): `_workspace/{순번}_{에이전트}_{산출물}` — 01_planner_outline.md · 02_writer_draft.md · 03_auditor_report.md · 04_final.hwpx · 05_qa_report.md. 중간 산출물 보존(부분 재실행·감사 추적).
- **반환값 기반**(서브 모드): 각 Agent 호출의 판정·요약을 오케스트레이터가 수집해 다음 Phase 라우팅.
- 최종 HWPX만 사용자 경로로 출력, `_workspace/`는 보존.

## 에러 핸들링

- 각 에이전트 1회 재시도, 재실패 시 해당 산출물 없이 진행하되 보고서에 누락 명시.
- 반려 루프 3회 초과 → 사용자 에스컬레이션(자동 무한 반복 금지).
- 상충 데이터(근거 소스 간 수치 불일치)는 삭제하지 않고 출처 병기.

## 테스트 시나리오

- **정상 흐름**: "2026 직원 AI 역량강화 교육계획 KCA 보고서 하네스로 써줘" → planner 골격+수요조사 수치 태깅 → writer 개조식 → auditor 통과 → builder HWPX → qa 통과 → 최종 hwpx.
- **반려 흐름(문체)**: writer가 "…운영합니다" 서술어 잔존 → auditor L1 반려 → writer 명사형 수정 → 재감사 통과.
- **반려 흐름(렌더)**: builder가 임의 스타일ID 사용 → qa validate_hwpx.py 불연속 FAIL → builder max(id)+1 재빌드 → 통과.
- **레이아웃 흐름(각주·붙임)**: writer가 한 ㅇ에 `*` 2개 → auditor L13b 반려 → 1개로 축소·재감사. 붙임 반 페이지 → L15 반려 → 상세 보강.
- **도해 흐름**: writer가 `[도해: …]` 마커 배치 → builder가 정사각 SVG→qlmanage PNG→`prep_report_md.py`→generate_document→build_from_template→`inject_image.py --marker "도해"`로 마커 위치 치환 → qa가 각주 `＊`(charPr49)·도해 이미지 확인.
- **부분 재실행**: 기존 `_workspace/` 있는 상태에서 "표만 다시" → writer~qa만 재호출, 01 outline 재사용.

## 하네스 변경 이력

| 날짜 | 변경 | 대상 | 사유 |
|------|------|------|------|
| 2026-07-10 | 초기 구성 (kca-report-style monolith → 5-에이전트 하네스) | 전체 | 자기검증 편향 제거·원인 격리·부분 재실행 |
| 2026-07-10 | 레이아웃 규율 도입 (kca-report-layout 신설, lint L11~L14 추가) | writer·style-auditor·신설 스킬 | ㅇ 나열 과다 개선 — 본문 2p·□당 ㅇ≤3·통합·붙임·용어 각주 |
| 2026-07-10 | 툴 라우팅 고정 (법령→korean-law, 변환→kordoc) | planner·builder | 근거·변환 수단 일관성 |
| 2026-07-10 | 웹 근거 수집 교체 (WebSearch → deep-research·firecrawl·insane-search) | planner·writer·layout | 로컬 설치 스킬 활용·다출처 교차검증·차단 사이트 우회 |
| 2026-07-10 | 워크플로우 도해 파이프라인 추가 (SVG→qlmanage PNG→inject_image.py 주입) | builder·layout·scripts | HWPX에 흐름도 이미지 삽입 — PoC 검증 완료(validate+parse 통과) |
| 2026-07-10 | 각주·붙임 규칙 강화 (ㅇ당 `*`≤1+`※`≤1, 붙임 최소 1페이지, L13b·L15 추가) | layout·style-lint·auditor | 각주 과다 방지·우선순위 표기·붙임 앙상함 방지 |
| 2026-07-10 | 하네스 엔지니어링 감사 반영 (8건) | 전체·scripts | ①트리거충돌 해소(kca-report-style 축소) ②각주 결정론화(prep_report_md.py) ③도해 마커치환 정확배치 ④inject id 결정론+충돌검사 ⑤postprocess 폴백 동기화 ⑥SSOT 중복정리 ⑦프로세스 지표 기록 ⑧테스트 시나리오·전역예외 |
| 2026-07-13 | 글 품질 규율 도입 (layout §7, L16~L18) | layout·lint·planner·writer·auditor | gold 대비 실측 갭 해소 — 향후계획 일정 필수·구체성 예산(수치밀도 gold 42%)·중복 상한("부분 재실행" 8회)·리듬 다양화·30초 테스트 |
| 2026-07-13 | HWPX 검증 훅 추가 (PostToolUse:Bash) | settings·hooks | 결정론적 안전망 — hwpx-qa가 건너뛰어도 validate_hwpx 무조건 실행 |
| 2026-07-13 | build_from_template 내용손실 버그 수정 | scripts | 마커 없는 문단(「붙임 N.」 헤딩 등)을 조용히 드롭하던 것 → 붙임=□·기타 텍스트=ㅇ로 보존(실전 보고서 생산 중 발견·수정) |
