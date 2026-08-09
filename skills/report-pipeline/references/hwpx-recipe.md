# hwpx-recipe — md→hwpx 변환 절차서

> 대상: `/report-export`(spec §6·§8-④)가 실행하는 변환 파이프라인. 입력은 게이트②에서 승인된
> `20_draft.md`(md-profile 준수, `md-profile.md` 참조). **원칙: "작성된 md 그대로" 변환** —
> 내용·구조·표·각주가 hwpx에 1:1로 재현되어야 한다(무손실). 초안 단계의 상시 lint 덕에 이
> 파이프라인은 "이미 통과한 입력"만 받는 것이 기본값이고, 왕복 QA는 확인 절차로 경량화된다.
>
> 결정론 스크립트(`prep_report_md.py`·`validate_hwpx.py`·`check_image_size.py`)는 stdlib-only
> 이고 MCP를 직접 호출할 수 없다 — hwpx 생성·되읽기는 kordoc MCP를 **모델이** 호출하고, 그
> 전후의 정규화·검증만 스크립트가 담당한다.

## 0. 사전조건

- 입력: `{work_dir}/20_draft.md` (게이트② 승인본, lint 통과 상태).
- `state_dir`(`harness_config.state_paths`)의 `rules.md`·`lessons.jsonl` 경로를 확보해 둔다 —
  실패 유형은 §6에서 여기 기록한다.
- 설정(`load_config`)의 `template_hwpx`가 지정돼 있으면 §2에서 서식 프로필을 병합한다.

## 1. prep 정규화 (무손실 정규화, 모호 입력 거부)

```
python3 skills/report-pipeline/scripts/prep_report_md.py \
    {work_dir}/20_draft.md -o {work_dir}/40_prepared.md
```

- `prep_report_md.py`는 의미 콘텐츠를 보존한다 — 단일행 HTML 주석 제거·문맥 확인된 구분선
  제거·각주 마커 전각 정규화만 수행하며, 삭제 문자수는 회계로 검증되고 모호한 입력(다중행
  주석·Setext 패턴)은 exit 2로 거부한다.
- **모호한 입력은 조용히 처리하지 않고 거부한다**(`PrepError`) — "모른다"를 명시적 실패로
  만드는 설계다. 대표 거부 사유:
  - `multiline-comment`: 여는 `<!--`와 닫는 `-->`가 다른 줄에 걸침(md-profile §2-3의
    "HTML 주석은 한 줄로만" 정책이 여기서 하드 실패로 강제된다).
  - `setext-ambiguous`: 구분선(`---`/`***`/`___`)의 앞뒤가 빈 줄이 아니어서 Setext 제목인지
    구분선인지 판정 불가.
  - `deletion-accounting-mismatch`: 삭제 문자 수 회계가 실제 삭제량과 어긋남(회귀 트립와이어).
- **exit 2**(`FATAL: {reason} at line {line} — 모호한 입력 거부`, stderr)면 **변환을 중단**하고
  사용자에게 사유·줄 번호를 그대로 보고한다. 20_draft.md를 수정해 원인을 제거한 뒤 이 단계부터
  재시도한다 — 다음 단계로 넘어가지 않는다.
- exit 0(`OK {work_dir}/40_prepared.md`)이면 §2로 진행.

## 2. 문서 생성 — kordoc `generate_document`

`template_hwpx`가 설정돼 있으면 먼저 서식 프로필을 추출해 병합 재료로 쓴다.

```
mcp__kordoc__extract_profile(
    hwpx_path="{template_hwpx}",
    output_path="{work_dir}/format-profile.json")

(선택) 추출 JSON을 사람이 읽는 프로파일 md로 렌더하려면 보조 헬퍼를 쓴다 —
`python3 skills/report-pipeline/scripts/extract_format_profile.py {work_dir}/format-profile.json -o {state_dir}/format-profile.{기관}.md`
```

도식 마커(`도식: {패턴ID}`)가 본문에 있으면, `generate_document` 호출 전에 md 텍스트 단계에서
치환한다 — `diagram-pool.md` 판정표로 고른 패턴ID의 원형 표 구조를 도식 Pool hwpx
(`harness_config` 출력의 `assets_dir` 아래 `도식Pool-경량.hwpx` 번들 사본, 로컬 원본 form/이
있으면 그것도 가)에서 `parse_document`로 추출해 슬롯을 채운 뒤, GFM 표로 재구성해
`40_prepared.md`의 마커 자리에 병합한다(md-profile의 표 규격 안에서 조립). 원형 hwpx가 어디에도
없으면 diagram-pool.md 판정표만으로 GFM 표를 직접 재구성한다 — 치환은 graceful degrade 대상.

**변환 입력 문법 (R007·R016·R040)**: ㅇ 계층의 괄호 리드는 `**(한 계)**`처럼 볼드 래핑해 전달한다(R016).
하이라이트 마커 `==특히 강조==`(R040)는 **그대로 리터럴로 전달**한다 — kordoc은 이 표기를
해석하지 않고 텍스트로 통과시키며, §3.5 postprocess `apply_highlight`가 마커를 제거하고
노란 음영+볼드 run으로 치환한다.
 generate_document에는 리터럴 개조식 기호가 아니라 **리스트 깊이
문법**으로 변환해 전달한다 — `□ X`→`- X`, ` ㅇ X`→`  - X`(2칸), `   - X`→`    - X`(4칸),
**제목(첫 줄)은 `# 제목` h1로 전달**(평문 첫 줄은 제목으로 인식되지 않아 제목 박스·20pt가
적용되지 않는다 — R010).
리터럴 기호를 그대로 넣으면 하위 대시가 상위 부호로 평탄화된다(왕복 compare가 검출하는 유형).
※·＊ 라인·표·캡션은 그대로 둔다. **발신 줄은 `<right>< '연. 월. 일.(요일), 본부 팀 ></right>`로
래핑**해 전달한다(R012 — kordoc `generate_document`의 우측정렬 출처행 문법. 미래핑 시 좌측/양쪽
정렬로 떨어져 양식과 어긋난다. 근거: 양식 바이너리 실측, 20260722건). 이 변환본은
`43_convert_input.md`로 저장한다(40_prepared는 compare 기준으로 불변 유지).

**KCA 프로파일 파라미터 (R008 — 필수 전달, format-profile.kca.md §2 매핑)**:

```
mcp__kordoc__generate_document(
    markdown="{43_convert_input.md 전문 — 도식 마커 치환 완료본}",
    output_path="{work_dir}/final/{제목}.hwpx",
    preset="보고서",
    body_pt=15,                      # ㅇ·- 본문 15pt
    fonts={"heading": "HY헤드라인M",  # □·제목 계열
           "body": "휴먼명조",        # ㅇ·- 본문
           "ref": "맑은고딕",         # ※·＊ 참고
           "table": "맑은 고딕"},     # 표 셀
    sizes={"dae": 15,                # □ 15pt
           "cham": 13,               # ※·＊ 13pt
           "table": 12,              # 표 12pt
           "bodyTitle": 20},         # 제목 박스 20pt (HY헤드라인M 20pt)
    bullet2="ㅇ",                    # 2단 부호 = 양식의 ㅇ (스키마 설명은 ᄋ이나 실 enum 값은 ㅇ U+3147)
    body_title_box=True,             # 제목 표구조(박스) — 양식 제목부 재현
    line_spacing=160,                # 편집용지 줄간격 160%
    profile_path="{work_dir}/format-profile.json")   # template_hwpx 설정 시에만 전달
```

- `preset="보고서"`(1페이지 요약보고서 프리셋), `font="myeongjo"`(휴먼명조 계열),
  `body_pt=15` — spec §6-3 "명조 15pt" 확정값과 동일(해당 프리셋 기본값이기도 하지만 명시
  전달로 회귀를 막는다).
- `template_hwpx` 미설정 시 `profile_path`를 생략한다 — 단 위 fonts·sizes 등 KCA 프로파일
  파라미터는 **profile_path와 무관하게 항상 전달**한다(R008).
- **＊ 각주 후처리 (R011)**: kordoc은 ※ 시작 문단만 참고 스타일로 인식하고 전각 ＊는 본문
  스타일로 남는다 — §3.5 `postprocess_hwpx.py --star-footnote`(또는 `--all`)로 일괄 치환한다
  (예전에는 이 치환을 수동 zip 패치로 매번 다시 짰다 — 이제는 스크립트 1회 호출로 대체).
- **스타일 사용 검증 (R010 검증부)**: 폰트 검증은 선언(fontface·charPr) 확인으로 끝내지 않는다 —
  대표 문단(제목·□·ㅇ·대시·※·＊·표 헤더)별로 section0.xml의 run `charPrIDRef`가 의도한
  charPr(폰트·크기)를 실제 참조하는지 확인한다. kordoc 렌더러는 generate 산출물 미리보기를
  지원하지 않을 수 있어(환경 한계) 이 XML 사용 검증이 시각 확인의 대체 수단이다.
- **붙임(R009)**: 본문에 붙임이 있으면 3열 배너 표(`| 붙임 1 | | 제목 |`, 단수는 `| 붙 임 | | 제목 |`)
  형식을 md 단계부터 유지해 변환한다 — 배너를 일반 문단으로 풀지 않는다.
- **kordoc 자체 표기법 경고**(4자리 연도·콜론 붙임 권장 등)는 `style-guide.md`의 기관 관례(`'26.` 축약·` : ` 콜론형)가 우선이므로 **무시하고 진행한다** — 경고이지 오류가 아니다.
- **2단 불릿 ㅇ(U+3147)을 원문 그대로 유지**하려면 `generate_document`에 `bullet2` 파라미터를 명시한다(미지정 시 ○로 정규화되며 compare의 points 집계는 두 기호를 동일 취급).

## 3. 이미지 주입 — 규격 판정 → `patch_document`

본문의 이미지 마커(`도해: {id}`, 출처 캡션 병기)마다 후보 이미지를 규격 판정한다.

```
python3 skills/report-pipeline/scripts/check_image_size.py \
    research/fetched/{주제슬러그}/images/{파일명} --max-w-mm 170 --max-h-mm 90 --dpi 96
```

- 출력 JSON: `{"w_mm":..,"h_mm":..,"fits":bool,"scale_to_fit":..}`.
- **exit 0**(규격 이내, `fits=true`): 주입 대상.
- **exit 1**(`fits=false`): `scale_to_fit` 비율로 축소해도 판독 가능하면 축소 재판정, 아니면
  차용 포기 — 텍스트 요약 + 출처 각주로 대체(마커 삭제).
- **exit 2**(포맷 오류 등): 해당 이미지는 건너뛰고 사유를 보고.

**통과분만** 주입한다. 방금 생성한 hwpx를 되읽어 이미지 마커 문단을 이미지 구문으로 치환한
편집본을 만들고 `patch_document`로 원본 서식(표·글꼴·도장칸)을 유지한 채 텍스트만 치환한다.

```
mcp__kordoc__patch_document(
    file_path="{work_dir}/final/{제목}.hwpx",
    edited_markdown="{parse_document로 얻은 마크다운에서 도해 마커 문단만
                      출처 캡션이 붙은 이미지로 치환한 전체 텍스트}",
    output_path="{work_dir}/final/{제목}.hwpx")
```

- `patch_document`는 블록 추가/삭제를 지원하지 않는다 — 이미지 마커 문단이 이미 존재하는
  자리에서만 치환이 성립한다(§7-1 배치 승인이 게이트①에서 이미 확정돼 있어야 하는 이유).
- 이미지가 없으면 이 단계는 생략하고 §3.5로 진행.

## 3.5. 후처리 — `postprocess_hwpx.py --all`

이미지 주입까지 끝난 hwpx를 양식 정합으로 후처리한다. §4 구조 검증 **이전**에 실행한다(스크립트가
직접 zip을 재작성하므로, 재작성 결과를 검증 대상으로 삼아야 한다).

```
python3 skills/report-pipeline/scripts/postprocess_hwpx.py \
    {work_dir}/final/{제목}.hwpx --all
```

`--all`은 `--star-footnote`·`--spacing`·`--header-banner`에 더해 발신 줄 12pt(R018)를 기본
적용한다(코드 상수 `SENDER_SIZE_PT`, 프로파일과의 일치는 `test_value_drift.py`가 강제).
과거에는 `--sender-size 12`를 매번 별도 지정해야 했고 빠뜨리면 R018 미적용본이 §4 검증을
통과해 버렸다 — 그 복제·누락 위험을 기본값 승격으로 제거했다.

- **`--star-footnote` (R011)**: ＊ 시작 문단의 run `charPrIDRef`를 참고 스타일(header.xml에서
  height=1300·fontRef=맑은고딕 계열 탐색)로 치환한다. kordoc은 ※만 참고 스타일로 인식하고
  전각 ＊는 본문 스타일로 남는 결함의 스크립트화 — 기존 수동 zip 패치를 대체한다.
- **`--spacing` (R013·R038)**: 계층 전환 지점(발신줄→□·□→ㅇ·ㅇ→-·-→＊·＊→표·블록 구분,
  그리고 ※·＊ 단서/각주 뒤 ㅇ 복귀 6pt=R038)의
  간격을 원본 KCA 양식 실측값(스페이서 문단 방식 — 문단모양 자체 간격이 아니라 글자크기를
  줄인 빈 문단)으로 재현한다. 전환 지점에 이미 빈 문단이 있으면 그 charPr 높이를 치환하고,
  없으면(= kordoc `generate_document` 산출물의 표준 상태) 새 스페이서 문단을 삽입한다. 확정값은
  format-profile.kca.md §7 참조.
- **`--sender-size N` (R018)**: 발신 줄(`classify=="sending"`) 문단 run들의 charPr을 폰트는
  유지한 채 높이만 N(pt)로 치환한다. `--all`이 KCA 양식 실측 확정값 12pt(`SENDER_SIZE_PT`)를
  기본 적용하므로 별도 지정은 다른 값으로 재정의할 때만 쓴다.
- **표 캡션 내장 (R034, '26.7.28 사용자 확정)**: 표 바깥 캡션 문단(`[ … ]`)을 바로 다음
  콘텐츠 표의 `hp:caption`(side=TOP — 260331 실무본 실측 원형: outMargin 다음 위치)으로
  옮기고 CENTER+볼드를 배정한다(크기는 R023 12pt 일괄 처리). 캡션↔표 사이 스페이서는
  제거되고 전환 간격은 X→표로 승계된다(＊→표 10pt, ㅇ/대시/※→표 6pt). 스페이서 계산 전에
  실행된다. ※ kordoc reflow 렌더는 hp:caption을 그리지 않는다 — 캡션 육안 확인은 한글 필요.
- **표 배치 정렬 (R015 정정·R035, '26.7.28 사용자 확정)**: 본문 콘텐츠 표 래퍼 문단 RIGHT,
  붙임·참고 배너 표 LEFT, 제목 박스 CENTER 유지.
- **본문 양쪽 정렬 (R032, '26.7.28 사용자 확정)**: □·ㅇ·대시 문단 paraPr align을 JUSTIFY로
  치환한다. ＊·※·캡션·발신 줄은 기존 정렬 유지.
- **본문 괄호 13pt (R033·R039, '26.7.28 사용자 확정)**: □·ㅇ·대시 문단 서술 중 `(…)` 구간을
  run 분할로 13pt 치환한다(폰트·볼드 유지). 괄호 구간은 **문단 전체 텍스트 기준**으로 찾아
  run 경계를 넘어도 걸친 run들을 각각 분할·치환한다(볼드 run 안 괄호는 13pt 볼드 — R039,
  문장 안 볼드로 run이 쪼개져 약 70%가 건너뛰어진 결함의 항구 수정). ㅇ 선두 괄호 리드(R016
  라벨)는 제외(15pt 볼드 유지), 표 셀·＊※ 각주 비대상. `cross_run_skipped`는 분할 불가
  run(그림 등 중첩 개체)에 걸친 구간만 남으며 통상 0이어야 한다.
- **`==문구==` 노란 음영 하이라이트 (R040, '26.7.28 사용자 확정)**: 초안 '특히 강조' 표기
  (md-profile §1-3)를 postprocess `apply_highlight`가 마커 제거 후 해당 구간 run에 charPr
  `shadeColor="#FFFF00"`+볼드 복제본으로 배정한다(260331 실무본 'AI검증 후 최종결과물 변환'
  run 실측 인코딩 — hwpx XML 색은 #RRGGBB 직독, COLORREF 바이트 반전은 hwp OLE 전용).
  표 셀 포함 전 문단 처리(마커 잔존 방지), 짝 없는 `==`는 그대로 두고 보고(lint
  `highlight-unpaired`가 초안 단계 1차 방어, compare `markdown-leftover`가 최종 검출).
- **서술 중 ＊ 위첨자 (R031, '26.7.28 사용자 확정)**: 용어 뒤 ＊(예: 바이브코딩＊)를
  `<hh:supscript/>` 추가 charPr 복제본의 별도 run으로 분리한다(실무본 실측 인코딩 —
  높이·offset 유지, 한글이 축소 렌더). 선두 ＊ 각주 문단은 평문 유지.
- **제목 박스 상단여백 — 미세 치환 (R022)**: `--spacing` 묶음이 제목 박스(첫 □ 이전 표) 앵커
  문단의 줄간격을 100%로 치환하고 표 outMargin top을 0으로 조인다. **상단 얇은 행은 양식
  원형의 배경 밴드이므로 행 삭제 금지**(행 삭제 시 그라데이션 소실 — 20260724건 회귀 확정).
  ※ '26.7.28 정정: 이 치환은 미세 기하 보정일 뿐, 사용자가 보는 상단 여백의 실체가 아니다 —
  치환 적용본의 제목표 위치는 한컴 저장 실무 보고서와 0.2mm 이내로 이미 일치한다.
- **KCA 머리말 배너 주입 (R030·R041)**: 머리말 부재 시 실무 보고서에서 이식한
  KCA 로고 배너 표(1×2, 높이 11.3mm — 로고 png+슬로건 bmp)를 `hp:header` ctrl로 주입해
  위 10mm+머리말 15mm(R020 양식 규격) 영역을 채운다(`--header-banner`, --all 포함).
  자산은 `assets/kca-header-banner/`
  (fragment.xml·resources.xml·이미지 2종), 주입 시 borderFill/paraPr/charPr id 재배정 +
  BinData 추가 + content.hpf manifest 등록까지 수행. **주입 시 앵커 문단 paraPr의
  lineSpacing을 PERCENT 100으로 강제하고 subList textWidth를 현 문서 본문 폭으로
  보정한다(R041)** — 도너(260331, 좌우 15mm) 앵커 150%가 배너 줄 높이를 머리말 영역
  15mm 초과(17.0mm)로 부풀려 본문 전체를 ≈4.6mm 밀어낸 것이 제목표 상단 여백의 실원인
  ('26.7.28 실기동 A/B: 100% 치환 시 실무본과 0.3mm 이내 일치). 배너 셀 내부 문단(160%)은
  건드리지 않는다. 문서에 hp:header가 이미 있으면 주입은 스킵하되 앵커 기하 보정은 소급
  적용한다(멱등). 편집용지 여백 축소로 대응하지 말 것(양식 규격 위반).
  '26.7.28 4차 재검증: 주입 서브트리는 실무본과 id 재배정 외 동일, 배너 라인 39.4pt <
  머리말 영역 42.5pt로 본문 밀림 없음. 앵커 문단([표1] 구조) 기여도 실측 0pt — 본문 쪽
  제거 가능한 잔여 여백 없음. kordoc reflow 렌더는 머리말·hp:caption·pageBreakBefore를
  그리지 않으므로 렌더만으로 상단여백·캡션·배너 페이지 시작을 판정하지 말 것.
- **표 폭 본문 정합 (R036·R042, '26.7.28 6차 정정)**: 표 총 폭(sz + outMargin 좌우)이
  본문 폭 − 283 hu(1.0mm)를 넘으면 표 폭·셀 폭·내부 그림을 같은 비율로 축소해 본문 폭
  **'미만'**으로 맞춘다(`apply_fit_page_width`. 셀 폭 합 == 표 sz 정확 일치).
  R036의 '이내'(정확히 같게)가 slack 0을 만들면 같은 문단에 선행 요소가 있을 때 한컴이
  표를 다음 줄로 내려 표 위에 15pt 빈 줄이 생긴다 — 6차 확정된 제목표 상단 여백의 정체
  (실기동 30.29 → 25.02mm, R042). 그림 축소 시 파생 캐시(scaMatrix e1/e5 = curSz/orgSz·
  rotationInfo center = curSz/2)도 재계산한다(스테일 방지). slack이 이미 283 hu 이상인
  표는 비대상(멱등). 이 결함은 정적 XML로 판정 불가 — 한글 실기동 계측 필요.
  **이 처리만은 표 폭 정합·패키지 정합(아래 R043)과 함께 플래그와 무관하게 항상 실행된다** —
  `process_file`이 모든 조건 블록 바깥에서 호출한다(실측). `--sender-size`만 준 호출에서도
  표 폭이 조정되므로, 폭 조정을 원치 않는 중간 산출물에는 이 스크립트를 아예 돌리지 말 것.
- **패키지 정합 (R043, '26.7.29 내부망 반입 거부 건)**: kordoc 산출물은 hwpx **최소
  패키지**(mimetype·container.xml·content.hpf·header·section·PrvText)라서 hwpx 확정
  마커인 **version.xml이 없고**, 디렉터리 엔트리 3개(`META-INF/`·`Contents/`·`Preview/`)·
  전량 STORED라는 정품에 없는 지문을 가진다 — mimetype+container.xml 구조는 EPUB류 일반
  OCF와 같아 심층 구조 검사를 하는 반입 시스템(내부망 자료교환 등)이 hwpx로 판별하지 못하고
  octet-stream → 미등록 확장자로 반려한다(타 hwpx는 동일 시스템에서 정상 유통 — 시스템이
  아니라 산출물 문제, 사용자 확정). `canonicalize_package`가 **플래그 무관 상시** 적용:
  version.xml·settings.xml(content.hpf manifest 등재)·META-INF/manifest.xml·container.rdf
  보강(한컴 정품 '도식 Pool.hwpx' 실측 정본 템플릿), 디렉터리 엔트리 제거, container.xml
  rootfiles 정본화(PrvText·container.rdf), 엔트리 순서·압축 프로파일(mimetype·version.xml·
  미디어 STORED, XML DEFLATED)을 정품 저장기와 일치시킨다. 멱등(2회 실행 바이트 동일).
  `validate_hwpx.py structural`이 OCF 시그니처(첫 엔트리 mimetype STORED·offset 0·extra 0·
  38바이트째 평문 `application/hwp+zip`)와 필수 멤버를 검증해 회귀를 차단한다.
  **'26.7.29 보강**: 한글 재저장본에 삽입되는 기본 빈 JScript 스텁(`Scripts/headerScripts`·
  `sourceScripts` — 확장자 없는 멤버 + hpf에 `application/x-javascript`로 등재되는
  활성콘텐츠)도 반려 사유다(실반려 오류 문구 'header script'가 이 멤버명). canonicalize가
  Scripts/ 전량 제거 + hpf item/itemref 등재 철회를 함께 수행한다. 기존 산출물·재저장본은
  `postprocess_hwpx.py <파일> --spacing`만 다시 돌려도 소급 정합된다(멱등).
- **표 캡션·셀 12pt (R023)**: 캡션(내장 hp:caption 포함)과 본문 콘텐츠 표(제목 박스 제외) 셀
  문단의 charPr을 폰트 유지·높이 1200(12pt)으로 치환한다.
- **□ 절 제목 볼드 (R024)**: dae 문단 run charPr에 `<hh:bold/>` 변형을 배정한다.
- **☞ 계층 처리 (R025)**: ☞ 선두 문단을 ＊·※와 동일하게 5칸 리터럴 띄어쓰기 + 내어쓰기
  (left=0·intent=-6000, 15pt 본문 4글자 폭)로 처리하고, 인접 간격은 3pt를 준용한다.
- **붙임·참고 배너 (R027)**: 3열 배너 표(첫 셀 '붙 임'/'붙임 N'/'참고N')의 셀 글자를
  HY헤드라인M 16pt로, 앵커 문단을 pageBreakBefore=1로 처리해 양식 참고 블록처럼 별도
  페이지에서 시작시킨다. 배너 셀은 R023 12pt 강제 대상에서 제외. 셀 테두리·채움은 양식
  '참고1' 실측값을 배정한다 — 라벨 셀 4변 SOLID 0.5mm #1B1760 + 채움 #2B2D63(남색) + 흰 글자,
  스페이서 좌변만 SOLID, 제목 셀 상·하변 SOLID, 행 높이 28.3pt(2830), 셀 폭 라벨
  5968(21.1mm)·스페이서 565(2.0mm)·제목 잔여.
- **배너 제목 셀 양쪽정렬 (R037, '26.7.28 사용자 확정)**: 배너 표 제목 셀(3번째)의 문단
  정렬을 JUSTIFY로 배정한다(`apply_annex_banner` ⑤). 라벨·스페이서 셀은 셀 텍스트 가운데
  정렬(CENTER) 현행 유지 — `apply_center_cell_text`는 배너 제목 셀을 제외한다(R023의 배너
  제외와 같은 패턴). 결과 요약 `annex_banner.title_justified`로 치환 문단 수를 보고한다.
- **`--all`**은 `--star-footnote`·`--spacing`·`--header-banner` 세 플래그에 더해 발신 줄
  12pt(R018 기본값)를 켜고 zip을 1회만 재작성한다(항목 순서·mimetype 보존). 결과 요약(치환
  건수·삽입/치환 스페이서 이벤트 목록)을 JSON으로 stdout에 낸다.
- exit 0: 변경 적용 완료. exit 1: **적용한 모든 처리에서 대상 0건**(＊ 문단·전환 지점·배너·
  폭 초과 표 어느 것도 미발견 — 잘못된 파일을 가리켰을 가능성, 원인 확인).
  exit 2: 인자·파일·zip/xml 구조 오류.
- 이 단계 이후 §4 구조 검증(`validate_hwpx.py structural`)을 재실행해 zip이 여전히 정상인지
  확인한다.

## 4. 검증 — 구조 검증 + 왕복 교차대조

### 4-1. 구조 검증

```
python3 skills/report-pipeline/scripts/validate_hwpx.py \
    structural {work_dir}/final/{제목}.hwpx
```

- zip 무결성(`testzip`) + 내부 xml 전체 파싱(`ET.fromstring`) 검사.
- exit 0(`{"errors": []}`): 구조 정상. exit 1: `errors` 배열에 손상 위치 나열 — §5로 이동
  (재변환 루프).

### 4-2. 왕복 되읽기

```
mcp__kordoc__parse_document(file_path="{work_dir}/final/{제목}.hwpx")
```

결과 마크다운을 모델이 `{work_dir}/40_roundtrip.md`로 저장한다(스크립트는 MCP를 직접 호출할
수 없으므로 이 저장은 모델 책임).

### 4-3. 내용 대조

compare의 src는 40_prepared.md — prep이 마크업(주석·구분선·각주 표기)을 바꾸므로 변환 입력과
동일본을 기준으로 대조해야 오탐이 없다. draft↔prepared 정합은 prep의 삭제 회계가 별도 보증한다.

```
python3 skills/report-pipeline/scripts/validate_hwpx.py \
    compare {work_dir}/40_prepared.md {work_dir}/40_roundtrip.md
```

- 대조 항목: □ 섹션 수·ㅇ/○ 요지 수·대시 상세 수·＊ 각주 수·표 개수·표 최대 열 수·수치 표본
  (콤마·소수 정규화 후 손실분), 그리고 되읽기 텍스트에 마크다운 잔재(헤딩·구분선·백틱·`**`·
  이탤릭·취소선(`~~..~~`)·서술 중 공백-하이픈·하이라이트 마커 `==`(R040) — 8종)가
  남아있는지(AI 티 3중 장치 ③ — 변환기가 기호를 문자 그대로
  박아버리는 사고의 최종 검출선).
- **되읽기 텍스트의 밑줄 이스케이프**(`generate_document` 등)는 kordoc 파서의 정상 재현 차이로 compare가 검출하지 않는다 — 알려진 무해 차이.
- exit 0(`{"issues": []}`): 일치. §7로 진행.
- exit 1: `issues` 배열에 `count-mismatch:{항목}` / `numbers-lost` / `markdown-leftover` 등
  판정 근거와 함께 나열 — §5로 이동.

## 5. 불일치 처리 — 재변환 루프 (최대 2회)

1. `validate_hwpx.py structural` 또는 `compare`가 exit 1을 내면, `issues`/`errors` 내용으로
   원인을 판정한다(예: 도식 표 병합 중 셀 텍스트 유실, 이미지 주입으로 인한 인접 문단 손상).
2. 원인에 대응하는 수정(마커 재구성·patch_document 재호출·generate_document 재실행)을 적용해
   §2~§4를 재실행한다.
3. 이 재변환 루프는 **최대 2회**까지 허용한다(최초 시도 포함 총 3회 시도).
4. 2회 재시도 후에도 불일치가 잔존하면 **조용한 변환 손실 금지** 원칙에 따라:
   - 잔존 불일치 전체 목록(`issues`/`errors`)을 사용자에게 명시 보고한다.
   - `20_draft.md`(항상 SSOT)를 그대로 인도한다 — hwpx 변환 실패가 md 인도를 막지 않는다.

## 6. lessons 기록

변환 과정에서 발생한 실패 유형(불일치·prep 거부·이미지 규격 초과 등)은 단계 종료 시
`state_dir/lessons.jsonl`에 `gate:"convert"`로 1줄 append한다(`gate`는
`research|analyze|outline|draft|factcheck|convert` 6값 enum 중 하나 — rules.md의 `[export]`
같은 단계 태그는 rules 파일 전용이며 feedback 문자열에 중복 삽입하지 않는다).

```json
{"date":"2026-07-22","case":"{work_dir 슬러그}","gate":"convert","feedback":"도식 표 치환 후 각주 수 불일치","fix":"슬롯 치환 순서 조정 후 재변환","promoted":false}
```

- 동일 유형이 2회 이상 반복 관찰되면 회고까지 기다리지 않고 그 자리에서 승격을 제안한다 —
  사용자 승인 시 `rules.md`에 `R0NN [export]`로 반영, `md-profile.md`의 금지 목록·
  `prep_report_md.py`의 거부 규칙으로 소급 반영할지 §5(md-profile.md)의 증보 절차를 따른다.

## 7. 인도

- `{work_dir}/final/{제목}.hwpx` + `{work_dir}/40_roundtrip.md`(왕복 대조 근거) +
  대조 결과 요약을 `40_qa.md`로 정리해 함께 인도한다.
- 1회 변환(재시도 0회)으로 통과한 경우가 표준 경로 — 초안 단계 lint가 이미 변환 가능
  프로파일만 통과시켰기 때문에 재변환 루프는 예외 처리다.

---

## 부록 — 스크립트 CLI 시그니처·exit 코드

| 스크립트 | 호출 | exit 0 | exit 1 | exit 2 |
|---|---|---|---|---|
| `prep_report_md.py` | `prep_report_md.py <src> -o <out>` | 정규화 성공, `<out>` 기록 | — (사용 안 함) | `PrepError`(모호한 입력 거부) |
| `validate_hwpx.py structural` | `validate_hwpx.py structural <path.hwpx>` | 구조 정상(`errors:[]`) | 구조 손상 발견(파일 미존재·zip 손상, `errors` 목록에 담겨 exit 1로 재변환 루프) | 인자 부족 |
| `validate_hwpx.py compare` | `validate_hwpx.py compare <src.md> <rt.md>` | 전항목 일치(`issues:[]`) | 불일치 발견 | 인자 부족(파일 접근 오류 시도 exit 2) |
| `validate_hwpx.py numbers` | `validate_hwpx.py numbers <draft.md> <research_dir>` | 초안 수치 전부 근거 있음(`issues:[]`) | 근거 없는 수치 발견(`numbers-unsourced`) | 인자 부족 |
| `check_image_size.py` | `check_image_size.py <img> [--max-w-mm 170] [--max-h-mm 90] [--dpi 96]` | 규격 이내(`fits:true`) | 규격 초과(`fits:false`) | 포맷 인식 실패 등 예외 |
| `postprocess_hwpx.py` | `postprocess_hwpx.py <file.hwpx> [--star-footnote] [--spacing] [--header-banner] [--all] [--sender-size PT]` | 변경 적용 완료(요약 JSON) | 적용한 모든 처리에서 대상 0건 | 인자/파일/zip·xml 구조 오류(참고 charPr 미발견 포함) |

- `postprocess_hwpx.py` 보충: `--all` = `--star-footnote`+`--spacing`+`--header-banner`
  +발신 줄 12pt(R018 기본값, `--sender-size PT`로 재정의). 플래그를 하나도 주지 않으면
  exit 2다. `apply_fit_page_width`(R036·R042)·`canonicalize_package`(R043)는
  플래그와 무관하게 항상 실행된다.
