# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

문서·주석·커밋 메시지는 한국어로 쓴다(저장소 전체가 그렇다).

## 이 저장소가 무엇인가

기관보고서(개조식·hwpx)를 **조사 → 분석 → 초안 → 변환** 4단계로 만드는 Claude Code 플러그인.
저장소 자체는 애플리케이션이 아니라 **스킬(마크다운 지시서) + 결정론 스크립트 + 회귀 테스트**의
묶음이다. 실행 주체는 LLM이고, 이 저장소는 그 LLM이 읽을 판단 기준과 손댈 수 없는 도구를 제공한다.

배포 산출물은 셋이다.

| | 무엇 | 어디에 |
|---|---|---|
| **하네스** | `skills/` + `commands/` + `hooks/` + `.mcp.json` — 4단계 전 구간, MCP 사용 | Claude Code 플러그인 |
| **웹앱 스킬** | `webapp/kca-report-hwpx/` — ③초안·④변환만, MCP 없이 자립 | claude.ai·ChatGPT·Gemini 업로드 / Codex·Antigravity는 `.agents/skills/`에 설치 |
| **claudian 위키** | 별도 저장소([bcchung81/claudian](https://github.com/bcchung81/claudian)) | 선택 결합 |

## 명령

```bash
python3 -m pytest -q                          # 전량 (CI가 매 push 실행)
python3 -m pytest tests/test_value_drift.py -q          # 파일 하나
python3 -m pytest tests/test_no_dead_code.py::test_no_orphan_scripts -q   # 테스트 하나
python3 -m pytest -q -k postprocess            # 이름 매칭

bash scripts/package_check.sh                  # 배포 가드 — 금지 폴더 추적·PII 스캔
python3 scripts/build_webapp_skill.py --target all   # dist/에 5플랫폼 패키지 (기준 9종 검사)

python3 skills/report-pipeline/scripts/doctor.py            # 자가진단
python3 skills/report-pipeline/scripts/consolidate_rules.py --check   # 규칙 통폐합 현황
```

의존성 설치 단계가 없다 — **모든 런타임 스크립트는 파이썬 표준 라이브러리만 쓴다**(웹앱
샌드박스에서 `pip` 없이 돌아야 한다). 테스트도 `pytest` 외 의존이 없다. 새 스크립트에
서드파티 import를 넣지 말 것.

## 아키텍처

### 판단은 `references/`, 실행은 `scripts/`

`skills/report-pipeline/`의 두 폴더가 이 저장소의 중심 분할이다.

- `references/*.md` — **LLM이 읽고 판단하는 기준**(style-guide·md-profile·format-profile·
  hwpx-recipe·rules-seed·diagram-pool·table-pool·factcheck).
- `scripts/*.py` — **판단이 끼어들면 안 되는 일**. 양식 정합처럼 매번 똑같아야 하는 것은 전부
  스크립트로 내려 LLM 편차를 없앴다.

새 기능이 "매번 같은 결과여야 하는가"로 어느 쪽에 넣을지 정한다.

### 작업폴더가 인터페이스다

4단계는 서로를 호출하지 않는다. 각 단계는 건별 작업폴더(`{reports_dir}/{YYYYMMDD}/{HHMM}_{슬러그}/`)를
읽고 쓸 뿐이다 — `00_context.md` → `research/` → `05_analysis.md` → `10_outline.md` →
`20_draft.md` → `final/{제목}.hwpx`. "이어서 해줘"가 항상 동작하는 이유이며, 단계 조합
("분석부터", "변환만")에 케이스 로직을 만들지 않는 이유다. 경로 규약은
`skills/report-pipeline/scripts/harness_config.py`가 단독으로 정의한다.

`20_draft.md`가 진짜 원본(SSOT)이다. 변환이 실패해도 초안은 반드시 인도된다.

### `SKILL_DIR` 상대 경로

SKILL.md 안의 모든 스크립트 호출은 `"$SKILL_DIR/scripts/…"` 형태여야 한다. 저장소 상대경로를
쓰면 플러그인 설치 환경(cwd가 사용자 프로젝트)에서 전부 깨진다.

### 규칙 복리축적 — `rules.md`

게이트 피드백이 `lessons.jsonl`에 쌓이고, 2회 이상 반복되면 `rules.md`에 `R0NN [단계태그]`로
승격된다. 각 단계는 자기 태그(`[research]`/`[analyze]`/`[draft]`/`[export]`)만 grep해 읽는다.

- 배포 시드는 `skills/report-pipeline/references/rules-seed.md`, 운영 축적본은
  `report/_harness/rules.md`(gitignore). 둘은 **양방향으로** 일치해야 하며
  `test_value_drift.py`가 검사한다.
- 폐지된 규칙은 번호를 재사용하지 않고 결번으로 남긴다(`references/rules-history.md`).
- 대체된 규칙에는 `**[대체됨 → R0NN]**` 표기를 단다 — 안 달면 틀린 값이 계속 살아 움직인다.
- 마지막 통합 마커(`<!-- consolidated-at: R0NN -->`) 이후 10건이 늘면
  `test_consolidate_rules.py`가 실패한다. 자동 병합은 하지 않는다.

### 값 드리프트 — 단일 출처는 `format-profile.kca.md`

간격·들여쓰기·자간 같은 실측값이 문서·코드·테스트 여러 곳에 복제돼 있다. `format-profile.kca.md`가
단일 출처이고 `test_value_drift.py`가 코드 상수와 대조한다. **값을 바꾸려면 프로파일과 코드를
함께 고쳐야 한다.**

### 웹앱 사본은 바이트 동일해야 한다

`webapp/kca-report-hwpx/`는 하네스에서 스크립트·문서를 복사해 쓴다. 하네스 쪽을 고쳤으면
`cp`로 동기화하고 빌드한다(안 하면 빌드·`test_no_dead_code.py`가 잡는다).

- 동기 대상 스크립트: `postprocess_hwpx.py` · `validate_hwpx.py` · `prep_report_md.py` ·
  `lint_md_profile.py` · `audit_style.py`
- 동기 대상 문서: `md-profile.md` · `style-guide.md` · `table-pool.md`
- `diagram-pool.md`는 **의도적 분기**(웹앱판은 도식 Pool 원형 hwpx를 싣지 않는다).
- `webapp/references/rules.md`는 손으로 고치지 않는다 — 빌드가 매번 시드에서 재생성하며
  `[draft]`·`[export]` 태그만 싣는다.

### hwpx 변환 — 후처리 생략 금지

kordoc `generate_document` 산출물은 **아직 양식 정합이 아니다**. 순서가 고정돼 있다.

```
prep 정규화 → generate → 이미지 규격판정·주입 → postprocess_hwpx.py --all
  → validate_hwpx.py structural → 왕복 되읽기 → validate_hwpx.py compare
```

`postprocess_hwpx.py`(114KB, hwpx XML 직접 수정)를 건너뛰면 규칙 위반본이 그대로 인도된다.
표 폭 정합(R036·R042)과 패키지 정합(R043 `canonicalize_package` — `version.xml` 등 필수 멤버.
없으면 자료교환 시스템이 hwpx로 인식하지 못해 내부망 반입이 반려된다)은 플래그와 무관하게
매 실행 적용된다. `hooks/verify_hwpx_hook.py`가 PostToolUse로 이 검증 우회를 차단한다.

### 하네스 금기 2건

1. 같은 파일에 병렬 쓰기 금지 — 각 에이전트는 자기 산출 파일에만 쓴다.
2. **본문 절별 병렬 집필 금지** — 문체·논지가 파편화된다. 속도가 남아도 하지 않는다
   (감사·검증만 쪼갠다).

## 저장소 경계 — 절대 커밋하지 않는 것

`form/`(기관 양식 원본)·`report/`(실보고서 산출물·운영 규칙)·`docs/analysis/`·
`docs/talk/`는 gitignore이며 `package_check.sh`가 `git ls-files`로 재확인한다. public 배포
저장소라 기관 내부 내용이 올라가면 안 된다.

런타임은 `form/`을 참조하지 않는다 — 양식 자산은 `skills/report-pipeline/assets/` 번들 사본을
쓴다. 테스트가 `report/_harness`를 참조할 때는 시드 폴백·skipif를 둬야 한다(fresh clone에서
CI가 돌기 때문).

`tests/`는 PII 탐지 픽스처(가짜 연락처)를 의도적으로 포함하므로 PII 스캔 대상에서 제외한다.

## 테스트가 지키는 것

| 테스트 | 막는 것 |
|---|---|
| `test_value_drift.py` | 규약 문서 ↔ 코드 상수 드리프트, 시드 ↔ 운영 규칙 양방향 불일치 |
| `test_consolidate_rules.py` | 규칙 축적 방치(+10건), 죽은 참조, 근거 등급 누락 |
| `test_no_dead_code.py` | 고아 스크립트·미호출 함수·유령 CLI 플래그·웹앱 사본 분기 |
| `test_references_consistency.py` | 참조 문서 간 정합, 룰 번호 중복 |
| `test_plugin_structure.py` | 플러그인·마켓플레이스 매니페스트 구조와 버전 일치 |
| `test_postprocess_hwpx.py` | 후처리 규칙 회귀 |

새 규칙(R0NN)을 추가하면 대체로 이 중 둘 이상을 함께 고쳐야 통과한다.
