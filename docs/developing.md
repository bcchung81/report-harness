# 개발자용 — 로컬 검증·패키징·테스트


## 로컬에서 직접 검증

플러그인 설치 없이 스킬·커맨드를 바로 시험하려면 복사한다.

```bash
cp -R skills/* ~/.claude/skills/
cp -R commands ~/.claude/
```

동일 이름 스킬이 이미 있으면(예: 다른 출처의 `humanizer`) 덮어쓰지 말고 파일 단위로 병합할 것.

## 배포 제외 항목

다음은 `.gitignore`로 배포 저장소에서 제외한다(로컬 파일은 유지, 추적에서만 제외).

- `form/` — 실보고서·기관 양식 원본(hwp/hwpx) 12.6MB. 코퍼스 분석·실측 재검증용 로컬
  원자재이며 민감할 수 있어 배포하지 않는다. **런타임은 이 경로를 참조하지 않는다**(참조 0곳).
- `docs/analysis/` — 위 코퍼스에 대한 내부 분석 산출물.

런타임이 읽는 양식 자산은 `skills/report-pipeline/assets/` 아래 번들 사본이다
(`harness_config`의 `assets_dir`, 스킬 상대 경로 고정 — 배포 환경에서 `form/` 부재를 전제).

- `250609_표준보고서_KCA_문서양식.hwp` (64KB) — 양식 원본과 바이트 동일(md5 `88378b94…`)
- `도식Pool-경량.hwpx` (103KB) — 도식 Pool 원본(8.9MB)의 이미지 제거 경량본, 표 90개 유효

프레임워크·표 모음 원본은 번들 사본이 없으나, 추출 결과가 `table-pool.md`·`diagram-pool.md`에
성문화돼 있어 런타임에는 원본이 필요 없다.

## 패키징 가드 (배포 전 필수)

```bash
bash scripts/package_check.sh
```

- `git ls-files`로 `form/`·`docs/analysis/`가 여전히 추적 중인지 확인(추적 중이면 즉시 실패).
- `scripts/pii_scan.py`로 `skills/`·`commands/`만 스캔해 전화번호·이메일 잔존을 검사한다
  (`tests/` 픽스처는 의도적 PII 예시를 포함하므로 스캔 대상에서 제외).
- 모두 통과하면 `package check OK`를 출력한다.

## 테스트

```bash
python3 -m pytest -q
```

건수는 `pytest`가 세는 값이 정본이다(문서에 박아두면 곧 낡는다 — 실제로 세 문서가 세 숫자를
말하던 드리프트를 겪었다). 참조 문서 간 정합성(`test_references_consistency.py`), 플러그인·마켓플레이스
매니페스트 구조와 버전 일치(`test_plugin_structure.py`), 후처리 규칙 회귀
(`test_postprocess_hwpx.py`)에 더해 규칙 체계 자체를 지키는 둘이 있다.

| 테스트 | 막는 것 |
|---|---|
| `test_value_drift.py` | 규약 문서와 코드 상수의 드리프트. `format-profile.kca.md`를 단일 출처로 간격·들여쓰기·자간 하한을 대조하고, 시드가 운영 규칙과 **양방향으로** 일치하는지 본다(폐지된 규칙이 시드에만 남는 것도 검출) |
| `test_consolidate_rules.py` | 규칙 축적 방치. 파서 정합(다중 태그 규칙 누락 회귀)·죽은 참조·근거 등급 누락을 검사하고, 마지막 통합 이후 **10건이 늘면 실패**시킨다 |

규칙 현황만 보려면 `python3 skills/report-pipeline/scripts/consolidate_rules.py --check`.

---


---

- 전체 소개 → [README](../README.md)
