# kca-report-hwpx — 클로드 웹앱 배포용 자립형 hwpx 스킬 설계

> 작성 2026-08-07. 노트북 하네스(report-harness 플러그인, kordoc MCP 사용)는 **그대로 둔다**.
> 이 문서는 MCP가 없는 클로드 웹앱에서 ③초안작성 → ④hwpx변환을 수행하는 별도 스킬의 설계다.

## 1. 배경과 사전 검증

같은 초안(`report/20260803/1814_AI성과측정-방안개선/20_draft.md`, 296줄·표 20개)으로 두 경로를
실측 비교했다. 하네스(postprocess·validate)는 양쪽 모두 손대지 않았다.

| | A: kordoc `generate_document` | B: `canine89/hwpxskill` `create_document.py` |
|---|---|---|
| postprocess `--all --sender-size 12` | exit 0, 전 룰 적용 | **exit 2 하드페일** (R011 앵커 charPr 부재) |
| structural | `errors: []` | `errors: []` |
| compare | issue 1건 (표 20→22, 정상 가산) | **issue 28건** (markdown-leftover 27 + 표 수) |
| □ 서체 | HY헤드라인M 15pt | 함초롬바탕 10pt |
| ※ 서체 | 맑은고딕 13pt | 함초롬바탕 10pt |
| 제목 박스 | `found: true` | `found: false` |

B가 깨진 원인은 세 가지다.

1. Skeleton 헤더에 charPr이 7종뿐 — R008·R010·R011이 요구하는 서체·크기가 없다.
2. 인라인 마크업 미파싱 — `**(지적 사항)**`이 리터럴로 문서에 박힌다(27개 문단).
3. 개조식 프리셋 부재 — 제목 박스·정부 서식 표 괘선이 생성되지 않는다.

정품 KCA 실무본(260331) header.xml을 이식해도 동일 하드페일이었다. **`맑은고딕/1300` charPr은
kordoc이 `fonts.ref`·`sizes.cham` 파라미터로 합성하는 산출물이라 정품 문서에도 없다.** 즉
하네스 후처리는 hwpx 일반이 아니라 kordoc의 스타일 테이블 관례에 결합돼 있다.

결론: hwpx 스킬은 현 상태로 kordoc을 대체하지 못한다. 대체하려면 `generate_document`가 하는 일
— **md → 개조식 section0.xml + KCA 스타일 테이블** — 을 직접 소유해야 한다. 그 조각만 만들면
postprocess(2,523줄)·validate는 한 줄도 고치지 않고 재사용된다.

## 2. 확정된 결정

| 항목 | 결정 |
|---|---|
| 범위 | ③초안작성 + ④변환 (게이트 2회: 아웃라인·초안) |
| 배포 | claude.ai 스킬 zip 업로드 (노트북 하네스와 완전 분리) |
| 의존성 | 전 구간 stdlib. python-hwpx는 되읽기 1순위 백엔드로만 쓰고, 없으면 stdlib 폴백 |
| 산출물 | 최종 hwpx 1개. 중간 파일은 샌드박스 `/tmp` |
| 룰 갱신 | 정적 탑재. 노트북에서 승격 후 zip 재배포 |
| references | md-profile·style-guide·rules·table-pool·diagram-pool 5종 통째 이식 |

## 3. 접근 — 정본 header.xml 동결 + section0.xml 직접 조립

검증된 kordoc 산출물에서 `Contents/header.xml`만 뽑아 자산으로 동결한다. 이 헤더는
charPr 44종·paraPr 34종·borderFill 30종을 갖고 있어 R008·R010·R011 앵커를 모두 충족한다.
생성기는 md-profile을 파싱해 **고정 id**를 참조하는 `section0.xml`만 쓴다.

python-hwpx `HwpxDocument` API로 조립하는 안은 배제했다 — 오늘 실패한 `create_document.py`가
정확히 그 경로였고, Skeleton 헤더 기반이라 제목박스·배너 borderFill·정부 서식 괘선을 결국
XML로 직접 만들어야 한다. 레퍼런스 슬롯 채우기 안도 배제했다(문단·표 개수가 문서마다 달라진다).

## 4. 패키지 구조

```
webapp/kca-report-hwpx/
├── SKILL.md
├── references/          md-profile.md style-guide.md rules.md table-pool.md diagram-pool.md
├── scripts/
│   ├── md2hwpx.py            ★신규
│   ├── assert_postprocess.py ★신규
│   ├── roundtrip_md.py       ★신규 (python-hwpx → 없으면 stdlib 폴백)
│   ├── postprocess_hwpx.py   하네스 복사본 (무수정)
│   ├── validate_hwpx.py      하네스 복사본 (무수정)
│   ├── prep_report_md.py     하네스 복사본 (무수정)
│   └── lint_md_profile.py    하네스 복사본 (무수정)
└── assets/
    ├── kca-header.xml        ★동결 정본 (95KB)
    └── kca-header-banner/    하네스 복사본 (71KB)
```

도식 Pool 원형 hwpx는 싣지 않는다 — §10대로 치환을 지원하지 않아 아무 코드도 읽지 않는
사장 자산이 된다(빌드 기준 5가 이를 검출한다).

`webapp/` 아래 두는 이유: `skills/` 아래 두면 노트북 플러그인이 자동 등록해 두 판이 섞인다.

## 5. 스타일 id 맵 (실측 확정)

문단:

| 클래스 | paraPr | charPr |
|---|---|---|
| 발신 | 17 `RIGHT` | 0 휴먼명조 15pt |
| □ dae | 8 `LEFT / intent -2205` | 11 HY헤드라인M 15pt |
| ㅇ yo | 9 `LEFT / left 1500 / intent -2205` | 0, 볼드 1 |
| - dash | 10 `LEFT / left 3000 / intent -1575` | 0 |
| ※ ＊ | 20 `LEFT / left 3250 / intent -1651` | 13 맑은고딕 13pt |
| 캡션 | 0 `JUSTIFY` | 0 |
| 표 래퍼 | 17 `RIGHT` (제목박스는 0) | 0 |

표 borderFill (셀 위치별 — 정부 서식 외곽 굵은선·헤더 음영·이중선이 이 배정으로 구현된다):

| 표 종류 | 표 자체 | 셀 |
|---|---|---|
| 콘텐츠 표 | 2 | 헤더행 `15/16/17`(좌/중/우), 첫 본문행 `18/19/20`, 중간행 `21/13/22`, 마지막행 `23/24/25` |
| 붙임 배너 1×3 | 2 | `26/27/28` |
| 산식 박스 1×1 | 2 | `14` |
| 제목 박스 3×1 | 1 | `11/13/12` |

나머지 서식(정렬 JUSTIFY 전환, □ 볼드, 계층 스페이서, 배너 채움·페이지분리, 캡션 내장,
괄호 13pt, 하이라이트, 머리말 배너, 패키지 정합)은 전부 postprocess가 처리한다.

## 6. `md2hwpx.py` — 3층 구조

**파서** `parse(md) -> [Block]`
md-profile 서브셋만 인식한다. 산출은 순수 데이터
(`Title / Sending / Dae / Yo / Dash / Cham / Star / Caption / Table / Banner / Formula`).
인라인은 `**볼드**`만 `[(text, bold)]` 세그먼트로 분해한다 — B안이 깨진 지점이라 파서 책임으로
명시한다. `==하이라이트==`(R040)는 마커를 **그대로 통과**시켜 postprocess가 처리하게 둔다.

**직렬화기** `render(blocks) -> section0.xml`
블록 → `hp:p`/`hp:tbl`. 스타일 id는 §5 상수 테이블(`STYLE_MAP`) 고정.

**패키저** `package(section_xml) -> base.hwpx`
동결 헤더 + 생성 섹션 + 부속 XML. 정품 순서·압축 프로파일은 postprocess의
`canonicalize_package`(R043)를 **재사용**한다 — 새로 짜지 않는다.

파서는 hwpx를 모르고 직렬화기는 md를 모른다. 예상 분량 파서 200 · 직렬화기 350 · 패키저 50줄.

## 7. 열 폭 알고리즘 (kordoc 대비 개선점)

kordoc의 열 폭 배분이 내용과 역행하는 것을 실측했다. 5열 표에서 34폭 열이 18.3mm(≈8.6폭/줄)를
받아 **4줄로 깨지고**, 23폭 열은 58.2mm(≈27폭/줄)를 받아 1줄에 여유가 남았다.

```
d_j  = 열 j 셀들의 최대 표시폭            (한글·전각 2, 영숫자 1)
하한 = max(헤더 표시폭, 8폭)               # 짧은 라벨 열 뭉갬 방지
상한 = 전체의 40%                          # 한 열 과점 방지
→ 클램프 → 나머지 비례 재분배 (수렴까지 2~3회)
→ 합계를 표 sz에 정확히 일치 (R036), 반올림 잔차는 최광열에 가산
```

위 표에 적용하면 `[12.0, 7.7, 31.4, 21.2, 27.7]%`가 되어 **최대 4줄 → 2줄**로 떨어진다.
표 총폭은 처음부터 `본문폭 − 283hu` 미만으로 내보내 `apply_fit_page_width`(R036·R042)가
멱등 no-op이 되게 한다.

## 8. 안전장치

### 8-1. `assert_postprocess.py` — 침묵 실패 차단

postprocess는 대상이 0건이어도 exit 0이다. 오늘 B안에서 `title_box found:false`,
`body_justify changed 0`, `line_fit fitted 0`이 전부 에러 없이 통과했다. 결과 JSON의 기대
하한을 검사해 하나라도 어긋나면 변환을 중단한다.

| 검사 | 기대 |
|---|---|
| `title_box.found` | `True` |
| `star_footnote.ref_charpr_id` | not None |
| `sender_size.runs_changed` | `== 1` |
| `dae_bold.runs_changed` | `== md의 □ 개수` |
| `annex_banner.title_justified` | `== 배너 수` |
| `paren_small.lead_skipped` | `== ㅇ 리드 라벨 수` |
| `body_justify.changed` | `> 0` |

기대값은 md에서 세어 넘긴다.

### 8-2. 골든 테스트

오늘 만든 A 산출물을 기준본으로 고정하고, md2hwpx 산출물과 **문단 클래스별
(paraPr, charPr, 정렬) 시퀀스**를 대조한다. 바이트 비교가 아니라 의미 비교라 §7의 열 폭 개선
같은 의도된 차이는 통과하고 스타일 회귀만 잡는다.

### 8-3. compare 기대값 테이블

오늘 A도 `count-mismatch:tables 20→22`로 exit 1이었다 — 제목박스 1 + 머리말 배너 1의 정상
가산이다. `expected_delta = {"tables": +2}`로 명시하고 그 외 불일치만 실패로 본다.

### 8-4. 스킬 배포 기준 — `scripts/build_webapp_skill.py`

여섯 기준을 전부 통과해야 `.skill`이 만들어진다(하나라도 걸리면 exit 1).

| 기준 | 내용 |
|---|---|
| 룰 최신성 | `references/rules.md`를 하네스 룰 원본에서 **매 빌드 재생성**. 손 사본을 싣지 않는다 |
| 범위 필터 | `[draft]`·`[export]` 룰만 (현재 70건) |
| 드리프트 0 | 복사한 스크립트 4종이 하네스 원본과 바이트 동일 |
| dangling 참조 0 | SKILL.md·references가 가리키는 스킬 내부 경로가 실재 |
| 사장 자산 0 | 어떤 스크립트·문서도 읽지 않는 `assets/` 파일 금지 |
| 출처 고정 | `manifest.json`에 전 파일 해시 + 룰 원본 경로·해시·건수 |

룰 원본은 기본 `rules-seed.md`(공개 안전)이고, `--rules report/_harness/rules.md`로 축적본을
실을 수 있다. **웹앱판은 세션 간 상태를 못 가지므로 재배포가 복리축적을 실무자에게 전달하는
유일한 경로다.**

## 9. 변환 흐름

```
게이트①  아웃라인 제시 → 승인                       (대화)
초안 생성 → lint_md_profile.py 통과까지 반복
게이트②  초안 전문 제시 → 승인                       (대화)
변환 (자동, 무게이트)
  prep_report_md.py        → prepared.md   (모호 입력은 exit 2로 거부)
  md2hwpx.py               → base.hwpx
  postprocess_hwpx.py --all --sender-size 12
  assert_postprocess.py                     ← 침묵 실패 차단
  validate_hwpx.py structural
  roundtrip_md.py + validate_hwpx.py compare (폴백 내장 — 항상 실행)
  → 최종 hwpx 인도
```

## 10. 범위 밖 (YAGNI)

- 이미지 주입(`patch_document` 대체)
- 도식 Pool 원형 표 치환 — 도식 마커가 나오면 `diagram-pool.md` 판정표로 GFM 표를 직접 짜는
  기존 graceful degrade 경로를 쓴다
- 서식 프로필 추출(`extract_profile` 대체)

## 11. 동결 헤더의 위치 — 한계가 아니라 설계 선택

**웹앱판 실행에 kordoc은 필요 없다.** 변환은 `md2hwpx.py` → `postprocess_hwpx.py` →
`validate_hwpx.py` 세 stdlib 스크립트만 탄다. MCP 호출 0회, 사용자 설치 항목 0개.

`assets/kca-header.xml`(95KB)은 kordoc `generate_document` 산출물에서 1회 추출한 자산이다.
헤더 자체는 문서 내용에 따라 달라지지만(같은 파라미터로 다른 문서를 변환하면 charPr 44→28,
borderFill 30→22), **생성기가 참조하는 id를 §5로 고정했으므로 닫힌 계다.** KCA 양식의
서체·크기·표 괘선은 고정이므로 이 헤더를 다시 뜰 일은 실무상 오지 않는다 — 기관이 양식
자체를 개정할 때뿐이다.

검증된 산출물을 자산으로 동결하는 것은 결함이 아니라 정상적인 선택이다(컴파일된 바이너리를
릴리스에 넣는 것과 같다). 출처만 여기에 명시해 둔다.

폰트 파일 자체를 스킬에 넣는 선택지는 없다. hwpx는 폰트를 문서에 품지 않는다 — 실측 결과
정품 한컴 문서조차 임베딩이 0이고(실무본 fontface 96종·도식Pool 156종 모두 `isEmbedded` 미설정),
`type="TTF"` + 서체 이름만 참조해 한글이 로컬 설치 폰트로 렌더한다. 휴먼명조·HY헤드라인M·
맑은 고딕은 상용 폰트라 재배포 소지도 있다.

## 12. 남는 한계

**③ 초안 룰 31종은 스크립트가 아니라 텍스트 규범이다.** 강제력이 약하고 복리축적
(lessons→rules)이 없어 웹앱판 초안 품질은 노트북판보다 낮게 수렴한다. 범위에 ③을 넣은 대가다.

**웹앱 샌드박스 전제 미확인.** zip 용량 한도와 파이썬 버전을 아직 실측하지 못했다.
python-hwpx는 더 이상 전제가 아니다 — `roundtrip_md.py`가 stdlib 폴백을 내장해 미설치
환경에서도 compare가 그대로 돈다(실측: 폴백이 python-hwpx와 동일 집계·동일 검출).
