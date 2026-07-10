# KCA 개조식 보고서 하네스 (report-harness)

> **한 문장:** KCA(한국방송통신전파진흥원)식 **개조식 공공기관 보고서**를, 작성·검증·렌더링을 분리한 **5-에이전트 팀**으로 생산하고 최종 **HWPX(한컴 한글)** 파일까지 산출하는 Claude Code 하네스.

기존의 단일 스킬(한 주체가 작성·검증·변환을 순차 수행)을 **파이프라인 + 생성-검증(Producer-Reviewer) 하이브리드** 아키텍처로 재구성했다. 작성자와 검증자를 강제로 분리해 자기검증 편향을 제거하고, 문체 오류와 렌더링 오류를 다른 에이전트가 잡아 원인을 격리한다.

![워크플로우](examples/workflow.png)

---

## 아키텍처

**파이프라인 + 생성-검증 하이브리드.** 순차 의존(기획→작성→렌더)을 파이프라인으로 두고, 품질이 중요한 두 지점에 생성-검증 반려 루프(`⇄`)를 끼운다.

```
[kca-report-orchestrator]  ← 진입점 / 조율
   │
   Phase 0  규모 라우팅(소형→기존 스킬 / 대형→팀) + 재실행 판별
   │
   Phase 1  kca-planner ─────────────────────▶ 01_planner_outline.md
   │        (korean-law MCP·deep-research·firecrawl 근거, 확정/미확정/플레이스홀더 태깅)
   │
   Phase 2  kca-writer  ⇄  kca-style-auditor  ▶ 02_draft / 03_auditor_report
   │        (개조식 작성)   (독립 문체 검증·반려, 최대 3회)
   │
   Phase 3  kca-builder ⇄  kca-hwpx-qa        ▶ 04_final.hwpx / 05_qa_report
   │        (MD→HWPX+도해)  (구조·내용 교차검증)
   │
   Phase 4  완료 보고 + 프로세스 지표 + 피드백 → 진화
```

`⇄` = 생성-검증 반려 루프. **작성자 ≠ 검증자**를 강제해 편향을 제거한다.

---

## 5개 에이전트 (`agents/`)

| 에이전트 | 역할 | 핵심 경계 | 산출물 |
|----------|------|-----------|--------|
| **kca-planner** | 골격 결정 + 사실·수치 수집·태깅 | 문체 안 다듬음 | `01_outline` |
| **kca-writer** | 개조식 문체 전개(명사형·2줄·괄호리드) | 사실 날조 안 함 | `02_draft` |
| **kca-style-auditor** | 문체 **외부** 검증·반려(L1~L15) | 원고 직접 수정 안 함, HWPX 안 봄 | `03_auditor_report` |
| **kca-builder** | MD→HWPX 렌더·양식 병합·도해 주입 | 문체 안 건드림 | `04_final.hwpx` |
| **kca-hwpx-qa** | 구조(`validate_hwpx.py`)+내용(`parse_document`) 교차검증 | 문체 판정 안 함 | `05_qa_report` |

모든 에이전트는 `model: opus`. QA 에이전트는 스크립트 실행이 필요해 `general-purpose` 계열로 동작한다.

---

## 스킬 (`skills/`)

| 스킬 | 역할 |
|------|------|
| **kca-report-orchestrator** | 진입점. 규모 라우팅·파이프라인·생성-검증 루프·부분 재실행·진화 조율 |
| **kca-report-layout** | **규칙 SSOT** — 본문 2p·□당 ㅇ≤3·통합·붙임(최소 1p)·용어 각주(ㅇ당 `*`≤1+`※`≤1)·워크플로우 도해 |
| **kca-style-lint** | **탐지 SSOT** — 개조식 린트 체크리스트 L1~L15(명사형·2줄·괄호리드·각주·붙임 등) |
| **kca-report-style** | 개조식 규칙 지식 베이스 + HWPX 변환 스크립트/참고양식. 소형 1페이지 보고서는 이 스킬이 단독 처리 |

> **SSOT 분담:** 규칙의 *임계값·방법*은 `kca-report-layout`이 유일 원천, `kca-style-lint`는 그것을 *탐지·판정*. 규칙 변경 시 layout을 먼저 고치고 lint·에이전트는 참조만 갱신한다.

---

## 스크립트 (`skills/kca-report-style/scripts/`)

| 스크립트 | 하는 일 |
|----------|---------|
| `prep_report_md.py` | HWPX 변환 전 결정론적 전처리 — 각주 `* `→전각 `＊ ` 치환, 도해 마커 보존 |
| `build_from_template.py` | 참고양식(레터헤드·그라데이션·계층 글꼴) 병합. `＊`를 각주 스타일(맑은고딕12)로 재지정 |
| `postprocess.py` | 참고양식 없이 단독 생성 시 폴백 렌더 경로 |
| `inject_image.py` | 워크플로우 도해 PNG를 HWPX BinData에 주입(`--marker` 위치 치환, 결정론 id, `hc` 네임스페이스 자동 선언) |
| `validate_hwpx.py` | 스타일 id 연속성·IDRef 범위·zip/xml 무결성 검사(렌더 불가 환경의 "조용한 실패" 방어선) |

---

## 워크플로우 도해 파이프라인 (SVG → PNG → HWPX)

HWPX(kordoc)는 이미지를 못 만들고 표·텍스트만 렌더하므로, 흐름도는 아래 4단계로 주입한다. 외부 의존(Figma·plan key) 없이 **로컬 도구만** 사용:

1. **SVG 직접 작성** — 정사각 캔버스(가로 클리핑 방지), 상단 배치
2. **`qlmanage`** (macOS 네이티브) — SVG → PNG 래스터화
3. **Pillow** — 비-흰색 크롭 + 흰 여백
4. **`inject_image.py --marker "도해"`** — MD의 `[도해: …]` 문단을 그림으로 치환(정확 위치 배치)

---

## 설치

Claude Code 전역(`~/.claude/`)에 배치한다:

```bash
git clone https://github.com/bcchung81/report-harness.git
cd report-harness
# 에이전트
cp agents/*.md ~/.claude/agents/
# 스킬
cp -R skills/* ~/.claude/skills/
```

플러그인으로 설치하려면 마켓플레이스에 추가:

```
/plugin marketplace add bcchung81/report-harness
```

---

## 사용

```
KCA 보고서 하네스로 써줘
2026 직원 AI 역량강화 교육계획을 개조식 보고서로 만들어
이 초안을 KCA 개조식 HWPX로 변환해줘
```

후속 작업(부분 재실행)도 처리:

```
표만 다시          → writer~qa 재호출, outline 재사용
문체만 재검수       → style-auditor만
HWPX만 다시 뽑아    → builder~qa만
```

---

## 요구사항

- **Claude Code** — 에이전트 팀 모드는 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`(없으면 서브에이전트 파이프라인으로 자동 폴백)
- **kordoc MCP** — MD↔HWPX 변환·파싱(`generate_document`·`parse_document`)
- **korean-law MCP** — 법령·규정 근거 수집(선택)
- **deep-research · firecrawl · insane-search 스킬** — 동향·통계 근거 수집(선택)
- **macOS** — `qlmanage`(SVG 래스터, 도해 사용 시)
- **Python 3 + Pillow** — 도해 크롭

---

## 설계 원칙

1. **작성자 ≠ 검증자** — writer와 style-auditor를 다른 에이전트로 강제 분리(자기검증 편향 제거)
2. **문체 검증 ≠ 렌더 검증** — auditor(문체) / hwpx-qa(구조)로 원인 격리
3. **에이전트=누가 / 스킬=어떻게** — 재사용성의 원천
4. **이중 트랙** — 소형은 단일 스킬, 대형만 하네스(과설계 방지)
5. **부분 재실행** — `_workspace/`에 01~05 산출물 보존
6. **진화하는 시스템** — 매 실행 후 피드백을 규칙(SSOT)에 반영, 변경 이력 기록

---

## 산출물 예시

`examples/sample-report.hwpx` — 이 하네스로 생성한 실제 보고서(레터헤드·워크플로우 도해·용어 각주·붙임 포함).

---

## 라이선스

Apache-2.0
