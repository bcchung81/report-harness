> `kca-report-hwpx` 스킬을 웹앱에 올린다. 터미널·MCP 없이 **파일 하나로** 개조식 초안 작성과
> hwpx 변환을 쓴다. 조사·분석까지 필요하면 [하네스판 설치](install-harness.md)를 보면 된다.
> 전체 소개는 [README](../README.md).

# 웹앱 스킬 설치 — Claude · ChatGPT · Gemini

터미널을 쓰지 않는 실무자에게는 이쪽을 준다. **MCP도 플러그인도 필요 없고 파일 하나면 된다.**

## 실무자: 설치

운영자에게 자기 플랫폼용 파일을 하나 받아 올리면 끝이다.

| 플랫폼 | 받을 파일 | 등록 경로 |
|---|---|---|
| **Claude** | `kca-report-hwpx-claude.skill` | 설정 → Capabilities → Skills → 업로드 |
| **ChatGPT** | `kca-report-hwpx-chatgpt.zip` | Plugins → Skills → Create → Upload from your computer |
| **Gemini Spark** | `kca-report-hwpx-gemini.zip` | Skills → 파일 업로드 |

올린 뒤 대화에서 `"이 내용으로 개조식 보고서 만들어줘"`라고 하고 자료를 붙여넣으면 된다.
아웃라인과 초안을 각각 한 번씩 확인해 주면 `.hwpx` 파일이 나온다(한글 2014 이상에서 열린다).

세 패키지의 **내용과 절차는 동일**하다. Gemini판만 배너 이미지가 base64 텍스트로 들어가
있고, 변환 0단계(`decode_assets.py`)가 원본으로 되돌린다 — Gemini Spark가 스킬 패키지에
바이너리 파일을 허용하지 않기 때문이다.

## 운영자: 빌드

```bash
# 세 플랫폼 전부 (기본 시드 룰)
python3 scripts/build_webapp_skill.py --target all

# 축적본 반영 — 하네스에서 쌓인 룰을 실어 배포
python3 scripts/build_webapp_skill.py --target all --rules report/_harness/rules.md

# 하나만
python3 scripts/build_webapp_skill.py --target chatgpt
```

산출: `dist/kca-report-hwpx-{claude,chatgpt,gemini}.{skill,zip}` (각 180~200KB).

`dist/`는 git에 올리지 않는다 — zip 바이트가 빌드마다 달라 이력만 불린다. 배포할 파일은
그때그때 위 명령으로 재빌드해 전달한다. 빌드 기준(아래)이 매번 다시 걸리므로 갓 빌드한
파일이 곧 검증된 파일이다.

## 플랫폼별 제약 (조사 '26.8.7)

| | Claude | ChatGPT | Gemini Spark |
|---|---|---|---|
| SKILL.md + `scripts/` 번들 | O | O | O |
| 파이썬 실행 | O | O (Code Interpreter) | O (Python·Bash만) |
| 바이너리 자산 | O | O | **X** → base64로 우회 |
| 외부 네트워크 | — | — | 금지 (우리는 미사용) |
| 용량 한도 | 넉넉 | 넉넉 | 100MB |
| 요금제 제약 | — | 개인 스킬은 **Business·Enterprise·Edu** 중심 | — |

우리 스킬은 전 구간 stdlib이고 네트워크를 쓰지 않아 세 곳 모두의 제약을 만족한다.
**단 실기동 검증은 아직 못 했다** — 각 플랫폼에서 짧은 초안으로 한 번씩 돌려봐야 한다.

## 스킬 배포 기준

빌드 스크립트가 아래를 **전부 통과해야** 패키지를 만든다. 하나라도 걸리면 exit 1로 멈춘다.

| 기준 | 내용 |
|---|---|
| **룰 최신성** | `references/rules.md`를 하네스 룰 원본에서 **매 빌드 재생성**한다. 손으로 만든 사본을 그대로 싣지 않는다 — 스테일 룰 배포 사고를 구조적으로 차단 |
| **서드파티 고지** | 번들한 서드파티 폴더마다 `LICENSE` 동봉 + 루트 `NOTICE.md`에 경로 기재. 번들 사본은 상류와 바이트 동일 |
| **루트 SKILL.md 단일** | 패키지 안에 SKILL.md가 둘 이상이면 매니페스트가 모호해진다 |
| **범위 필터** | 웹앱판은 ③·④만 하므로 `[draft]`·`[export]` 룰만 싣는다 (현재 70건) |
| **드리프트 0** | 하네스에서 복사한 스크립트 4종이 원본과 **바이트 동일**해야 한다. 갈라지면 두 판의 룰이 조용히 달라진다 |
| **dangling 참조 0** | SKILL.md·references가 가리키는 스킬 내부 경로가 실재해야 한다 |
| **사장 자산 0** | 어떤 스크립트·문서도 읽지 않는 `assets/` 파일이 있으면 안 된다 |
| **출처 고정** | `manifest.json`에 전 파일 해시 + 룰 원본 경로·해시·건수를 박는다 |
| **PII 0** | 패키지 전 파일에 전화·이메일이 없어야 한다. 위반 시 빌드 중단 + 재생성된 rules.md 원복 |

**운영 흐름은 이렇게 돈다.** 하네스(B)로 보고서를 쓰다 보면 lessons가 쌓이고, 승격되면
`rules.md`가 늘어난다. 그 시점에 위 `--rules` 빌드로 `.skill`을 다시 만들어 배포하면
**웹앱 사용자도 같은 룰을 물려받는다.** 웹앱판은 세션 간 상태를 못 가지므로, 재배포가
복리축적을 실무자에게 전달하는 유일한 경로다.

## 웹앱판에 없는 것

- **①조사·②분석** — 자료는 대화에 직접 붙여넣는다
- **이미지 주입·도식 Pool 원형 표 치환** — 도식은 `diagram-pool.md` 판정표를 보고 GFM 표로 직접 그린다
- **룰 자기증식** — 정적. 새 룰은 재배포로만 반영된다

---


## 라이선스·원작자

패키지에 번들된 서드파티는 **`humanizer` 1종**이다 — MIT © [DaleSeo](https://github.com/DaleSeo).
라이선스 전문은 패키지 안 `references/humanizer/LICENSE`, 고지는 루트 `NOTICE.md`에 있다.
빌드 기준이 LICENSE 동봉·NOTICE 기재·상류 원본과의 바이트 일치를 검사하므로, 하나라도 빠지면
패키지가 만들어지지 않는다.

되읽기에 쓰는 `python-hwpx`(Apache-2.0 © [airmang](https://github.com/airmang))는 **번들하지
않는다** — 설치돼 있으면 쓰고, 없으면 stdlib 폴백이 대신한다.

스킬 자체는 MIT © 2026 bcchung81. 전체 고지는
[docs/licenses.md](licenses.md) 참조.

---

- 전체 소개 → [README](../README.md)
- 하네스판 설치 → [install-harness.md](install-harness.md)
