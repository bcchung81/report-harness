> report-harness 플러그인을 터미널(Claude Code)에 설치한다. 4단계 전 구간(조사·분석·초안·변환)과
> 룰 복리축적을 쓰려면 이쪽이다. 웹앱만 쓸 사람은 [웹앱 스킬 설치](install-webapp.md)를 보면 된다.
> 전체 소개는 [README](../README.md).

# 하네스판 설치 — 터미널 (Claude Code)

## 0. 사전 요구사항

| 항목 | 최소 버전 | 확인 명령 | 용도 |
|---|---|---|---|
| **Claude Code** | 플러그인 지원 버전 | `claude --version` | 본체 |
| **Node.js / npx** | Node 18+ | `node -v && npx -v` | MCP 서버 실행 (`kordoc`·`korean-law`) |
| **Python 3** | 3.9+ | `python3 --version` | 결정론 스크립트 실행 (**stdlib만 사용 — pip 설치 불필요**) |
| 네트워크 | — | — | 첫 실행 시 npx 패키지 다운로드 |

Python 패키지 의존성은 **없다.** `harness_config`·`lint_md_profile`·`postprocess_hwpx` 등
모든 스크립트가 표준 라이브러리(`json`·`pathlib`·`zipfile`·`xml.etree`)만 쓴다.

## 0-1. 인증 방식과 비용 — 팀 배포 전 먼저 읽을 것

Claude Code는 **구독(OAuth)**과 **API 키(종량제)** 두 방식으로 인증한다. 어느 쪽이든
하네스는 동일하게 동작하지만 **비용 구조가 크게 다르다.**

| 방식 | 인증 | 과금 | 팀 배포 시 |
|---|---|---|---|
| 구독 | claude.ai 로그인 (Pro·Max) | 정액 + 사용량 한도(5시간 창·주간) | 1인 1구독 |
| **API 키** | `ANTHROPIC_API_KEY` 환경변수 | **토큰 종량제** | 기관 키 하나로 다수 사용 |

**보고서 1건의 실측 소비는 약 15만 토큰이다**(조사 2단위·초안 2판·변환 2회 기준).
이를 종량제로 환산하면 다음과 같다.

| 사용량 | 월 토큰 | 종량제 환산 |
|---|---|---|
| 월 2건 | 30만 | 약 $1 |
| 월 8건(주 2건) | 120만 | 약 $5 |
| 월 20건(전담) | 300만 | 약 $13 |

> 위 환산은 공개 단가에 입력:출력 9:1을 가정한 **자릿수 감각**이다. 실제 모델·캐시
> 적중률에 따라 달라지므로 도입 전 소액으로 실측할 것.

**팀에 배포한다면 API 키 방식을 먼저 검토하라.** 10명이 월 8건씩 쓰는 경우 구독은
1인 1계정이 필요하지만, 기관 API 키 하나로 묶으면 총액이 두 자릿수 배 낮아진다.
사용량 한도(5시간 창)에 걸려 작업이 끊기는 문제도 없다.

**주의 — 두 방식은 섞이지 않는다.** `ANTHROPIC_API_KEY`가 환경변수로 설정돼 있으면
claude.ai 구독으로 로그인돼 있어도 **API 종량제로 과금된다**(환경변수가 우선한다).
구독을 쓰려면 이 변수를 **비워 두어야** 예상치 못한 API 청구를 피할 수 있다.

```bash
# 종량제로 쓰려면 — 기관 키를 환경변수로
export ANTHROPIC_API_KEY="sk-ant-..."

# 구독으로 쓰려면 — 변수를 지운 상태여야 한다
unset ANTHROPIC_API_KEY
```

## 1. 설치 (2줄)

Claude Code를 실행한 뒤 프롬프트에 순서대로 입력한다.

```
/plugin marketplace add kca-deep/report-harness
```

이 저장소는 **플러그인이면서 동시에 마켓플레이스**다(`.claude-plugin/marketplace.json`).
위 명령으로 저장소를 마켓플레이스로 등록한다.

```
/plugin install report-harness@report-harness
```

`{플러그인명}@{마켓플레이스명}` 형식이며, 둘 다 `report-harness`라서 이렇게 쓴다.

> 설치 대신 `/plugin` 메뉴에서 GUI로 골라 설치해도 된다.

## 2. 설치 확인

**① 스킬·커맨드 등록 확인**

```
/report-
```

까지 입력했을 때 `report-research` · `report-analyze` · `report-draft` · `report-export` ·
`report-doctor` 5종이 자동완성에 뜨면 커맨드가 붙은 것이다.

**설치 직후 `/report-doctor`를 한 번 돌리는 것을 권한다.** 실행 환경·스크립트·규약·인증과
kordoc MCP 연결까지 순서대로 점검하고 막힌 지점을 지목한다 — 특히 **kordoc이 연결되지 않으면
hwpx 없이 md만 나오는데** 처음 쓰는 사람은 이를 실패로 인지하지 못하므로 여기서 잡는다.

**② MCP 서버 연결 확인**

```
/mcp
```

`kordoc`이 **connected**로 뜨면 정상이다. `korean-law`는 `LAW_OC` 환경변수를 등록하지 않았다면
연결 실패로 표시되는 것이 정상이며, 나머지 기능에 영향을 주지 않는다.

> 첫 `/mcp` 확인 시 `kordoc`이 연결 중이거나 실패로 보일 수 있다. npx가 패키지를 내려받는
> 중이기 때문이다. 잠시 후 다시 확인하거나 Claude Code를 재시작한다.

## 3. (선택) `korean-law` 키 등록

법령 조사가 필요하면 [korean-law 키 발급](licenses.md#korean-law-api-키-발급--무료-1분) 절차로 `LAW_OC`를 등록한 뒤
**Claude Code를 재시작**한다. 환경변수는 프로세스 시작 시점에 읽히기 때문이다.

## 4. (선택) `insane-search` 설치

```
/plugin marketplace add fivetaku/gptaku_plugins
/plugin install insane-search@gptaku-plugins
```

## 5. 첫 실행

**설정 파일을 만들지 않아도 된다.** 전부 기본값으로 동작한다. 그냥 말을 걸면 된다.

```
"AI 활용 성과측정 체계 개선방안으로 보고서 써줘"
```

첫 실행 시 다음이 자동으로 준비된다.

1. `{cwd}/reports/{YYYYMMDD}/{HHMM}_{슬러그}/` 작업폴더 생성
2. `{cwd}/.report-harness/` 상태 폴더 생성
3. `rules-seed.md`(현재 R001~R094)가 `.report-harness/rules.md`로, 경위 로그가 `rules-history.md`로 복사되어
   복리축적 시드가 됨

플러그인을 갱신한 뒤에는 첫 요청 때 `sync_rules.py --apply`가 **새로 온 규칙만** 운영 `rules.md` 끝에
덧붙이고, 손대지 않은 옛 규칙은 새 문구로 바꾼다(시드에서 폐지된 규칙은 지운다). 직접 쌓거나 고친 규칙은 번호가
겹쳐도 건드리지 않고 번호만 알려 준다(고친 규칙에 시드가 '대체됨·정정됨' 표기를 달면 본문은 두고 표기만 붙인다).
작업 중 새로 승격하는 규칙은 R9NN 번호를 받는다 — 시드 번호와 겹치지 않아 다음 갱신 때 충돌하지 않는다.
`/report-doctor`의 '규칙 동기화' 항목으로 상태를 볼 수 있다.

경로를 바꾸고 싶으면 [8. 설정](#8-설정-선택)을 보면 된다.

## 6. 문제 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| `/report-*` 커맨드가 안 뜬다 | 플러그인 미설치 또는 재시작 필요 | `/plugin` 메뉴에서 설치 상태 확인 후 Claude Code 재시작 |
| `/mcp`에서 `kordoc` 연결 실패 | npx 다운로드 실패 / 네트워크 | `npx -y kordoc@4.15.3 mcp`(`.mcp.json`에 고정된 버전)를 터미널에서 직접 실행해 오류 확인 |
| hwpx가 안 만들어지고 md만 나온다 | `kordoc` 미연결 | 위와 동일. 연결 복구 후 `"hwpx로 변환해줘"`로 ④단계만 재실행 |
| 법령 조사가 안 된다 | `LAW_OC` 미등록 | [korean-law 키 발급](licenses.md#korean-law-api-키-발급--무료-1분) 참조 후 재시작 |
| 산출물이 어디 있는지 모르겠다 | 기본값이 실행위치 기준 | `{현재 작업 디렉토리}/reports/` 확인. 고정하려면 [8. 설정](#8-설정-선택) |
| hwpx 서식이 양식과 다르다 | 후처리 누락 가능성 | `40_qa.md` 확인. `postprocess_hwpx.py`가 exit 1(대상 0건)이면 원인 규명 필요 |
| 내부망 자료교환에서 반입 거부 (octet-stream·미등록 확장자) | ① 후처리 전 hwpx는 version.xml 등 필수 멤버가 없어 판별 실패 ② 한글 재저장본은 확장자 없는 JScript 스텁(`Scripts/headerScripts`)이 삽입돼 내부 검사에 반려 | `postprocess_hwpx.py <파일> --spacing`을 다시 돌리면 패키지 정합(R043)이 두 경우 모두 소급 적용된다(멱등). `validate_hwpx.py structural`이 `errors: []`이면 정상 |
| `"이어서 해줘"` 했더니 새 폴더가 생겼다 | 슬러그 부분일치 실패 | 건명을 함께 말한다 — `"AI성과측정 건 이어서 해줘"` |
| 초안을 저장할 때마다 "초안 규칙 위반"으로 막힌다 | 플러그인 초안 린트 훅(`hooks/lint_draft_hook.py`)이 `20_draft.md`의 린트·감사 위반을 막음 | 메시지의 규칙·줄 번호대로 고친다(경고는 막지 않는다). 되읽기 기록 등 다른 md는 검사하지 않는다 |
| 갱신한 뒤에도 새 규칙이 안 보인다 | 운영 `rules.md`가 옛 시드 그대로 | `/report-doctor`의 '규칙 동기화' 확인 후 `sync_rules.py --apply`(파이프라인 첫 단계가 자동 실행) |

## 6-1. 업데이트

새 버전을 받으려면 마켓플레이스를 갱신한 뒤 플러그인을 갱신하고 Claude Code를 재시작한다. 터미널에서:

```
claude plugin marketplace update report-harness
claude plugin update report-harness@report-harness
```

Claude Code 안에서는 `/plugin` 메뉴에서 같은 일을 한다. 설치된 버전은 `claude plugin list`로 본다. 갱신은 **버전이
올라갔을 때만** 받아진다 — "already at the latest version"이면 새 판이 아직 나오지 않은 것이다.

갱신 뒤 첫 요청에서 파이프라인이 `sync_rules.py --apply`로 새로 온 규칙을 운영 `rules.md`에 덧붙이고, 손대지 않은
옛 규칙은 새 문구로 바꾸며(폐지된 규칙은 지운다) 경위 로그·통합 마커도 맞춘다. 직접 쌓거나 고친 규칙은 그대로 둔다 —
로컬 규칙은 R9NN 대역을 쓰면 시드 번호와 겹치지 않는다. 상태는 `/report-doctor`의 '규칙 동기화'에서 본다. 바뀐 내용은 [CHANGELOG](../CHANGELOG.md).

## 7. 제거

```
/plugin uninstall report-harness@report-harness
```

작업폴더(`reports/`)와 상태 폴더(`.report-harness/`)는 **삭제되지 않는다** — 축적된
`rules.md`·`lessons.jsonl`이 남으므로 재설치하면 복리 자산을 그대로 이어 쓴다.


---

## 8. 설정 (선택)

**설정 파일이 없어도 전 기능이 동작한다.** 첫 인도 시 안내를 1줄만 출력한다.
경로를 고정하고 싶으면 `~/.claude/report-harness.json`에 아래 키를 채운다(전부 선택). 설정 파일 위치는 환경변수
`REPORT_HARNESS_CONFIG`로 바꿀 수 있다 — 시험 실행이 운영 폴더를 건드리지 않게 할 때 쓰며, 없는 경로를 주면 설정 없이
(실행 위치 기준 기본값으로) 돈다.

```json
{
  "reports_dir":     "/path/to/reports",
  "state_dir":       "/path/to/state",
  "knowledge_vault": "/path/to/obsidian-vault",
  "template_hwpx":   "/path/to/기관보고양식.hwpx",
  "font_dirs":       ["/path/to/fonts"]
}
```

| 키 | 없을 때 기본값 | 역할 |
|---|---|---|
| `reports_dir` | `{cwd}/reports` | 건별 작업폴더 루트(`{reports_dir}/{YYYYMMDD}/{HHMM}_{슬러그}/`) |
| `state_dir` | `{cwd}/.report-harness` (자동 생성) | `rules.md`·`rules-history.md`·`lessons.jsonl` 위치. 첫 실행 시 시드를 복사하고, 갱신 뒤에는 `sync_rules.py`가 시드와 맞춘다 |
| `knowledge_vault` | 없음 → vault 기능(사전지식 조회·적재) 생략 | 개인 지식 vault 루트 |
| `template_hwpx` | 없음 → 번들 기본 서식 사용 | 기관 레터헤드·스타일 템플릿 병합용 |
| `font_dirs` | 없음 → OS 기본 폰트 폴더만 탐색 | 이미지 도식(`render_diagram.py`)이 맑은 고딕을 찾을 추가 폴더. 못 찾으면 대체 서체로 그리고 `font_fallback`으로 알린다 |

> 기본값이 홈이 아니라 **실행위치(cwd) 기준**인 이유: 웹앱처럼 홈 디렉토리가 휘발성인 환경에서도
> 산출물과 복리 state가 프로젝트 폴더와 함께 남도록 하기 위해서다. 로컬 사용자는 설정 파일로
> 절대경로를 주입해 오버라이드하면 된다.

`template_hwpx`는 대개 비워 둔다 — KCA 기본 양식 프로파일이
`references/format-profile.kca.md`로 번들 시드되어 별도 지정 없이 적용된다.

**vault 연동 예시** — 조사 산출물 저장소와 사전지식 소스를 같은 vault로 묶는 구성:

```json
{
  "reports_dir": "~/workspace/my-vault/reports",
  "state_dir": "~/workspace/my-vault/reports/_harness",
  "knowledge_vault": "~/workspace/my-vault"
}
```

경로에 `~`를 쓸 수 있다(자동 확장된다).

---


## 9. 라이선스·원작자

`npx`로 내려받는 MCP 2종은 MIT © [chrisryugj](https://github.com/chrisryugj)이고, 번들된
`humanizer`는 MIT © [DaleSeo](https://github.com/DaleSeo)다. **법제처 인증키(`LAW_OC`)는
개인 발급분이라 저장소·공유 설정에 넣지 않는다.** 전체 고지는
[docs/licenses.md](licenses.md) 참조.

---

- 전체 소개 → [README](../README.md)
- 웹앱 스킬 설치 → [install-webapp.md](install-webapp.md)
