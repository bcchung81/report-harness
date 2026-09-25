# 리뷰 코멘트 처리 에이전트 지시서 — 여러 보고서 동시 리뷰용 서브에이전트

> 쓰는 때: 리뷰 중인 보고서가 **2건 이상**이고 `review_server.py wait --all`이 여러 보고서의 코멘트를
> 넘겼을 때('26.9.25 사용자 선택). 메인 세션이 보고서마다 이 지시서로 에이전트 1개를 띄운다. 보고서 1건이면
> 메인이 직접 처리한다(에이전트마다 기준 문서를 다시 읽는 비용이 1건일 때는 손해다).
>
> 분담 원칙: **데이터는 에이전트, 하네스·규칙·사용자 대화는 메인.** 공유 자원(규칙·코드·lessons)을 한
> 곳에서만 쓰게 해 여러 보고서를 동시에 고쳐도 서로 부딪히지 않게 한다. 한 보고서의 묶음은 한 번에 한
> 에이전트만 맡는다 — 절별로 나눠 맡기지 않는다(하네스 금기 2).

## 1. 메인이 넘기는 것

- `work_dir` — 이 보고서의 작업폴더(다른 보고서 폴더는 읽지도 쓰지도 않는다)
- `SKILL_DIR` — 하네스 스킬 폴더
- `items` — `wait --all` 출력 중 이 보고서 것(`id`·`doc`·`kind`·`scope`·`addr`·`quote`·`comment`)

## 2. 먼저 읽는다(생략 금지)

1. `{SKILL_DIR}/references/style-guide.md` — 문체·계층·절 제목의 기준(R074)
2. `python3 "{SKILL_DIR}/scripts/harness_config.py"`로 `state_dir`을 얻고 `grep -F "[draft]" {state_dir}/rules.md`
3. `{work_dir}/00_context.md` — 이 보고서에서 이미 정한 것(게이트 답변·사용자 결정)
4. 코멘트가 가리키는 문서(`doc`, 없으면 `20_draft.md`)의 해당 항목과 앞뒤 — `addr`는 절 주소(`□2-ㅇ1`·`□2-표3`·
   `§1.2-•4`), `quote`는 사용자가 본 글자다

## 3. 고쳐도 되는 것과 안 되는 것

| 대상 | 처리 |
|---|---|
| `20_draft.md`, `figures/*.json`, 그 밖의 루트 부속 md | 코멘트가 가리킨 항목만 고친다 |
| `00_context.md` | 고치지 않고 정정 줄을 덧붙인다 |
| 초안이 있는 건의 `05_analysis.md` | 고치지 않고 반영 결과 줄을 덧붙인다(앞 게이트의 기록) |
| 초안이 있는 건의 `10_outline.md` | 손대지 않는다 — 구조 지적은 초안에 반영(승인 때 메인이 `seal`) |
| `research/`·`history/`·`final/` | 손대지 않는다 |
| `SKILL_DIR` 아래 전부(스크립트·참조 문서·자산), `rules.md`·`lessons.jsonl`, 다른 보고서 | 손대지 않는다 — 메인이 전후 지문(`review_server.py sum`)으로 대조한다 |

실행하지 않는 것: `review_server.py resolve|refresh|wait|stop|lock`, 변환(④), git. 반영 표시·화면 갱신은 메인이 한다.

## 4. 고치지 않고 메인에 돌려보낼 것

- `kind: 질문` — 답을 정해 초안에 쓰지 않는다. 질문과 초안에서 확인한 사실을 돌려준다(사용자에게 묻는 것은 메인만 할 수 있다)
- `scope: rule`(패널의 '앞으로도 적용') — 이번 문서에는 반영하고, **규칙 후보**를 돌려준다(lessons·승격은 메인)
- 하네스가 규칙대로 그리지 못하는 결함 — 데이터로 풀 수 있으면 풀고, 결함 내용을 돌려준다
- 뜻이 둘 이상으로 읽혀 고칠 수 없는 것

## 5. 고친 뒤

1. `python3 "{SKILL_DIR}/scripts/lint_md_profile.py" {work_dir}/20_draft.md` exit 0,
   `python3 "{SKILL_DIR}/scripts/audit_style.py" {work_dir}/20_draft.md` violations 0 — 통과할 때까지 고친다
2. 수치·인용을 바꾸지 않았는지 고치기 전후를 대조한다(바꾸라는 코멘트가 아니면 불변)
3. 결과를 JSON 한 덩어리로 끝낸다 — 메인은 이것만 읽는다:

```json
{"work_dir": "…",
 "done": [{"id": "f3", "what": "□2-표3에 '26 목표 열 추가"}],
 "to_main": [{"id": "f4", "why": "질문|rule|defect|ambiguous", "note": "…"}],
 "lessons": [{"gate": "draft", "feedback": "…", "fix": "…"}]}
```
