# 의존성과 라이선스·원작자 고지

> **원작자 표기는 필수다.** 이 하네스가 쓰는 외부 저작물을 전부 여기에 명시한다.
> 번들하는 것은 원본 라이선스 전문을 함께 동봉하고, 빌드 스크립트가 그 동봉·고지를 검사한다.

## 한눈에 보기

| 구분 | 이름 | 필수 여부 | 설치 |
|---|---|---|---|
| 스킬 | `report-pipeline` | 필수 | ✅ **번들 포함** — 할 일 없음 |
| 스킬 | `report-research` | 필수 | ✅ **번들 포함** — 할 일 없음 |
| 스킬 | `humanizer` | 선택 | ✅ **번들 포함** — 할 일 없음 |
| MCP | `kordoc` | **필수** | ✅ **번들 포함** — 첫 실행 시 npx 자동 설치 |
| MCP | `korean-law` | 선택 | ✅ **번들 포함** — 단, **API 키 직접 발급 필요** |
| 플러그인 | `insane-search` | 선택 | ⬜ 별도 마켓플레이스에서 설치 |
| 외부 | 개인 지식 vault | 선택 | ⬜ 설정 파일에 경로만 지정 |

## 번들 포함분 — 따로 설치할 게 없다

플러그인을 설치하면 아래가 **한꺼번에** 붙는다. 개별 설치 명령이 필요 없다.

#### 스킬 3종 (`skills/`)

| 스킬 | 역할 | 출처 |
|---|---|---|
| `report-pipeline` | 4단계 오케스트레이터. references 7종 + scripts 8종 + assets 포함 | 이 저장소 |
| `report-research` | 자료조사 (산출 계약 강제). tool-playbook 포함 | 이 저장소 |
| `humanizer` | 한국어 AI 문체 흔적 제거 (40개 패턴, KatFishNet 논문 기반) | MIT © [DaleSeo](https://github.com/DaleSeo) — 원본 라이선스 고지를 `skills/humanizer/LICENSE`로 유지 |

#### MCP 서버 2종 (`.mcp.json`)

플러그인의 `.mcp.json`에 정의되어 있어 설치 시 자동 등록된다. 서버 실행은 `npx -y`로 이뤄지며,
**첫 실행 때 패키지를 내려받으므로 네트워크 연결이 필요하다.**

```jsonc
{
  "mcpServers": {
    "kordoc":     { "command": "npx", "args": ["-y", "kordoc", "mcp"] },
    "korean-law": { "command": "npx", "args": ["-y", "korean-law-mcp"],
                    "env": { "LAW_OC": "${LAW_OC}" } }
  }
}
```

| MCP | 필수 | 역할 | API 키 |
|---|---|---|---|
| **`kordoc`** | **필수** | hwp·hwpx·pdf·docx 파싱, hwpx 생성·검증·패치 | **불필요** |
| `korean-law` | 선택 | 법령·판례·행정규칙 근거 조사 | **필요** (아래 3-3) |

> **kordoc이 없으면?** 마크다운 초안(`20_draft.md`)까지만 만들어지고, hwpx 변환이 불가능하다는
> 사실을 1줄로 알려준다. 파이프라인이 침묵하며 실패하지 않는다.

## `korean-law` API 키 발급 — 무료, 1분

법령 조사 기능을 쓰려면 **법제처 Open API 인증키(OC)** 가 필요하다.

1. 법제처 Open API 신청 페이지 접속 → **https://open.law.go.kr/LSO/openApi/guideList.do**
2. 회원가입 → 로그인 → **"Open API 사용 신청"** 클릭
3. 발급받은 **인증키(OC)** 를 환경변수로 등록

```bash
# ~/.zshrc (zsh) 또는 ~/.bashrc (bash)에 추가
export LAW_OC="발급받은_인증키"
```

```bash
# 적용 후 확인
source ~/.zshrc && echo $LAW_OC
```

> **키가 없어도 나머지는 전부 정상 동작한다.** `korean-law` 서버만 연결에 실패하고,
> 법령 조사가 필요한 대목은 일반 웹 검색으로 대체된다.

## 별도 설치 — 있으면 좋은 것 (없어도 무방)

#### `insane-search` — 봇 차단 사이트 조사용

X/Twitter·Reddit·네이버·유튜브처럼 WAF·봇 차단이 걸린 사이트에서 자료를 가져올 때 쓴다.
없으면 접근 가능한 소스만 조사한다(파이프라인은 정상 동작).

```
/plugin marketplace add fivetaku/gptaku_plugins
/plugin install insane-search@gptaku-plugins
```

저장소: **https://github.com/fivetaku/gptaku_plugins**

#### 개인 지식 vault (Obsidian 등)

`knowledge_vault` 경로를 설정하면 조사 결과를 vault에 축적하고, 다음 보고서에서 사전지식으로
재활용한다(모드 Q). 설정하지 않으면 vault 기능만 존재하지 않는 것처럼 생략된다.
설치할 것은 없고 [설정](install-harness.md#8-설정-선택)에서 경로만 지정하면 된다.


---

# 라이선스·원작자 고지


**원작자 표기는 필수다.** 이 하네스가 쓰는 외부 저작물은 전부 아래에 명시하고, 번들하는 것은
원본 라이선스 전문을 함께 동봉한다.

## 번들 — 저장소에 사본이 들어 있는 것

| 저작물 | 원작자 | 라이선스 | 경로 | 용도 |
|---|---|---|---|---|
| `humanizer` | **[DaleSeo](https://github.com/DaleSeo)** | MIT | `skills/humanizer/LICENSE`<br/>웹앱판 `references/humanizer/LICENSE` | 한국어 AI 문체 흔적 제거 (40패턴) |

웹앱 스킬(`webapp/kca-report-hwpx/`)에도 같은 사본이 들어가며, 패키지 루트 `NOTICE.md`에
저작자·라이선스·변경 사항(프론트매터 제거, 파일명 `HUMANIZER.md`)을 명시한다. 빌드 스크립트가
**LICENSE 동봉·NOTICE 기재·상류 원본과 바이트 일치**를 검사해 하나라도 빠지면 패키징을 막는다.

## 실행 시 내려받는 것 — 사본을 두지 않는다

`npx -y`로 실행 시점에 설치되므로 이 저장소에 코드 사본이 없다. 각 패키지의 라이선스는
해당 저장소에 있다.

| 패키지 | 원작자 | 라이선스 | 저장소 |
|---|---|---|---|
| `kordoc` | **[chrisryugj](https://github.com/chrisryugj)** | MIT | [chrisryugj/kordoc](https://github.com/chrisryugj/kordoc) |
| `korean-law-mcp` | **[chrisryugj](https://github.com/chrisryugj)** | MIT | [chrisryugj/korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp) |

## 별도 설치 — 사용자가 직접 설치하는 것

| 항목 | 원작자 | 라이선스 | 저장소 |
|---|---|---|---|
| `insane-search` 플러그인 | **[fivetaku](https://github.com/fivetaku)** | MIT | [fivetaku/gptaku_plugins](https://github.com/fivetaku/gptaku_plugins) |
| `python-hwpx` (웹앱판 선택) | **[airmang](https://github.com/airmang)** | Apache-2.0 | [airmang/python-hwpx](https://github.com/airmang/python-hwpx) |

`python-hwpx`는 웹앱 스킬의 되읽기 1순위 백엔드로만 쓰고, 없으면 stdlib 폴백이 대신하므로
**필수가 아니다.**

## 코드가 아닌 것 — 데이터·서식·글꼴

라이선스가 코드와 다르게 걸리는 항목이라 따로 짚는다.

| 항목 | 성격 | 주의 |
|---|---|---|
| 법제처 Open API 데이터 | 공공데이터 | **인증키(`LAW_OC`)는 개인 발급분이며 저장소·배포본에 넣지 않는다.** 조회 결과의 이용 조건은 [법제처 이용안내](https://open.law.go.kr/LSO/information/service.do)를 따른다 — 구체적 이용 조건은 확인하지 않았으니 대외 배포 전 직접 확인할 것 |
| KCA 양식 자산 | 기관 서식 | 머리말 배너(로고·슬로건)와 동결 헤더는 **기관 내부 서식에서 이식**한 것이다. 이 저장소는 공개이므로 대외 재배포 시 기관 승인 여부를 확인할 것 |
| 휴먼명조 · HY헤드라인M · 맑은 고딕 | 상용 글꼴 | **글꼴 파일을 배포하지 않는다.** hwpx는 글꼴을 문서에 품지 않고 이름만 참조하며(실측: 정품 한컴 문서도 임베딩 0), 렌더링은 열람자 PC에 설치된 글꼴이 담당한다 |

## 이 저장소 자체

MIT © 2026 bcchung81 — 전문은 [LICENSE](../LICENSE). 하네스가 만든 **보고서 산출물의 저작권은
작성자에게 있다** — 이 라이선스는 도구에만 적용된다.


---


---

- 전체 소개 → [README](../README.md)
