---
name: claudian-research
description: "claudian 지식 vault(/Users/bcchung81/workspace/claudian)를 어느 디렉토리에서든 사용하는 글로벌 자료조사·위키 참조 스킬. ①위키 사전지식 참조(QUERY) — 보고서·조사 주제와 관련된 기존 위키 페이지를 찾아 원출처와 함께 인용, ②신규 조사(RESEARCH) — 병렬 팬아웃 조사 후 vault acquired/에 적재해 지식을 복리 축적. KCA 보고서 하네스의 kca-planner가 근거 수집 시 사용. 트리거 — '자료조사', '조사해줘', '리서치해서 보고서', '위키 참고해서', '사전지식 인용', 'claudian 조사'."
---

# claudian-research — 글로벌 자료조사·위키 참조

claudian vault(Obsidian LLM Wiki)를 **작업 디렉토리와 무관하게** 조사 인프라로 쓴다. 조사 결과는 vault에 적재되어 다음 보고서에서 재사용된다(복리 원칙).

**VAULT** = `/Users/bcchung81/workspace/claudian` (이하 절대경로 사용 — cwd가 어디든 동작)

## 0. 스키마 먼저 (필수)

작업 전 `VAULT/CLAUDE.md`를 읽는다 — vault의 3-레이어 규칙·적재 규칙(§2.1)·프론트매터(§4.8)·도구 자율 선택(§5.1)의 SSOT다. 이 스킬은 그 스키마를 외부 cwd에서 실행하는 어댑터이며, 규칙을 재정의하지 않는다. 특히:
- `VAULT/raw/`(사람 원본)는 **읽기·인용만** — 절대 수정·삭제 금지.
- LLM 적재는 `VAULT/acquired/fetched/{주제-슬러그}/`에만, §4.8 출처 프론트매터 + `_manifest.jsonl` 필수. 출처 불명 자료는 적재하지 않는다.
- 저작권 위험 자료는 요약·인용만(§2.1).

## 모드 A — 위키 사전지식 참조 (QUERY)

보고서·조사 주제가 주어지면 **신규 조사 전에 vault를 먼저 검색**한다(이미 컴파일된 지식을 다시 조사하는 낭비 방지):

1. `VAULT/wiki/index.md`를 읽고 주제 관련 페이지를 선별한다. 필요 시 `VAULT/concepts/`·`entities/`·`topics/`를 키워드 Grep으로 보강.
2. 관련 페이지를 읽고 **사실·수치·개념을 원출처와 함께** 뽑는다 — 위키 페이지 하단 `## 출처`의 원본 경로·URL을 반드시 병기한다.
3. **인용 형식**: `(출처: claudian [[페이지명]] ← {원출처 URL 또는 raw 경로})`.
4. **신뢰 태깅 규칙** (kca-planner 연동): 위키 주장이 검증 가능한 원출처(공식 문서·원문 경로)를 인용하면 `[확정]`, 위키에만 있고 원출처 추적이 안 되면 `[미확정]`으로 태깅한다. 위키는 파생 사본이다 — 수치가 의심되면 `VAULT/raw/`·`acquired/` 원본을 직접 열어 대조한다.

## 모드 B — 신규 조사 (RESEARCH)

위키에 없는 근거는 `VAULT/.claude/commands/research.md`의 워크플로우를 따라 조사한다. 요지:

1. **분해·병렬**: 주제를 상호 독립 단위로 분해, 2개 이상이면 한 메시지에서 여러 `Agent`로 팬아웃(각자 다른 `acquired/fetched/{단위}/` 폴더 → 병렬 쓰기 안전). 의존적·단일 주제는 직렬.
2. **도구 자율 선택** (CLAUDE.md §5.1): 다출처 심층 → `deep-research` / 차단 사이트 → `insane-search` / 법령·판례 → MCP `korean-law` / 공시·재무 → `opendart` / 한글 문서 파싱 → `kordoc` / 라이브러리 문서 → `Context7` / YouTube → `youtube-transcript`. 핵심 주장은 ≥2개 독립 출처 교차검증.
3. **적재**: 원문·클리핑을 `VAULT/acquired/fetched/{주제-슬러그}/`에 §4.8 프론트매터로 저장 + `_manifest.jsonl` append.
4. **장부 (기본 = 적재까지, 컴파일 보류)**: `VAULT/wiki/log.md`에 `[RESEARCH-PENDING] {주제} → acquired/fetched/{폴더} (컴파일 대기)` 한 줄을 append한다(직렬). **위키 컴파일(§5 4~5단계)은 기본 보류** — 보고서 생산 경로의 시간을 지키기 위해서다. 사용자가 "위키까지 컴파일"을 요청하거나 claudian vault 세션에서 후속 처리한다.
5. 조사 산출물 반환: ① 핵심 요점(신뢰 태깅 포함) ② 적재 경로 ③ 출처 목록(url·title·tool).

## 모드 C — 제공자료 적재 (INGEST-lite)

사용자가 드래그·지정한 파일을 vault 정식 동선으로 적재한다(보고서 생산 속도를 위해 위키 컴파일은 보류):

1. **원본 보존**: 파일을 `VAULT/raw/`로 복사한다 — 같은 이름이 이미 있으면 **덮어쓰지 말고** 파일명에 날짜를 붙여 새로 둔다(§2.1 파괴 금지).
2. **추출**: 바이너리(hwp·hwpx·pdf·docx)는 kordoc(`parse_document`, 표는 `parse_table`)로 파싱해 `VAULT/acquired/parsed/{원본명}/{원본명}.md`에 저장(§4.8 변형 프론트매터 — `source_url`=raw 로컬경로, `fetched_by`="kordoc"). md·txt는 이 단계 생략.
3. **장부**: `VAULT/wiki/log.md`에 `[INGEST-PENDING] {원본명} → acquired/parsed/{…} (위키 컴파일 대기)` append. 전체 INGEST(위키 페이지화·이미지 자산화)는 claudian 세션에서 후속 처리.
4. 반환: raw 경로·parsed 경로 목록 (호출자가 `00_context.md` "제공 자료" 절에 기록).

## KCA 보고서 하네스 연동

`kca-planner`가 근거 수집 시 이 스킬을 사용한다. 순서: **모드 C 적재분(제공 자료 parsed 추출본) → 모드 A(위키 사전지식) → 모드 B(신규 조사)**. 수집 근거 로그에는 세 경로 모두 출처를 남긴다 — 위키 인용은 위 인용 형식, 신규 조사는 적재 경로 + 원 URL. 하네스 작업 폴더는 `VAULT/reports/{날짜}_{건명}/`(오케스트레이터 규약)이며, 이 스킬은 그 폴더가 아니라 **vault의 raw/acquired/wiki 레이어**에만 쓴다.

## 금지

- `VAULT/raw/` 수정·삭제, 출처 프론트매터 없는 적재, 출처 불명 자료 적재.
- `wiki/index.md`·기존 위키 페이지의 병렬 수정(장부는 단일 패스 직렬 — 경합 방지).
- 위키 주장을 원출처 확인 없이 `[확정]`으로 승격.
