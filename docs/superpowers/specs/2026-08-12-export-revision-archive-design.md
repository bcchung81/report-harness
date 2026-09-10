# export 판본 보존 설계 — 개정 시 변환 세트 아카이브

> '26.8.12 확정. `final/` hwpx가 이미 있는 상태에서 재변환이 일어날 때, 직전 변환 세트를
> `revisions/rNN/`에 통째로 보존한다. 스크립트가 실체이고 훅이 안전망이다.
>
> **'26.9.10 구현 시 변경 2건(R086)** — 이 문서의 나머지 결정은 그대로 승계했다.
> ① 폴더명 `revisions/` → `history/`. 초안 교정 스냅샷(`history/drafts/`)까지 담게 되어
> '변환 판본'만 가리키는 이름이 좁아졌다. ② **hwpx는 `history/`로 옮기지 않는다** —
> `final/`에 `r{NN}_{YYYYMMDD}_` 접두어로 쌓아 판본별로 남긴다(사용자 확정: "파일명이
> 길어져도 바로 판단 가능하도록"). 원문의 '`final/`에 항상 1개' 결정을 대체한다.
> ③ 훅 안전망은 채택하지 않았다 — 스냅샷은 사유가 필요해 사람이 뜨는 것이 맞고,
> `revise`는 재변환 절차에 박아 두었다.

## 1. 배경 — 실측된 두 가지 어긋남

`report/` 산출물 6건을 전수 대조한 결과, 변환 파이프라인의 결정론 구간은 텍스트에 충실했다
(`20_draft → 40_prepared → 43_convert_input` 드리프트 0건, `20_draft ↔ 최종 hwpx` 실물
유사도 0.967~0.976이며 차이는 전부 표 평탄화·h1 제목 아티팩트). 실제 불일치 2건은 변환이
아니라 **판본 관리 부재**였다.

- `20260730/2046_이음5G…`: hwpx는 8/4 13:38에 재생성됐는데 `40_roundtrip.md`는 7/30 20:48
  그대로다. 현행 draft와 그 roundtrip의 유사도는 0.524 — 같은 폴더 안에서 두 판본이 섞여 있다.
  같은 8/4 hwpx 실물과는 0.967로 정상이므로, 어긋난 것은 산출물이 아니라 **폴더 상태**다.
- `20260807/2242_xmos…`: `final/`에 서로 다른 보고서 hwpx 2개가 이름만 다르게 공존한다.
  `40_prepared.md`(19,254B)의 출처는 `20_draft.md`가 아니라 `50_사전미팅_종합검토_draft.md`
  (19,254B, 바이트 일치)였다. 파일명 규약이 지켜지지 않아 **어느 초안의 산출물인지 추적이
  파일명으로는 불가능**했다.

두 건 모두 규약 문서에는 절차가 적혀 있었다. 규약만으로는 새는 것이 이 저장소의 실증된
실패 모드이며, 이는 `verify_hwpx_hook.py`가 이미 다루는 문제와 같은 성격이다 — *"린트·검증
스크립트는 모델이 부를 때만 돕는다. 이 훅은 모델의 협조 없이 걸린다."*

## 2. 목표 / 비목표

**목표**

- 재변환 직전에 직전 변환 세트를 손실 없이 보존한다.
- `final/`에 hwpx가 항상 1개만 남게 해 현행본이 파일만 보고 판별되게 한다.
- "이 hwpx가 어느 초안에서 나왔나"를 파일명 규약이 아니라 **지문**으로 답할 수 있게 한다.
- 모델이 절차를 빠뜨려도 보존이 일어나게 한다.

**비목표**

- 기존 산출물의 소급 복구. `2046`·`2242`의 어긋남은 이미 벌어진 일이며 별도 1회 정리 건이다.
- 판본 간 diff·머지·롤백 UI. 보존만 한다.
- 웹앱(`webapp/kca-report-hwpx/`) 반영. 웹앱에는 work_dir 개념이 없다.

## 3. 설계 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| 판본 단위 | 변환 세트 전체(6종) | draft·hwpx 2개만으로는 대조 근거가 남지 않고, §1의 roundtrip 어긋남을 못 막는다 |
| 트리거 | 재변환 직전(`final/*.hwpx` 존재 감지) | 파일 존재 여부만 보므로 모델 판단이 개입하지 않고, 개정 없는 건에는 아예 도달하지 않는다 |
| 구현 | 스크립트 + PreToolUse 훅 두 겹 | 스크립트가 실체, 레시피가 정상 경로, 훅이 미호출 시 안전망. 저장소 기존 패턴 |
| 복사 의미론 | 이동이 아니라 **복사** | 재변환이 실패해도 직전 정본이 `final/`에 그대로 남아야 한다 |
| `research/` | 복사하지 않고 공존, 지문만 기록 | append-only 자산이라 판본마다 복사하면 원본 PDF·이미지가 중복된다 |

## 4. 폴더 구조

`2242` 건이 2회 개정된 상태를 예로 든다.

```
report/20260807/2242_xmos-펌웨어-보안검증/
├── 00_context.md              ← 갱신 누적 (판본 무관)
├── 05_analysis.md
├── 10_outline.md
├── 20_draft.md                ← 현행본 (항상 최신 = SSOT)
├── 40_prepared.md             ← 현행본
├── 43_convert_input.md        ← 현행본
├── 40_roundtrip.md            ← 현행본
├── 40_qa.md                   ← 현행본
│
├── final/
│   └── 데스크톱형 AI 로봇 도입 보안성 종합 검토결과.hwpx   ← 현행본 1개만
│
├── revisions/                 ← 신설
│   ├── index.jsonl
│   ├── r01_20260808-1807/
│   │   ├── 20_draft.md
│   │   ├── 40_prepared.md
│   │   ├── 43_convert_input.md
│   │   ├── 40_roundtrip.md
│   │   ├── 40_qa.md
│   │   └── 데스크톱형 AI 로봇 오디오 펌웨어 보안 검증결과.hwpx
│   └── r02_20260810-1535/
│       └── (같은 6종)
│
├── research/                  ← 복사 안 함, 전 판본 공유
│   ├── _manifest.jsonl
│   ├── provided/XMOS_오디오_펌웨어_보안점검_중국.pdf
│   └── fetched/vault-사전지식/
└── tools/                     ← 복사 안 함
```

- 아카이브 대상 6종 중 **없는 파일은 조용히 건너뛴다**(전건 필수가 아니다 — 팩트체크 생략 등으로
  `40_qa.md`가 없을 수 있다). 실제 복사된 목록은 `index.jsonl`에 남는다.
- `final/`에 hwpx가 여러 개면 전부 복사한 뒤 전부 비운다. `2242`의 현 상태가 그 경우다.
- 디렉터리명 `rNN_{YYYYMMDD-HHMM}`의 `NN`은 `index.jsonl` 줄 수 + 1로 정한다(0 패딩 2자리).
  같은 분에 두 번 실행되면 `NN`이 달라 충돌하지 않는다.

## 5. `revisions/index.jsonl`

1판본 1줄 append.

```jsonl
{"rev":1,"at":"2026-08-08T18:07:13","reason":"사전미팅 의견 반영 개정","dir":"r01_20260808-1807","hwpx":["데스크톱형 AI 로봇 오디오 펌웨어 보안 검증결과.hwpx"],"files":{"20_draft.md":"a3f1…","40_prepared.md":"9c22…","데스크톱형 AI 로봇 오디오 펌웨어 보안 검증결과.hwpx":"7e04…"},"research":{"manifest_lines":12,"manifest_sha256":"b81d…"}}
{"rev":2,"at":"2026-08-10T15:35:06","reason":"unattended","dir":"r02_20260810-1535","hwpx":["데스크톱형 AI 로봇 도입 보안성 종합 검토결과.hwpx"],"files":{"20_draft.md":"5b7e…","40_prepared.md":"1d90…","데스크톱형 AI 로봇 도입 보안성 종합 검토결과.hwpx":"c412…"},"research":{"manifest_lines":14,"manifest_sha256":"e77a…"}}
```

| 필드 | 의미 |
|---|---|
| `rev` | 1부터의 순번 |
| `at` | 보존 시각 ISO8601 (초 단위) |
| `reason` | 개정 사유. 훅이 대신 뜬 경우 **`"unattended"` 고정** |
| `dir` | 아카이브 디렉터리명 |
| `hwpx` | 보존한 hwpx 파일명 목록 |
| `files` | 보존한 전 파일의 sha256 |
| `research` | `_manifest.jsonl`의 줄 수와 sha256. 없으면 `null` |

`files`의 sha256이 이 설계의 핵심이다. §1의 `2242` 건 출처를 밝힌 근거가 바이트 일치였다 —
지문이 있으면 파일명 규약에 기대지 않고 계보를 답할 수 있다.

`reason`의 `"unattended"`는 사유 공백이 아니라 **규약 밖 경로로 변환됐다는 신호**다. R072가
다룬 이탈(레시피를 타지 않은 직접 `generate_document` 호출)을 사후에 셀 수 있게 한다.

## 6. 스크립트 계약 — `archive_revision.py`

`skills/report-pipeline/scripts/archive_revision.py`, stdlib-only(저장소 전 스크립트 공통 제약).

```
python3 "$SKILL_DIR/scripts/archive_revision.py" <work_dir> [--reason TEXT] [--dry-run]
```

| exit | 조건 | 의미 |
|---|---|---|
| 0 | `final/*.hwpx` 존재 → 세트 복사 + index append 완료 | 보존함. 요약 JSON을 stdout |
| 1 | `final/`에 hwpx 0건 | 최초 변환이라 보존할 것이 없음 (`postprocess_hwpx.py`의 "대상 0건"과 같은 의미론) |
| 2 | 인자 오류·work_dir 부재·IO 실패 | 오류 |

- `--dry-run`은 복사 없이 대상 목록과 산정된 `rNN`만 JSON으로 낸다.
- `--reason` 미지정 시 `reason`은 빈 문자열. 훅은 `--reason unattended`로 호출한다.
- **멱등이 아니다** — 호출할 때마다 판본이 하나 는다. 중복 방지는 §7 훅이 담당한다.
- 복사 후 `final/`의 hwpx를 삭제해 현행본 자리를 비운다. 삭제는 복사·index append가 **모두
  성공한 뒤**에만 한다.

## 7. 훅 계약 — `hooks/archive_revision_hook.py`

`hooks.json`에 `PreToolUse` 항목을 추가한다. 기존 `verify_hwpx_hook.py`(PostToolUse)와 대칭이다.

```json
{
  "PreToolUse": [
    { "matcher": "mcp__.*__generate_document",
      "hooks": [{ "type": "command",
                  "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/archive_revision_hook.py\"" }] }
  ]
}
```

동작:

1. `tool_input`에서 `.hwpx` 경로를 찾는다(기존 훅의 `strings()` 방식 재사용 — MCP 도구는 인자
   이름이 제각각이라 값 전체를 훑는다).
2. 그 경로의 부모가 `final/`이 아니면 아무것도 하지 않는다.
3. `final/`에 hwpx가 없으면 아무것도 하지 않는다(최초 변환).
4. `revisions/index.jsonl`의 마지막 줄 시각이 **10분 이내**면 아무것도 하지 않는다 — 정상 경로가
   이미 스크립트를 불렀거나, 재변환 루프(레시피 §5, 최대 2회)가 도는 중이다. 이 창이 훅과
   스크립트의 이중 실행을 막는 유일한 장치다.
5. 그 외에는 `archive_revision.py <work_dir> --reason unattended`를 실행한다.
6. `archive_revision.py`를 찾지 못하면 **아무것도 하지 않는다** — 훅이 파이프라인을 막는 원인이
   되면 안 된다(기존 훅과 동일 원칙).

**`patch_document`은 감시 대상에서 뺀다.** 훅은 보존 후 `final/`을 비우는데, `patch_document`은
레시피 §3에서 바로 그 파일을 제자리 수정하므로 훅이 입력 파일을 지워버린다. `generate_document`은
항상 `patch_document` 앞에 오므로 그 시점의 보존으로 충분하고, R072가 다룬 이탈 경로도
`generate_document` 직접 호출이었다.

## 8. 수정 대상

**신규 3개**

| 파일 | 내용 |
|---|---|
| `skills/report-pipeline/scripts/archive_revision.py` | §6 계약 |
| `hooks/archive_revision_hook.py` | §7 계약 |
| `tests/test_archive_revision.py` | §9 |

**수정 8건 (파일 9개 — rules 행이 2파일)**

| 파일 | 변경 | 안 고치면 |
|---|---|---|
| `references/hwpx-recipe.md` | §0.5 「판본 보존」 신설(§1 prep 앞), 부록 CLI 표에 행 추가 | 정상 경로에 절차가 없어 훅에만 의존 |
| `SKILL.md` ④ export | 1번 팩트체크 앞에 0단계 삽입, §참조 스크립트 목록 추가 | 동일 |
| `commands/report-export.md` | 1줄 | — |
| `hooks/hooks.json` | `PreToolUse` 항목 추가, `description` 갱신 | 훅이 등록되지 않음 |
| `skills/report-pipeline/scripts/doctor.py` | `SCRIPTS` 존재 검사 8종 → 9종 (`:53`) | 자가진단이 새 스크립트 부재를 못 잡음 |
| `report/_harness/rules.md` **+** `references/rules-seed.md` | **R073 신설 — 두 곳 동시** | `test_value_drift.test_seed_carries_every_operational_rule` 실패. R062 정정 때 시드를 놓친 사고의 회귀 방지 장치다 |
| `tests/test_references_consistency.py` | `test_hwpx_recipe_mentions_scripts`의 스크립트 목록에 추가 | 레시피에서 스크립트 언급이 빠져도 통과 |
| `CHANGELOG.md` | 판본 보존 항목 | — |

**의도적 제외**

- `scripts/build_webapp_skill.py`의 `COPIED` — 웹앱에는 work_dir이 없다.
- `tests/test_no_dead_code.py`의 `COPIED` — 위와 같은 이유. 단 이 테스트는 "스크립트가 아무에게도
  안 불리는지"를 감사하므로, `archive_revision.py`가 `hwpx-recipe.md`·`SKILL.md`·훅에서
  참조되면 자동으로 통과한다.

## 9. 규칙 문안 — R073

`rules.md`와 `rules-seed.md`에 동일 문안으로 넣는다. 현재 마지막 규칙은 R072이고 통합 마커는
`consolidated-at: R068`이라, R073 신설 시 누적 5건으로 R068의 10건 임계에 걸리지 않는다.

> R073 [export] **`final/`에 hwpx가 이미 있는 상태의 재변환은 직전 변환 세트를 먼저
> 보존한다** — `archive_revision.py`가 `20_draft.md`·`40_prepared.md`·`43_convert_input.md`·
> `40_roundtrip.md`·`40_qa.md`·`final/*.hwpx` 6종을 `revisions/rNN_{YYYYMMDD-HHMM}/`로
> 복사(이동 아님)하고 `revisions/index.jsonl`에 sha256 지문과 함께 1줄 남긴 뒤 `final/`을
> 비운다. `research/`는 append-only 자산이라 복사 대상이 아니며 `_manifest.jsonl` 줄 수·지문만
> 기록한다. 정상 경로는 레시피 §0.5가 부르고, 미호출 시 PreToolUse 훅이 `--reason unattended`로
> 대신 뜬다. 배경: 재변환이 일어난 2건에서 `40_roundtrip.md`가 구판으로 남거나(2046 — 현행
> draft와 유사도 0.524) 서로 다른 판본 hwpx가 `final/`에 공존해(2242) 계보 추적이 불가능했다
> (근거[실측]: '26.8.12 산출물 6건 전수 대조)

## 10. 테스트 — `tests/test_archive_revision.py`

| 케이스 | 확인 |
|---|---|
| hwpx 없는 work_dir | exit 1, `revisions/` 미생성 |
| hwpx 1개 + 세트 전건 | exit 0, 6종 복사, `final/` 비워짐, index 1줄 |
| hwpx 2개 (`2242` 형태) | 둘 다 복사, `hwpx` 배열 길이 2 |
| `40_qa.md` 없음 | 나머지만 복사하고 성공, `files`에 미포함 |
| 2회 연속 실행 | `r01`·`r02` 생성, index 2줄, `rev` 1·2 |
| sha256 정합 | `files`의 값이 복사본 실제 해시와 일치 |
| `research/` 미복사 | `revisions/rNN/research`가 없고 `research.manifest_lines`가 원본 줄 수와 같음 |
| `--dry-run` | 파일 시스템 무변경, JSON에 대상 목록·`rNN` |
| index append 실패 시 | `final/` 미삭제 (복사·append 성공 후에만 삭제) |
| 훅 10분 창 | 최근 항목이 있으면 훅이 스크립트를 부르지 않음 |

## 11. 남는 판단

- **재변환 실패 시 헛도는 판본**: 스냅샷만 뜨고 변환이 실패하면 `rNN`이 하나 는다. 복사본이라
  무해하므로 허용한다 — 롤백 로직을 넣으면 훅이 파이프라인을 막는 원인이 될 수 있다.
- **10분 창의 임의성**: §7-4의 값은 재변환 루프(최대 2회)가 도는 시간을 넉넉히 덮는 어림값이다.
  실사용에서 이중 판본이 관찰되면 조정하고 lessons에 남긴다.
- **소급 정리**: `2046`의 구판 roundtrip과 `2242`의 hwpx 2개 공존은 이 설계로 자동 복구되지
  않는다. 별도 1회 작업으로 각각 `r01`을 손으로 구성할지는 이 스펙 밖이다.
