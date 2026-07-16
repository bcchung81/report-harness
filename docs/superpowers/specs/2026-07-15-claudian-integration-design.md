# claudian × 보고서 하네스 통합 설계 (2026-07-15, 사용자 승인)

## 결정 사항 (AskUserQuestion 2회)

1. **토폴로지**: vault=콘텐츠 / 하네스=엔진. report-harness는 에이전트·스킬·스크립트만 git 관리, 작업 산출물은 claudian vault에 요청건별 누적.
2. **지식화 깊이**: 표준 — 제공자료는 raw+parsed까지(위키 컴파일 PENDING), 완성 보고서는 topics/ 페이지 1장 + index/log 등록.

## 아키텍처

```
workspace/
├─ report-harness/          ← 엔진 (git: agents/ skills/ tests/ hooks/)
└─ claudian/                 ← 콘텐츠 (Obsidian LLM Wiki + 보고서)
    ├─ raw/                  ← 제공자료 원본 (모드 C: 드래그 → 복사, 불변)
    ├─ acquired/parsed|fetched/  ← 추출본(kordoc)·조사자료
    ├─ concepts|entities|topics/ ← 위키 (planner 인용 / Phase 4 보고서 페이지)
    └─ reports/{YYMMDD}_{건명}/  ← 요청건별 산출물 (00~05 + final/{제목}.hwpx)
```

- **REPORT_DIR** = `claudian/reports/{YYMMDD}_{건명슬러그}/` — 오케스트레이터가 각 에이전트에 절대경로로 전달. `_workspace/` 폐지(직전 1건만 백업되던 덮어쓰기 구조 해소).
- **최종 산출물은 반드시 `{REPORT_DIR}/final/`** — 저장소 루트·외부 경로 산출 금지 (사용자 요구).
- 부분 재실행 대상 = 건명 지정 폴더 또는 날짜 최신 폴더.

## 동선 (Phase별 vault 접점)

| Phase | 접점 |
|---|---|
| 0 | REPORT_DIR 생성 + 제공자료 INGEST-lite(claudian-research 모드 C: raw 복사→parsed 추출→log `[INGEST-PENDING]`) |
| 1 | planner 3단 소스: ①parsed 추출본 ②위키 인용(모드 A) ③신규 조사(모드 B, fetched 적재) |
| 2·3 | REPORT_DIR 안에서만 작업 |
| 4 | 완성 지식화: topics/ 보고서 페이지 + index/log 등록 (다음 보고서가 [[인용]]) |

## 스키마 개정 (vault CLAUDE.md — 사람 승인)

3-레이어 표에 Reports 행(LLM 쓰기 허용·기존 건 폴더 삭제/덮어쓰기 금지), 폴더 구조에 reports/ 추가, §5.2 REPORTS 절 신설(INGEST-lite·RESEARCH-lite·지식화·PENDING 처리 우선순위).

## 이관 (1회성, 완료)

- `_workspace_prev/` → `reports/260714_PIMS-정부지적사례/`
- `_workspace/` → `reports/260715_ICT기금-관리권한-위임건의/` (+최종 hwpx → final/)
- vault 루트 보고서 7파일 → `reports/legacy/` (Obsidian 링크는 파일명 해석이라 유지)

## 같은 날 동반 수정 (실물 보고서 결함 2건 → 하네스 규칙화)

1. **표 페이지 이탈**: kordoc generate가 협폭 열 기준으로 셀 높이 과대 산정(57,882 hwpunit) → `adjust_table_widths.py`에 행 높이 재계산(줄당 1,920+282, 실측 눈금) + 제외 신호를 "첫 행 균등폭"→"rowCnt<2"로 교체(builder가 ~/.claude 사본에만 고친 드리프트를 repo 정식 흡수). TDD.
2. **법령 표기**: layout §10(「정식 법령명」+제N조제N항제N호 붙여쓰기, §·원문자·띄어쓰기·미선언 약칭 금지) + lint L24 기계 판정. planner 수집 시점부터 표준 표기. TDD.
