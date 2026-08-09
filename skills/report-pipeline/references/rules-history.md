# rules-history — 규칙 확정 경위·실측 로그 (배포 시드)

> rules-seed.md와 함께 배포되는 경위 로그의 시드다. 결번(폐지·이관) 기록이 여기 남아
> `consolidate_rules.py`·테스트가 죽은 참조와 결번을 판정한다. 운영 축적분과 함께 동기화한다.

> `rules.md`는 **따를 값**만 담는다. 그 값이 왜 그 값인지의 조사 경위·실기동 계측·폐기된 가설은
> 여기에 남긴다. 규칙 본문이 1,000자를 넘으면 이 파일로 내리고 규칙에는 `경위 → rules-history.md#R0NN`만 건다.

## R042

- R042 [export] **표 총 폭(sz + outMargin 좌우)은 본문 폭 '미만' — 여유 283 hu(1.0mm) 확보. R036('이내')의 계열 정정(R036 폐기 아님 — 폭 상한 원칙·비례 축소 메커니즘은 유지, 상한값만 정정)**: R036이 초과 표를 본문 폭과 **정확히 같게**(slack 0) 축소한 결과, 같은 문단에 표보다 앞선 요소가 있으면 한컴 엔진이 표를 다음 줄로 내려 표 위에 **15pt 빈 줄**(charPr#0 height 1500 = 5.29mm)이 생겼다 — 사용자가 6회 보고한 제목표 상단 여백의 정체는 이 줄바꿈 빈 줄이다(넘쳐서가 아니라 **딱 맞아서** 생긴 문제). 실기동 A/B 실측: slack 0 = 제목표 상단 30.29mm / 제목표 폭만 축소 = 25.03mm(여백 소멸) / 본 수정판 재계측 25.02mm·머리말 배너 좌석 불변(로고 상단 12.28→12.23mm, 한 줄 렌더 유지). 처리: `apply_fit_page_width`가 총 폭 > 본문 폭 − FIT_PAGE_SLACK(283 hu — 제목표·배너 자산의 outMargin 퀀텀과 동일한 문서 그리드 최소 단위, 시각적으로 무감지)인 표를 본문 폭 − 283으로 비례 축소한다(셀 폭 합 == 표 sz 정확 일치 유지·내부 그림 동반 축소 — R036 메커니즘 그대로). slack 0이던 머리말 배너에도 동일 적용(당장은 선행 요소가 없어 안 꺾이지만 취약 상태 해소 — 'KCA 실보고서 12건 배너 폭 == 본문 폭' 관례에서 1.0mm 이탈은 실기동 무감지 확인), slack이 이미 283 이상인 본문 표(1801)는 비대상·멱등. **위생 동반 수정**: 그림 축소 시 sz·curSz만 줄이면 파생 캐시가 도너 원값으로 스테일된다(6차 실측: kcaHdrLogo scaMatrix 0.238583 = 도너 14315×1905 잔존) — scaMatrix e1/e5 = curSz/orgSz, rotationInfo centerX/Y = curSz/2로 재계산한다(transMatrix·scaMatrix e3/e6은 offset 파생이라 불변, 실기동 렌더 정상 확인). R022(앵커 기하)·R030(머리말 부재)·R041(앵커 150%)은 전부 실재한 별개 결함이었으나 6차 확정된 이 원인(등호 slack 0)과는 다른 축이다. 이 결함은 정적 XML로 판정 불가 — 실기동 픽셀 계측이 결정타(5·6차 동일, kordoc reflow는 머리말 미렌더로 부적합). 단위 주의: 1 hu = 1/7200 inch → 283 hu ≈ 1.0mm(6차 제시 '283 hu = 0.1mm'는 환산 오기, 15pt = 1500 = 5.29mm와 교차 검증) (근거: '26.7.28 사용자 확정 — 6차 실기동 A/B + 수정판 실기동 재계측 30.29→25.02mm)


## R043

- R043 [export] **hwpx는 한컴 정본 패키지 프로파일로 정합해 인도한다 — kordoc 최소 패키지는 내부망 자료교환 반입에서 hwpx로 판별되지 않는다(octet-stream → 미등록 확장자 반려)**: kordoc 산출물은 mimetype·container.xml·content.hpf·header·section·PrvText만 있는 최소 OCF라서 hwpx 확정 마커인 version.xml이 없고, 디렉터리 엔트리 3개(META-INF/·Contents/·Preview/)·전량 STORED라는 정품에 없는 지문을 가진다 — mimetype+container.xml 구조는 EPUB류 일반 OCF와 지문이 같아 심층 구조 검사 엔진이 판별에 실패한다(타 hwpx는 동일 시스템 정상 유통 — 시스템 미등록이 아니라 산출물 문제, 사용자 확정). postprocess `canonicalize_package`가 플래그 무관 상시 적용: version.xml·settings.xml(content.hpf manifest 등재)·META-INF/manifest.xml·container.rdf 보강(한컴 정품 도식Pool.hwpx 실측 정본 템플릿), 디렉터리 엔트리 제거, container.xml rootfiles 정본화(PrvText·container.rdf), 엔트리 순서·압축 프로파일(mimetype·version.xml·미디어 STORED, XML DEFLATED) 정품 일치, 멱등. `validate_hwpx.py structural`이 OCF 시그니처(첫 엔트리 mimetype STORED·offset 0·extra 0·38바이트째 평문 application/hwp+zip)와 필수 멤버(version.xml·container.xml·content.hpf·header·section)·디렉터리 엔트리 부재를 검증해 회귀 차단. **'26.7.29 보강(실반려 파일 실측)**: 한글에서 재저장한 본은 정본 패키지가 되는 대신 기본 빈 JScript 스텁 Scripts/headerScripts·sourceScripts(확장자 없는 멤버 + hpf에 application/x-javascript로 등재되는 활성콘텐츠)가 삽입된다 — 압축 내부까지 검사하는 반입 엔진이 이것을 '등록되지 않은 확장자'로 반려하며, 실반려 오류 문구의 'header script'가 이 멤버명이다. canonicalize_package가 Scripts/ 멤버 전량 제거 + hpf item/itemref 등재 철회를 함께 수행한다(스텁은 기능 0, 기관보고서 인도본에 매크로 불필요) (근거: '26.7.29 내부망 자료교환 반입 거부 — 한컴 정품 대조 + 실반려 파일 실측)

## R050 [R062로 흡수·이관 — '26.8.7]

- R050 [draft] **[R062로 흡수·이관됨 — 본 규칙 폐지]** **계층 문구는 1줄로 끝내지 말고 2줄 밀도로 쓴다 (자수 기준은 R062가 정정 — 1줄 35자·상한 90자) — 렌더 기준 60~90자(휴먼명조 15pt, 1줄 = 35자 실측 — R062가 정정)**: R028이 "2줄 이내" 상한만 정한 탓에 40~60자짜리 한 줄 문구가 양산됐는데, 이는 보고서가 아니라 목차처럼 읽히고 근거·판단이 빠진 앙상한 서술이 된다. **상한(2줄)과 함께 하한(2줄에 가깝게)을 둔다** — 1줄로 끝나는 항목이 나오면 ① 인접 항목과 통합해 한 문장으로 합치거나(연결어 ~하며·~하고·~여서), ② 그 판단의 **근거·수치·조건·귀결**을 덧붙여 보강한다. 보강할 내용이 없으면 그 항목은 애초에 쓸 필요가 없는 항목이므로 삭제한다. **금지**: 자수를 채우려고 같은 말을 다르게 반복하거나 수식어를 늘리는 것 — 늘어난 분량은 반드시 새 정보(근거·수치·귀결)여야 한다. 표 셀·※ 단서·＊ 각주는 대상이 아니다(단서는 원래 짧다). 자가검산은 `**`·`==` 마커를 제거한 순수 글자수 기준 (근거[관례]: '26.8.3 사용자 확정, cert-poc PoC 결과보고건)

> 폐지 사유: 자수 기준(78~115자)이 실측과 어긋나 R062가 정정했고, 고유하게 남던 '2줄 밀도 하한' 취지는 R062 본문에 흡수했다. 피참조 0건이라 안전하게 제거.
