---
name: kca-report-orchestrator
description: "KCA 개조식 보고서를 5-에이전트 하네스(기획→작성→문체감사→렌더→산출물QA)로 조율해 최종 HWPX까지 생산하는 오케스트레이터. 'KCA 보고서 써줘', '개조식으로 정리', '추진배경/추진내용/향후계획으로 문서화', '이 초안 보고서체로 변환', '공문서/계획서 hwpx로 만들어', '전략보고서', '하네스로 보고서 작성' 요청 시 사용. **파일을 드래그·첨부하며 '이 자료로/참고해서 보고서' 요청 시에도 사용**(자료→조사→보고서가 기본 동선 — 제공 파일은 claudian vault에 INGEST-lite 적재, 위키 사전지식·신규 조사는 claudian-research). 산출물은 요청건별로 claudian vault reports/{날짜}_{건명}/에 누적, 최종본은 그 안의 final/. 후속 작업도 처리 — '표만 다시', '향후계획 보완', '문체만 재검수', 'HWPX만 다시 뽑아', '이전 결과 개선', '재실행'. 짧은 1페이지 보고서는 기존 kca-report-style 단일 스킬로 위임."
---

# KCA 보고서 하네스 오케스트레이터

개조식 보고서를 **작성·검증·렌더링을 분리한 에이전트 팀**으로 생산한다. 단일 주체가 다 하던 기존 방식의 자기검증 편향·원인 격리 실패를 제거하고, 부분 재실행을 가능케 한다.

**팀(5):** kca-planner(기획·자료) → kca-writer(작성) ⇄ kca-style-auditor(문체 감사) → kca-builder(HWPX, 자가 검증 포함) → (조건부) kca-hwpx-qa(산출물 QA). `⇄`는 생성-검증 반려 루프.

**아키텍처:** 파이프라인 + 생성-검증 하이브리드. **검증의 기계화 원칙**: 결정론 판정이 가능한 검증(문체 린트 기계 항목·HWPX 구조 검증)은 스크립트(`lint_report_md.py`·`validate_hwpx.py`+parse 왕복)가 수행하고, LLM 에이전트는 의미 판단에만 투입한다 — 무반려 사이클의 실측 병목이 스크립트가 아니라 opus 에이전트 호출 대기였기 때문('26.7.15 분석).

**모델 배정:** planner·writer = `opus`(창작·판단 중심) / style-auditor·builder·hwpx-qa = `sonnet`(스크립트 실행·체크리스트 판정 중심).

## 작업 폴더 규약 — claudian vault `reports/` (요청건별 누적)

- **VAULT** = `/Users/bcchung81/workspace/claudian` (지식·자료·보고서가 복리 축적되는 콘텐츠 저장소). 이 저장소(report-harness)는 엔진만 — **작업 산출물을 여기 쓰지 않는다** (기존 `_workspace/` 방식 폐지).
- **REPORT_DIR** = `VAULT/reports/{YYMMDD}_{건명슬러그}/` — 요청건마다 새 폴더. 산출물: `00_context.md`~`05_qa_report.md`·`table_widths.json`·`03_body.hwpx`·`input/`(참조 목록만, 원본은 vault raw/) + **`final/{보고서제목}.hwpx`(최종본 — 반드시 이 안에 산출, 저장소 루트·외부 경로 금지)**.
- 각 에이전트 호출 시 REPORT_DIR 절대경로를 프롬프트에 명시해 전달한다.

## Phase 0: 컨텍스트 확인 + 라우팅

1. **규모 라우팅 (이중 트랙):**
   - **짧은 1페이지·단순 보고서** → 하네스는 과설계. 기존 `kca-report-style` 단일 스킬로 위임하고 종료. (팀 조율 오버헤드 > 이득)
   - **다면·전략·대규모 보고서**(추진배경/내용/향후계획 다수 섹션, 표·근거 수집 필요, 전략 종합보고서) → 하네스 전체 실행.
   판단이 애매하면 사용자에게 규모를 확인한다.
2. **실행 모드 결정:**
   - 기본값 = **서브에이전트 파이프라인** (Agent 도구 직접 호출). 실험 플래그 불필요, 어디서나 동작.
   - `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`이 켜져 있고 사용자가 실시간 협업을 원하면 → 에이전트 팀 모드(TeamCreate+SendMessage+TaskCreate).
3. **재실행 판별** (`VAULT/reports/` 확인):
   - 새 주제 → **새 실행**: `reports/{오늘YYMMDD}_{건명슬러그}/` 폴더 생성 후 Phase 1부터. 기존 폴더는 그대로 둔다(밀려나는 백업 없음 — 건별 누적).
   - 부분 수정 요청 → **부분 재실행**: 대상 폴더 = 사용자가 건명을 지정하면 해당 폴더, 아니면 날짜 프리픽스 최신 폴더. 해당 에이전트만 재호출(아래 매트릭스).
4. **자료 입력 수집 (자료조사·자료제공이 출발점)**: 사용자가 프롬프트에 **드래그·첨부한 파일 경로**를 식별해 `claudian-research` 스킬 **모드 C(INGEST-lite)** 로 vault에 적재한다 — 원본을 `VAULT/raw/`로 복사(불변 보존·덮어쓰기 금지), 바이너리는 kordoc 파싱해 `VAULT/acquired/parsed/{원본명}/`에 추출, 위키 컴파일은 `[PENDING]`. `00_context.md`의 **"제공 자료"** 절에 원경로·raw 경로·parsed 경로를 기록(REPORT_DIR 안에 사본을 두지 않음 — vault가 단일 원천, 다음 보고서가 재사용). 제공 자료가 없으면 "없음 — 위키·신규 조사로 진행"을 기록.
5. **생성 전 Q&A 게이트 (1단계)**: 하네스 실행이 확정되면 AskUserQuestion **1회**로 다음을 묻고 `{REPORT_DIR}/00_context.md`에 기록한다:
   - **보고 대상** (택1): 임원 / 경영진 / 부서장·실무 — `kca-report-layout` §9 프로파일이 분량·용어·관점·표 상세도를 결정. "Other"로 직접 지정 가능.
   - **자료 구성 방향** (택1): 표 중심(총괄표·비교표 적극) / 서술 중심(표 최소) / LLM 판단 위임.
   부분 재실행 시 기존 `00_context.md`를 재사용하고 다시 묻지 않는다. `00_context.md`가 없으면 기본값을 가정하지 말고 되묻는다.

**부분 재실행 매트릭스** (writer 재호출은 전면 재작성이 아니라 **기존 draft를 Edit로 패치** — 수정 범위를 프롬프트에 명시하고, auditor는 diff만 재감사):
| 요청 | 재호출 에이전트 | 재사용 산출물 |
|------|----------------|---------------|
| "표만 다시" / "향후계획 보완" | writer(패치) → style-auditor(diff) → builder | 01 outline + 02 draft |
| "문체만 재검수" | style-auditor (→ 반려 시 writer 패치) | 02 draft |
| "HWPX만 다시 뽑아" / "폰트 틀어졌어" | builder(자가 검증 포함) | 02 draft |
| "근거·수치 보강" | planner → writer(패치) → … | 02 draft |
| "대상 바꿔서 다시" (보고 대상 변경) | writer(재작성) → style-auditor → builder | 01 outline (00_context.md만 갱신) |

## Phase 1: 기획·자료 (kca-planner)

`Agent(subagent_type 기반, model:"opus")`로 planner 호출. 주제/초안 + `00_context.md`(보고 대상·구성 방향·**제공 자료 목록**) + `{REPORT_DIR}/input/` 경로 전달. planner는 **3단 소스 우선순위**로 근거를 수집한다 — ①사용자 제공 자료(`input/`, kordoc 파싱) → ②claudian 위키 사전지식(`claudian-research` 모드 A — 관련 페이지 인용) → ③신규 조사(`claudian-research` 모드 B — vault 적재로 복리 축적). 산출물 `{REPORT_DIR}/01_planner_outline.md`.

planner 산출물에는 **"집필 스토리보드"(□별 ㅇ후보 메시지 1줄·형식·재료)와 "표·부연자료 구상" 섹션이 반드시 포함**되어야 한다(누락 시 planner 재호출).

**Phase 1 종료 = 스토리보드 승인 게이트 (사전고지·2단계 Q&A)** — 초안을 쓰기 **전에** "어떤 내용을 쓸지, 무엇을 표로 만들지"를 사용자에게 고지하고 승인받는다(방향 수정을 opus writer 재작성이 아니라 계획 편집으로 소화 — 실측 병목이 opus 대기였으므로 이것이 핵심 속도 장치). AskUserQuestion **1회**로 묶어 확인:
- **스토리보드 사전고지**: □별 ㅇ후보(핵심 메시지 1줄)와 형식(서술/표/도해)을 요약 제시 → 승인 / 섹션별 수정 지시("Other"로 자유 지시). 수정이 경미하면 오케스트레이터가 outline의 스토리보드를 직접 Edit, 방향이 크게 바뀌면 planner 해당 섹션만 재호출 → 재고지.
- planner가 반환한 **미확정·플레이스홀더 목록**(핵심 수치가 비면 여기서 되묻기)
- **표·부연자료 후보 채택**(multiSelect): 총괄표·비교표·부연자료 후보(유형·묶는 조사항목·본문/붙임 배치·기대 효과)를 후보별로 채택/제외. 1단계에서 "서술 중심"을 선택했어도 표가 명백히 유리한 항목은 후보로 제시할 수 있다(채택은 사용자 몫).
- **초안 검토 게이트(Phase 2.5) 실행 여부**: 실행(기본) / 생략(스토리보드 승인으로 충분하니 바로 최종까지).

승인된 스토리보드를 outline에 확정 반영한 뒤 Phase 2로 진행한다. **승인본은 writer의 계약이다** — writer는 승인된 ㅇ후보·형식 밖으로 벗어나지 못하고, auditor가 L25(스토리보드 정합)로 검증한다.

## Phase 2: 작성 ⇄ 문체 감사 (생성-검증 루프)

1. `Agent(kca-writer, model:"opus")` → `02_writer_draft.md`. writer는 제출 전 `lint_report_md.py`를 **자가 실행해 기계 위반 0건(exit 0)을 만든 뒤** 제출한다(결정론 스크립트라 자기검증 편향 없음 — 기계적 반려 왕복 제거).
2. `Agent(kca-style-auditor, model:"sonnet")` → `03_auditor_report.md`. auditor는 기계 린트를 재실행해 결과를 싣고, **의미 판단(L10 날조·L14 통합·L20 표 전환·L21 프로파일·30초 테스트·L22 품질·L25 스토리보드 정합)에 집중**한다.
3. `판정: 반려`면 writer 재호출(지적 항목만 Edit로 수정) → 재감사는 **diff만**(지적 항목 해소 + 수정 부위 새 위반). **최대 3회**, 이후 사용자 에스컬레이션(무한 루프 방지).
4. `판정: 통과`면 Phase 2.5(스토리보드 승인 시 "생략"을 선택했으면 바로 Phase 3).

## Phase 2.5: 초안 검토 게이트 (사용자 의견 수렴 — 빌드 전)

HWPX 빌드는 가장 비싼 단계이므로 **내용 확정 전에 빌드하지 않는다.** auditor 통과 직후 초안을 사용자에게 제시하고 피드백을 받는다. 스토리보드가 이미 승인됐으므로 이 게이트는 방향 교정이 아니라 **표현·세부 확인** 성격 — 기본 1라운드 통과를 기대한다.

1. **제시**: □ 표제 + 괄호리드 요약(30초 테스트와 동일 뷰) + `02_writer_draft.md` 전문 경로 → AskUserQuestion으로 승인 / 수정 지시 분기.
2. **수정 지시 라우팅** (기존 기계 재사용, 새 에이전트 없음):
   | 피드백 유형 | 라우팅 |
   |------------|--------|
   | 강화(근거·수치 보강) | planner 증분 조사(해당 항목만, 모드 B) → writer 패치 → auditor diff → 게이트 재진입 |
   | 삭제·축소 | writer 패치 → auditor diff → 재진입 (planner 생략) |
   | 추가 자료 제출(새 파일) | INGEST-lite(모드 C) → planner 증분 갱신 → writer 패치 → auditor diff → 재진입 |
   | 방향 전환(대상·구성 변경) | `00_context.md`·스토리보드 갱신 → writer 재작성 → auditor → 재진입 |
3. 라운드별 피드백을 `{REPORT_DIR}/06_feedback_round{N}.md`에 기록(무엇을 왜 바꿨는지 — 감사 추적). **상한 3라운드**, 초과 시 에스컬레이션. planner 증분 조사 결과는 vault에 적재되어 라운드가 돌수록 조사가 싸진다(복리).
4. **승인 시 Phase 3.** 스토리보드를 크게 벗어나는 피드백이면 승인된 스토리보드도 함께 갱신해 계약-이행 정합을 유지한다.

> writer와 auditor는 **반드시 다른 에이전트 호출**이어야 한다. 같은 컨텍스트가 쓰고 검증하면 자기검증 편향이 되살아난다. (기계 린트는 예외 — 결정론 스크립트는 누가 돌려도 같은 결과.)

## Phase 3: 렌더 + 자가 검증 (QA 에이전트는 조건부)

1. `Agent(kca-builder, model:"sonnet")` → `{REPORT_DIR}/04_final.hwpx` (generate_document + build_from_template.py) + **자가 검증**(validate_hwpx.py + parse_document 왕복 교차대조, 결과를 `05_qa_report.md`에 기록). 실패 시 1회 즉시 재빌드. PostToolUse 훅이 validate를 이중으로 보장.
2. **hwpx-qa 스폰 조건** (기본 경로에서는 생략): ① builder 자가 검증이 재빌드 후에도 실패, ② 참고양식 교체·수정 후 첫 빌드, ③ 원인(렌더 vs MD) 판별 불가 이슈, ④ 사용자가 독립 QA 명시 요청 → `Agent(kca-hwpx-qa, model:"sonnet")`로 독립 재검증.
3. 반려 시 원인 추정에 따라 라우팅: 렌더링 → builder 재빌드 / 문체·MD → Phase 2(writer). 최대 3회, 이후 에스컬레이션.
4. 검증 통과면 `04_final.hwpx`를 **`{REPORT_DIR}/final/{보고서제목}.hwpx`로 복사**해 확정한다. 저장소 루트·홈 등 외부 경로 산출 금지(사용자가 별도 경로를 명시한 경우에만 추가 사본).

## Phase 4: 완료 + 지식화 + 진화

1. 최종 HWPX 경로(`{REPORT_DIR}/final/…`)·QA 요약·미확정/플레이스홀더 잔여 항목을 사용자에게 보고.
2. **완성 보고서 지식화 (표준 깊이)**: `VAULT/topics/`에 보고서 위키 페이지 1장을 생성한다 — 요지·건의·핵심 수치, 인용한 위키 페이지 `[[링크]]`, 근거 소스 경로, `reports/{건}/` 경로. `VAULT/wiki/index.md`·`log.md`에 등록(직렬 단일 패스 — vault CLAUDE.md §4.1 프론트매터 준수). 이로써 **다음 보고서가 과거 보고서를 `[[페이지]]`로 인용**할 수 있다.
3. **피드백 요청 (프로세스·규칙 개선 전용)**: 내용 피드백은 Phase 2.5에서 소화됐으므로, 여기서는 하네스 자체의 개선점을 묻는다. 피드백 유형별 반영:
   - 결과 품질 → 해당 에이전트 스킬/references
   - 역할·워크플로우 → 에이전트 정의 / 이 오케스트레이터
   - 트리거 누락 → 해당 스킬 description
4. 변경 시 이 하네스의 변경 이력에 기록(날짜·변경·대상·사유).

## 데이터 전달 프로토콜

- **파일 기반**(주): `{REPORT_DIR}/{순번}_{에이전트}_{산출물}` — 01_planner_outline.md(집필 스토리보드 포함) · 02_writer_draft.md · 03_auditor_report.md · 04_final.hwpx · 05_qa_report.md · 06_feedback_round{N}.md(Phase 2.5 라운드별). 중간 산출물 보존(부분 재실행·감사 추적).
- **반환값 기반**(서브 모드): 각 Agent 호출의 판정·요약을 오케스트레이터가 수집해 다음 Phase 라우팅.
- 최종본은 `{REPORT_DIR}/final/`에, 중간 산출물은 `{REPORT_DIR}/`에 요청건별로 영구 보존(감사 추적·부분 재실행·과거 건 인용).

## 에러 핸들링

- 각 에이전트 1회 재시도, 재실패 시 해당 산출물 없이 진행하되 보고서에 누락 명시.
- 반려 루프 3회 초과 → 사용자 에스컬레이션(자동 무한 반복 금지).
- 상충 데이터(근거 소스 간 수치 불일치)는 삭제하지 않고 출처 병기.

## 테스트 시나리오

- **정상 흐름**: "2026 직원 AI 역량강화 교육계획 KCA 보고서 하네스로 써줘" → planner 골격+수요조사 수치 태깅 → writer 개조식(자가 린트 exit 0) → auditor 통과 → builder HWPX+자가 검증 통과(hwpx-qa 미스폰) → 최종 hwpx.
- **반려 흐름(문체·기계)**: writer가 "…운영합니다" 서술어 잔존 → **자가 린트 L1이 제출 전 적발** → writer 명사형 수정 후 제출 → auditor는 의미 판단만.
- **반려 흐름(문체·의미)**: outline `[확정]`에 없는 수치가 확정형으로 등장 → auditor L10 반려 → writer 패치 → diff 재감사 통과.
- **반려 흐름(렌더)**: builder가 임의 스타일ID 사용 → builder 자가 검증 validate_hwpx.py 불연속 FAIL → max(id)+1 재빌드 → 통과. 재빌드로도 실패 시 hwpx-qa 스폰.
- **레이아웃 흐름(각주·붙임)**: writer가 한 ㅇ에 `*` 2개 → auditor L13b 반려 → 1개로 축소·재감사. 붙임 반 페이지 → L15 반려 → 상세 보강.
- **도해 흐름**: writer가 `[도해: …]` 마커 배치 → builder가 정사각 SVG→qlmanage PNG→`prep_report_md.py`→generate_document→build_from_template→`inject_image.py --marker "도해"`로 마커 위치 치환 → builder 자가 검증이 각주 `＊`(charPr49)·도해 이미지 확인.
- **부분 재실행**: 기존 `{REPORT_DIR}/` 있는 상태에서 "표만 다시" → writer가 기존 draft의 표만 Edit → auditor diff 재감사 → builder 재빌드, 01 outline·02 draft 재사용.
- **표 폭 흐름**: 4열 표(1열 짧은 라벨·4열 긴 설명) → builder의 adjust_table_widths.py 후 4열이 1열보다 넓고 행 폭 합 = 표 폭, validate 통과. `[ 캡션 | 폭 2:1:1:3 ]` 지시자는 캡션에서 제거되고 비율 적용. 제목 그라데이션·붙임 라벨박스 표는 불변.
- **대상 프로파일 흐름**: Phase 0에서 임원 선택 → writer가 본문 1~2p·총괄표만 본문. writer가 상세 표를 본문에 넣으면 auditor L21 반려.
- **2단계 제안 흐름**: planner outline에 표·부연자료 구상 섹션 부재 → planner 재호출. 사용자가 후보 일부만 채택 → writer 산출물에 채택분만 반영.
- **스토리보드 사전고지 흐름**: Phase 1 종료 게이트에서 "□ 추진내용의 2번째 ㅇ후보를 표로" 수정 지시 → 오케스트레이터가 outline 스토리보드의 형식만 Edit(planner·writer 재호출 없음) → 재고지·승인 → writer가 승인본대로 작성. writer가 승인 안 된 ㅇ를 추가하면 auditor L25 반려.
- **초안 검토 흐름(Phase 2.5)**: auditor 통과 후 사용자가 "붙임2 근거 더 보강" → 강화 라우팅: planner 증분 조사(해당 항목만) → writer 패치 → auditor diff → 게이트 재진입 → 승인 → 빌드. 피드백은 06_feedback_round1.md에 기록.
- **자료 제공 흐름**: 사용자가 hwpx·pdf를 드래그하며 "이 자료로 보고서" → Phase 0이 claudian-research 모드 C로 vault raw/ 복사 + parsed 추출·00_context 기록 → planner가 parsed 추출본을 `[확정]`(사용자 제공) 태깅 → 부족 근거만 위키·신규 조사.
- **표 렌더 흐름(높이)**: 원본 셀 높이가 협폭 열 기준으로 과대 산정된 표 → adjust_table_widths.py가 폭 재분배와 함께 행 높이 재계산 → 표가 페이지를 벗어나지 않음(빈 행 공간 제거).
- **법령 표기 흐름**: planner가 korean-law로 조문 수집 시부터 `제N조제N항` 표기 → writer 15c 준수 → 위반(`§45③` 등)은 자가 린트 L24가 제출 전 적발.
- **위키 인용 흐름**: 주제가 claudian 위키 사전지식(예: ISO 42001·하네스 엔지니어링)과 관련 → planner가 모드 A로 페이지 인용 `(출처: claudian [[페이지]] ← 원출처)`, 원출처 미추적 주장은 `[미확정]` → 신규 조사(모드 B) 결과는 vault `acquired/fetched/`에 적재·복리.

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
| 2026-07-14 | 표 열 폭 유동 분배(adjust_table_widths.py) + 보고 대상 프로파일(layout §9·L21) + 총괄표·부연자료 2단계 Q&A | scripts·builder·layout·lint·planner·writer·auditor·오케스트레이터 | 균등 4분할 표 개선·보고자 수준 맞춤·조사내역 기반 표 구상 제안(실전 보고서 피드백) |
| 2026-07-15 | 두괄식(BLUF) 1급 규율 승격 + 원리 근거 이식 (layout §7-6, lint L22, references/one-pager-principles.md) | layout·lint·writer·auditor·style references | 1페이지 작성기법 조사(두괄식·Minto 피라미드·아마존 answer-first·A3) 정수를 규칙화 — 결론·건의 본문 선두 배치(기관장·임원 필수), 하네스의 '왜'를 실측 경험→정립 원리로 보강 |
| 2026-07-15 | 실행 시간 단축 4종 — ①기계 린트 스크립트화(lint_report_md.py, writer 자가 게이트+auditor 1차 판정기) ②builder 자가 검증으로 hwpx-qa 조건부화 ③auditor·builder·hwpx-qa sonnet 강등 ④부분 재실행 패치 단위화(writer Edit·auditor diff 재감사) | scripts·writer·auditor·builder·hwpx-qa·lint·오케스트레이터 | 실측('26.7.14 실행): 무반려 사이클 16분의 90%가 opus 에이전트 대기, 감사·QA 모두 통과 재확인에 소모 — 결정론 검증은 스크립트로, LLM은 의미 판단만 (목표: 사이클 16분→6~8분) |
| 2026-07-15 | 자료조사·자료제공 출발점 정립 — ①claudian-research 글로벌 스킬 신설(위키 QUERY + 조사 RESEARCH, vault 적재 복리) ②Phase 0 드래그 파일 수집(`{REPORT_DIR}/input/`) ③planner 3단 소스 우선순위(제공 자료→위키 사전지식→신규 조사) | 신설 스킬·planner·오케스트레이터 | 보고서 작성이 자료조사·제공으로 시작하도록 동선 고정 — 사용자 파일 최우선 `[확정]` 태깅, claudian 위키(사전지식) 관련도 있으면 원출처 병기 인용, 신규 조사는 vault에 적재해 다음 보고서에서 재사용 |
| 2026-07-15 | 본문 표 크기 규율 (layout §8 반 페이지 상한, lint L23 기계 판정 — 데이터 행≤8) | layout·lint·lint_report_md.py·planner·writer·auditor | 사용자 피드백: 원본 데이터 전량 표가 본문 반 페이지 초과 — 핵심 행 선별(+외 N건) 또는 통계 가공만 본문 허용, 전량은 붙임. planner가 후보 단계에서 가공 형태 설계, auditor는 가공 정합성(합계·이중계산)만 판단 |
| 2026-07-15 | claudian 통합 — 작업 폴더를 vault `reports/{날짜}_{건명}/`로 이전(요청건별 누적, `_workspace` 폐지), 최종본 `final/` 규약, 제공자료 INGEST-lite(모드 C), Phase 4 보고서 지식화(topics 페이지) | 오케스트레이터·에이전트 5종·claudian-research·vault CLAUDE.md | 덮어쓰기 구조 해소(직전 1건만 백업되던 문제) + 자료·지식·보고서 단일 저장소 복리 + 최종본 위치 고정(루트 유출 방지) |
| 2026-07-15 | 표 행 높이 재계산(adjust_table_widths.py) + 제외 신호 rowCnt<2 정식 흡수 + 법령 한국식 표기(layout §10·lint L24) | scripts·layout·lint·planner·writer·auditor | 실물 보고서(ICT기금 위임건의) 결함 2건: ①kordoc 협폭 열 기준 과대 셀 높이(57,882 hwpunit)로 표가 페이지 이탈 — 폭 재분배 시 높이 동반 재계산 ②`§45③`식 독일식 조문 표기 — `제45조제3항` 한국식 강제. builder가 실행 중 ~/.claude 사본에만 고친 rowCnt 신호도 repo 정식 반영(드리프트 해소) |
| 2026-07-16 | 집필 스토리보드 사전고지 게이트(Phase 1 종료 승격, dot-dash 차용) + 초안 검토 게이트(Phase 2.5) + writer 계약·auditor L25 정합 검증 | 오케스트레이터·planner·writer·auditor·style-lint·README | 사용자 피드백: 작성 후 수정이 아니라 "무엇을 쓸지·표로 만들지" 사전고지 후 진행 — 방향 수정을 opus writer 재작성이 아닌 계획 편집으로 상류 이동(외부 근거: McKinsey dot-dash/고스트덱·테크니컬 라이팅 계획 40%·공공기관 목차 사전 컨센서스). 내용 피드백은 2.5에서 소화, Phase 4는 프로세스 개선 전용으로 순화 |
