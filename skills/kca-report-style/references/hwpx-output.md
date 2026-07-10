# MD → HWPX 변환 (최종 산출물)

스킬의 종착 산출물은 **HWPX 파일**이다. 권장 경로는 **참고양식 템플릿 병합**이다: 레터헤드(KCA 로고·슬로건 이미지)·제목 그라데이션·페이지 설정을 참고양식 원본 그대로 유지하고, 개조식 본문만 참고양식 스타일로 주입한다.

## ⚠️ 치명적 불변식 — 스타일 id는 빈틈·중복 없는 연속

HWPX/한글은 `paraPr`·`charPr`·`borderFill`의 **id를 배열 인덱스처럼 취급**한다. 참고양식은 항상 `itemCnt=N`이고 id가 **완전 연속**(빈틈·중복 없음)이다. 신규 스타일을 추가할 때 **반드시 `max(id)+1`부터 순차 id**를 부여하고 itemCnt를 그만큼 올려야 한다.

- ⚠️ **시작 번호는 컬렉션마다 다르다**(실측): `paraPr`·`charPr`·`fontface`는 **0-based**(0..N-1), `borderFill`은 **1-based**(1..N). borderFill에 id=0을 넣지 말 것. 실무상 `max(id)+1`만 지키면 base와 무관하게 안전.
- 큰 임의 id(예: 300)를 쓰면 한글이 `IDRef=300`을 **못 찾고 기본값으로 폴백** → **간격·정렬·테두리가 조용히 무시된다**(파싱은 되나 화면에 미적용). 실제로 이 버그로 문단 간격이 적용되지 않았음.
- **자동 검증**: `python3 scripts/validate_hwpx.py <파일.hwpx>` — itemCnt 일치·연속성(base 무관)·모든 IDRef 존재 범위·zip/xml 무결성을 한 번에 검사.
- 주의: HWPX는 LibreOffice·QuickLook에서 렌더링 불가 → 최종 시각 확인은 한컴에서. 위 구조 검증으로 사전 판정.

## 권장 — 참고양식 템플릿 병합 (build_from_template.py)

```
python3 scripts/build_from_template.py <generate_document_본문.hwpx> <최종.hwpx> \
  --title "제목" --date "< '26. 7. 3.(목), 부서명 >"
```

- 베이스 = `assets/reference-form-교육계획안.hwpx`. 참고양식의 header(전 스타일·글꼴), content.hpf(이미지 등록), BinData(로고 image3·슬로건 image4), 제목 그라데이션 3행 표, 페이지 설정을 **그대로 유지**.
- 본문은 generate_document 산출물에서 추출해 참고양식 계층 스타일 ID로 재지정. 이중기호 `○ ※`→`※` 정리.
- **문단 위 간격**(`SPACING_DEFS`, HWPUNIT 1pt=100): □ 위 10pt·ㅇ 위 6pt(□↔ㅇ)·**- 위 3pt(ㅇ↔-)**·※ 위 3pt(-↔※). 참고양식 계층 paraPr(□42·ㅇ38·-73·※86) 복제 후 **max+1부터 순차 id** 부여.
- **계층 들여쓰기**(참고양식 실측): 여백이 아니라 **텍스트 선두 공백 + 계층별 hanging intent(paraPr)** 조합. 선두 공백 `LEAD` = □0·ㅇ1·-3·※1칸. hanging intent는 참고 paraPr에 내장(□42=−3580·ㅇ38=−3001·-73=−3585). `-`는 참고 paraPr 73 직접 사용.
- **본문 데이터표**(원본 커리큘럼 표 스타일): 헤더행(rowAddr=0) = **#FFF7CC 음영** + **12pt KoPub돋움체 Bold(charPr77)** + CENTER; 본문셀 = **11pt KoPub돋움체 Medium(charPr8)** + CENTER. 표 pos horzAlign=CENTER, 캡션 `[ ]` 가운데.
- **표 바깥 좌우 세로선 제거**: 첫 열 left=NONE, 마지막 열 right=NONE(안쪽 세로선·모든 가로선·헤더음영 유지). 열 위치별 신규 borderFill(45~48, 순차 id) — `add_table_borderfills`가 colAddr로 첫/끝 열 판별해 적용.
- **계층별 글꼴·크기는 `references/style-spec.md`(SSOT) 단일 표를 따른다.** 아래는 요약이며 상충 시 SSOT가 우선.
- ⚠️ **native ≠ applied 구분**(과거 문서 모순의 원인): 참고양식 원본값(native)과 이 스킬이 의도적으로 적용하는 값(applied)은 다르다.
  - **`※`**: applied = **12pt 맑은고딕(charPr49)** ← 의도적 재지정. native는 15pt 휴먼명조(charPr102). 적용 출력에서 `※`와 각주 `*`는 charPr49를 공유.
  - **캡션 `[ ]`**: applied = **12pt 휴먼명조(charPr42)**. native는 13pt KoPub돋움체 Bold(charPr63).
  - □·ㅇ·-는 native=applied(□ HY헤드라인M15 / ㅇ·- 휴먼명조15).
- 마커 정규화: generate_document의 `○`(U+25CB)를 원본 자모 **`ㅇ`(U+3147)**로 치환(ㅇ 계층만).
- 제목·날짜 텍스트만 교체. **이미지·그라데이션을 새로 그리지 않는다.**
- 참고양식 교체 시 스타일 ID를 재측정(`python3 scripts/validate_hwpx.py <양식.hwpx> --dump-styles`로 charPr 크기·글꼴 덤프)해 `REF_CHAR`·`SPACING_DEFS`·SSOT 갱신 필요.

> 검증: 병합 후 `validate_hwpx.py`(구조)·`parse_document`(내용)·XML well-formed·zip testzip으로 확인. 실측 결과 □ HY헤드라인M15·ㅇ/- 휴먼명조15·※ 맑은고딕12·표 헤더 KoPub돋움체Bold12·표 본문 KoPub돋움체Medium11, 로고·슬로건 이미지·그라데이션 유지 확인됨.

## 대안 — generate_document 단독 (템플릿 없을 때)

참고양식 없이 단일 파일만 필요하면 아래 경로. 단 레터헤드 이미지·정확한 그라데이션은 재현 불가.

## 1단계 — generate_document

```
mcp__kordoc__generate_document(
  markdown = <확정된 개조식 MD>,
  output_path = "/절대경로/파일명.hwpx",
  preset = "보고서",      # 또는 "계획서"
  font = "myeongjo",      # 함초롬바탕(명조)
  body_pt = 15
)
```

동작(실측 검증됨): 마크다운 **중첩 리스트가 항목부호로 자동 매핑**된다.
- 최상위 `-` → **`□`**, 1단계 들여쓰기 → **`○`(ㅇ)**, 2단계 → **`-`**.
- 함초롬바탕 적용, 제목 ~20pt / 본문 15pt. GFM 표 → 한글 표, **볼드** 반영.

### 권장 매핑 — 섹션을 최상위 리스트로 (검증 완료)

KCA 실제 문서는 섹션 표제도 `□ 추진 배경`처럼 **`□` 기호**를 단다. 이를 재현하려면 `##` 헤딩이 아니라 **섹션을 최상위 리스트 항목**으로 둔다. 그러면 `□ 섹션 → ○ 항목 → - 세부`로 KCA 계층과 정확히 일치.

```markdown
# 2026년도 ○○ 계획(안)

< '26. 7. 3.(금), AI디지털심화팀 >

- 추진 배경
  - AI 활용 확산에 따른 전 직원 역량 강화 필요성 증대
  - 수요조사 결과 반영한 체계적 교육 운영 필요

- 추진 내용
  - (추진 방향) 초급·중급·고급 3단계 과정 운영
    - 초급: 분기별 운영, AI 윤리·동향 중심
  - (세부 과제) 자체 LLM 기반 업무 자동화

- 향후 계획
  - 초급 1차 교육 구성·실시 : '26. 6월 중
```

- 매핑 결과: `- 추진 배경`→`□ 추진 배경`, `  - 항목`→`○ 항목`, `    - 세부`→`- 세부`.
- 표·`[ 캡션 ]`은 리스트 밖 최상위에 둔다(리스트 안 중첩 불가).
- 괄호 리드·명사형·2줄 규칙은 **MD 단계에서 이미 반영**돼 있어야 한다(변환기는 문체를 고치지 않음).

## 2단계 — postprocess.py (필수)

`generate_document`(프리셋)는 아래를 못 잡는다. `scripts/postprocess.py`가 생성물 HWPX의 XML을 표적 교정한다.

```
python3 scripts/postprocess.py <생성물.hwpx> <최종.hwpx>
```

교정 항목(실측 검증됨):

| 문제 | 프리셋 결과 | 후처리 결과 |
|---|---|---|
| 제목 | 무박스 20pt 함초롬바탕 | 테두리 박스 + 18pt HY헤드라인M |
| 발신정보 `< >` | 15pt 함초롬바탕 | 12pt 휴먼명조 |
| `□` 섹션 | 15pt 함초롬바탕 | 15pt HY헤드라인M |
| `ㅇ`·`-` | 15pt 함초롬바탕 | 15pt 휴먼명조 |
| `※` | 15pt 함초롬바탕 | 12pt 맑은 고딕 |
| 표 캡션 `[ ]` | 15pt | 13pt 휴먼명조 |
| 표 내부 셀 | 15pt | 11pt 휴먼명조 |
| 이중 기호 `○ ※` | `○ ※ …` | `※ …` |

추가 레이아웃 정합(참고양식 실측 대조로 확정):

| 항목 | 참고양식 | 적용 |
|---|---|---|
| 페이지 여백 | 좌우 15mm·상하 10mm(header 15·footer 10) | 동일 적용 |
| 발신정보 정렬 | 우측 | 우측 |
| □ 정렬 | 좌측 | 좌측 |
| 계층 들여쓰기 | 전부 flush(좌0·intent0), 마커로만 구분 | flush로 통일 |
| 제목 박스 | 3행1열 표(상단 그라데이션 바·제목·하단 역그라데이션 바), 외곽 0.12mm | **동일 3행1열 표 이식**(treatAsChar, secPr 보존) |
| 제목 그라데이션 | LINEAR 90° `#3057B9`↔`#DFE6F7` (상단 정방향·하단 역방향) | 동일 gradation borderFill |

동작 원리: HANGUL fontface에 글꼴 3종 추가 → 계층별 charPr 생성 → section run을 **선두 마커(□/○/-/※/`<`/`[`)로 판별해 재지정** → 마커별 paraPr를 flush·정렬 교정 → 발신정보는 우측정렬 신규 paraPr로 재지정 → pagePr 여백 교체 → 제목 문단 테두리 박스 → `○ ※`→`※`. mimetype 무압축 유지로 재패킹.

> 검증: 정식 XML 파서로 참고양식과 결과물의 스타일 프로파일(여백·계층별 글꼴/크기/정렬/들여쓰기)을 대조해 일치 확인. 제목만 표 셀 대신 문단 테두리(시각 동등, 음영 없어 차이 없음).

> ⚠️ `generate_document` 출력 구조를 전제로 한 정규식 표적 치환이다. 프리셋/버전이 바뀌면 스크립트 정규식 점검 필요. **실행 후 반드시 parse_document로 재검증**(손상·내용 보존 확인).

### 남은 한계

- **계층별 폰트 차등**은 참고양식 자체가 하지 않음(□/ㅇ/- 모두 15pt 플랫). 계층 구분은 기호+들여쓰기. 굳이 원하면 postprocess에 계층별 charPr 재지정 로직 추가 가능(참고양식과는 달라짐).
- **소제목 굵게**: 마크다운 `**텍스트**` 볼드는 반영되나 별도 계층기호는 안 붙음.

## 폰트·서식 스펙 (postprocess 폴백 경로)

> **전체 스펙은 `references/style-spec.md`(SSOT)를 따른다.** 아래는 폴백 경로(`postprocess.py`) 요약. 권장 경로(참고양식 병합)와 캡션(13pt vs 12pt)·표셀 글꼴(휴먼명조 vs KoPub돋움체)이 다르다 — SSOT 참조.

| 요소 | 크기 | **글꼴** |
|---|---|---|
| 제목 | 18pt | **HY헤드라인M** (+테두리 박스) |
| 발신정보 `< >` | 12pt | **휴먼명조** |
| `□` 섹션 | 15pt | **HY헤드라인M** |
| `ㅇ`·`-` 본문 | 15pt | **휴먼명조** |
| `※` 주석 | 12pt | **맑은 고딕** |
| `[ 표 캡션 ]` | 13pt | 휴먼명조 *(권장 경로는 12pt)* |
| 표 내부 셀 | 11pt | 휴먼명조 *(권장 경로는 KoPub돋움체)* |

**핵심**: 계층 구분은 크기가 아니라 **글꼴**로 한다(□=헤드라인 고딕, ㅇ/-=명조, ※=고딕 소). `generate_document`는 전부 함초롬바탕 15pt로 통일하므로, `postprocess.py`가 위 글꼴을 주입(HANGUL fontface에 휴먼명조·HY헤드라인M·맑은 고딕 추가)하고 마커별 run에 재지정한다. 계층별 스타일은 스크립트 상단 `STYLE` dict로 조정하되 **SSOT와 동기화**한다.

## 양식 정합이 중요할 때 — patch_document 대안

`generate_document`가 특정 양식(여백·머리말·도장칸·고정 표)을 정확히 못 맞추면, **원본 양식 HWPX에 텍스트만 치환**한다.

```
mcp__kordoc__patch_document(
  file_path = "<원본 양식.hwpx>",
  edited_markdown = <parse_document 출력을 편집한 MD>,
  output_path = "/절대경로/결과.hwpx"
)
```

⚠️ **제약**: patch_document·fill_form은 **블록 추가/삭제·표 구조 변경 미지원**. 항목(ㅇ/-) 개수나 표 행이 가변인 일반 보고서에는 부적합 → 그런 경우 generate_document 사용. patch는 **고정 레이아웃 양식**(빈칸 채우기)에만.

## 필수 검증 (변환 후)

1. `mcp__kordoc__parse_document(생성물.hwpx)`로 재파싱.
2. 확인: 계층기호(□/ㅇ/-) 매핑 정확, 표 구조 보존, 명사형·2줄 유지, 제목·발신정보 위치.
3. 어긋나면 MD 수정 후 재생성(문체 문제) 또는 patch 경로 전환(양식 문제).
