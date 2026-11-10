# tool-playbook — 출처 유형별 도구 선택표

> `report-research`(SKILL.md §1)의 참고 자료다. **강제 규칙이 아니다** — 조사 방법은 자유이며,
> 이 표는 "이런 출처면 이 도구가 잘 맞는다"는 매핑을 제시할 뿐이다. 강제되는 것은 SKILL.md §2의
> 산출 계약(경로·프론트매터·manifest)이지 여기서 어떤 도구를 썼는지가 아니다.

## 매핑표

| 출처 유형 | 우선 도구 | 비고 |
|---|---|---|
| 법령·판례·행정규칙 | MCP `korean-law` **(번들)** | `search_law`·`get_law_text`·`search_decisions`·`get_decision_text` 등. 조문·판결 원문 대조에 강함. **법제처 Open API 인증키(`LAW_OC`)를 사용자가 직접 발급해야 동작한다** — 키가 없으면 이 행을 건너뛴다. |
| 한글 문서(hwp·hwpx·pdf·docx) 파싱 | MCP `kordoc` **(번들)** | `parse_document`(본문)·`parse_table`(표)·`parse_metadata`. 제공자료(모드 I) 처리에도 동일 도구. API 키 불필요. |
| 접근 차단·봇 방지 사이트(X/Twitter, Reddit, 네이버 블로그 등) | `insane-search` 스킬 | WebFetch가 402/403을 반환하거나 알려진 차단 플랫폼(X, Reddit, YouTube, GitHub, Medium, Substack, StackOverflow, 네이버 등)일 때. 별도 설치 필요. |
| 라이브러리·프레임워크·SDK 공식 문서 | MCP `Context7` | 버전별 최신 API 문서. 기술 스펙 확인용(보고서 주제가 기술 도입 검토일 때 유용). |
| YouTube 영상 내용 | `youtube-transcript` MCP | 자막 추출 후 텍스트로 인용. |
| 위 어느 것에도 해당 없는 일반 웹 조사 | `WebSearch` → `WebFetch` | 기본값. 검색으로 후보 URL 확보 후 본문 페치. **WebFetch가 빈 본문·차단으로 실패하면 `curl -A '<브라우저 User-Agent>'`로 한 번 더 받는다** — 실패를 0건으로 세면 수치가 과소집계된다('26.8.15 개방 데이터셋 2건 → 재집계 30건). 핵심 수치는 분석 단계에서 1회 다시 확인한다. |

### 법령 본문 조회가 실패할 때 — 법제처 오픈API 직접 호출

`korean-law`의 `search_law`는 되는데 `get_law_text`·`get_annexes`가 실패하는 일이 있다('26.9.1 — 3개 조사 단위
전부, 세션 안 5회 연속 재현). 그때는 검색으로 얻은 법령일련번호(MST)로 법제처 DRF 오픈API를 직접 받는다:

```
curl -s "https://www.law.go.kr/DRF/lawService.do?OC={LAW_OC}&target=law&MST={MST}&type=XML"   # 행정규칙은 target=admrul
```

조문은 XML의 조문단위 CDATA에 있다. 받은 원문은 다른 산출물과 같이 research/ 계약(프론트매터·manifest)대로 둔다.

### 조사 단위를 나눌 때

원본(xlsx·pdf 표)을 직접 다시 읽어야 하는 단위는 팬아웃 계획에 처음부터 포함한다 — 뒤에 따로 붙이면 시간
상한을 넘긴다('26.8.23 — 4단위 계획에 원본 재판독이 추가돼 15분 상한을 20분으로 초과).

## 환경 편차 흡수 규칙

**환경에 없는 MCP·스킬은 해당 행을 건너뛰고 일반 도구로 대체한다.** 이 플러그인이 번들하는
MCP는 `kordoc`·`korean-law` 둘뿐이고(`.mcp.json`) 나머지는 사용자 환경에 있으면 활용한다.
`korean-law`는 번들되지만 인증키가 없으면 연결에 실패하므로 **미설치와 동일하게 취급**한다.
없는 도구는 표의 마지막 행(`WebSearch` → `WebFetch`)으로 강등해도 조사 자체는 계속 진행한다.
도구 부재로 조사를 중단하지 않는다.

대체가 발생하면 SKILL.md §6 종료 훅의 lessons 기록에 `gate:"research"`로 남긴다(예: feedback
"korean-law 미설치 — WebSearch로 법령 원문 검색 대체").

## 교차검증 원칙

핵심 주장(보고서 논지를 직접 지탱하는 사실·수치)은 **독립 출처 2개 이상**으로 대조한다.

- "독립"의 기준: 같은 1차 발행처를 재인용한 두 기사는 독립 출처가 아니다. 서로 다른 발행
  주체(정부 공표 vs 언론 보도, 또는 서로 다른 언론사)여야 한다.
- 출처 2개의 수치·사실이 일치하면 `confidence: 확정`. 하나만 확보됐거나 둘이 상충하면
  `confidence: 추정`으로 태깅하고, 상충 사실 자체를 산출물 본문에 명시한다(숨기지 않는다).
- 법령·공시처럼 원출처 자체가 유일하게 존재하는 유형(예: 특정 법 조문, 특정 기업의 특정 공시)은
  그 1차 출처 하나로 `확정` 처리해도 된다 — 교차검증은 "여러 매체의 진술을 대조"하는 데 의미가
  있지, 유일 원본을 억지로 두 번 찾는 절차가 아니다.
