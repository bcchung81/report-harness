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

- `git ls-files`로 `form/`·`docs/analysis/`·`report/`가 추적 중인지 확인(추적 중이면 즉시 실패).
- `scripts/pii_scan.py`로 `skills/`·`commands/`·`webapp/`·`hooks/`·`scripts/`·`docs/`를 스캔해
  전화번호·이메일 잔존을 검사한다(`tests/` 픽스처는 의도적 PII 예시를 포함하므로 제외).
- 배포 원격(`deploy/main`)이 있는 노트북에서는 **버전 가드**도 본다 — 플러그인 내용이 배포 저장소와 다른데
  `plugin.json` 버전이 같으면 `WARN`을 낸다(실패는 아니다).
- 모두 통과하면 `package check OK`를 출력한다.

### 배포할 때는 버전을 올린다

설치본은 **버전으로** 갱신을 판단한다. 격리 설정 폴더(`CLAUDE_CONFIG_DIR`)로 배포 저장소를 설치한 뒤 새 커밋을 푸시하고
`claude plugin update report-harness@report-harness`를 돌리면, 버전이 같을 때는 `already at the latest version`으로
끝나고 설치본은 옛 커밋에 머문다('26.9.25 재현). 배포 저장소(`kca-deep/report-harness`)로 내보내는 묶음마다
`.claude-plugin/plugin.json`·`marketplace.json`의 버전을 함께 올리고(`test_plugin_structure.py`가 둘의 일치를 본다)
CHANGELOG에 절을 단다.

릴리스는 플러그인 규약 태그(`{이름}--v{버전}`)로 만든다 — `claude plugin tag`가 plugin.json과 마켓플레이스 항목의
버전 일치를 확인한 뒤 태그를 단다. 첫 릴리스는 `report-harness--v0.5.1`('26.9.25).

```bash
claude plugin tag . -m "report-harness %s — 한 줄 요약"
git push origin refs/tags/report-harness--v{버전} && git push deploy refs/tags/report-harness--v{버전}
gh release create report-harness--v{버전} -R kca-deep/report-harness --notes-file <CHANGELOG 해당 절> dist/kca-report-hwpx-*
```

설치·갱신 경로를 사용자 설정을 건드리지 않고 재현하려면:

```bash
export CLAUDE_CONFIG_DIR=$(mktemp -d)
claude plugin marketplace add kca-deep/report-harness
claude plugin install report-harness@report-harness
claude plugin details report-harness@report-harness      # 스킬·훅·MCP 구성과 상시 토큰 비용
claude plugin validate . --strict                        # 저장소 매니페스트 검증(루트 CLAUDE.md 경고는 의도 — 개발자용 문서)
```

## 웹앱 스킬 빌드

```bash
python3 scripts/build_webapp_skill.py --target all        # dist/에 3플랫폼 패키지
```

배포 기준 9종(룰 최신성·범위 필터·드리프트 0·dangling 0·사장 자산 0·출처 고정·서드파티 고지·
SKILL.md 단일·PII 0)을 전부 통과해야 산출된다 — 상세는 [install-webapp.md](install-webapp.md).
`dist/`는 gitignore 대상이다. 하네스 스크립트 4종과 references 문서 3종(md-profile·style-guide·
table-pool)은 웹앱 사본이 바이트 동일해야 한다 — 하네스 쪽을 고쳤으면 `cp`로 동기화한 뒤
빌드한다(안 하면 빌드·테스트가 잡는다). `diagram-pool.md`만 의도적 분기다.

## 훅

`hooks/hooks.json`이 PostToolUse 훅 `verify_hwpx_hook.py`를 등록한다 — hwpx를 만들고
구조 검증을 건너뛴 채 인도되는 것을 차단하는 마지막 안전망이다('26.8.7 실사고 재발 방지).
matcher는 Bash와 kordoc MCP(`generate_document`·`patch_document`)를 함께 잡는다 — 파이프라인의
주 생성 경로가 MCP라 Bash만 보면 정작 사고 경로가 사각지대가 된다. 검사 강도는 단계별로 다르다:
생성 단계 산출물은 `version.xml`이 없는 것이 정상이므로(그걸 채우는 게 뒤따르는 R043
`canonicalize_package`다) zip·XML 무결성만 보고 남은 후처리·검증을 비차단 리마인더로 돌려주며,
정합 단계(`postprocess_hwpx.py`·`md2hwpx.py`)에서만 `structural` 전량과 필수 멤버를 걸어 차단한다.
플러그인 설치 시 자동 등록되며, 동작 검증은 `tests/test_verify_hwpx_hook.py`.

두 번째 훅 `lint_draft_hook.py`는 Write·Edit를 잡아 **`20_draft.md`만** 결정론 린트·문체 감사에 태운다. 위반이
있으면 `decision: block`으로 되돌려 0건이 될 때까지 고치게 하고, 경고는 막지 않는다. 종전 사용자 설정 훅은 □ 줄이
두 개 이상인 md를 다 검사해 되읽기 기록(`40_roundtrip.md`)까지 막았다 — 파생 md는 대상이 아니다. 동작 검증은
`tests/test_lint_draft_hook.py`.

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
설치자 환경의 시드 ↔ 운영 규칙 차이는 `python3 skills/report-pipeline/scripts/sync_rules.py`(점검만, `--apply`로 반영).

**시드를 고쳤으면 커밋 전에 `python3 scripts/build_seed_lineage.py`** — 배포한 시드 줄의 지문을
`references/rules-seed.lineage.json`에 더한다. `sync_rules.py`는 이 계보로 설치자 운영본의 줄이 '손대지 않은 옛 시드
줄'인지 가려, 그런 줄만 새 시드 줄로 바꾸거나(폐지된 번호면 지우고) 설치자가 고친 줄은 그대로 둔다. 계보에 빠진 줄이
있으면 `test_sync_rules.py`가 실패한다. git 이력 전체에서 다시 모으려면 `--git`.

### 실전 점검 — 파이프라인 전 구간을 헤드리스로

회귀 테스트는 스크립트를 부품별로 본다. LLM이 SKILL.md를 읽고 자료 → 초안 → hwpx까지 실제로 가는지는
`scripts/smoke_pipeline.py`가 본다 — 가상 자료로 `claude -p` 세션을 돌리고 결과를 결정론으로 채점한다(린트·감사·설계
칸·구조·되읽기 대조·예상 쪽수·턴·비용). 실행마다 임시 폴더의 설정 파일을 `REPORT_HARNESS_CONFIG`로 가리켜 운영 폴더와
섞이지 않는다. 로그인된 Claude Code와 kordoc MCP가 필요하고 1회 약 10분·수 달러라 CI에서는 돌리지 않는다.

```bash
python3 scripts/smoke_pipeline.py --runs 2                          # 현재 하네스
python3 scripts/smoke_pipeline.py --runs 3 --rules /path/슬림판.md   # 규칙 판본 A/B — state_dir에 미리 둔다
python3 scripts/smoke_pipeline.py --score-only <결과 폴더>            # 다시 채점만
```

'26.9.25 첫 실행(9분·60턴)에서 CI가 못 보는 결함 3건을 찾았다 — R054 절 제목 경고, '끝.' 없는 문서의 머리말 그림
오계수, 게이트② 승인 뒤 쪽수 맞추기 압축. 헤드리스 세션은 `--dangerously-skip-permissions`로 돌므로 이 스크립트의 가상
자료로만 쓴다.

주의 — 세션은 이 저장소가 아니라 **설치된 하네스**(`~/.claude/skills` 사본 또는 플러그인)를 읽는다. 사본이 저장소와
다르면 도구가 멈추니(`--allow-stale`로 넘김) 커밋 뒤 사본을 교체하고 돌린다. 안전망 훅 2종은 플러그인으로 설치돼 있을
때만 돈다. `--rules` 판본은 시드의 규칙 번호를 모두 담아야 한다 — 빠진 번호는 첫 단계 `sync_rules.py --apply`가 되살려
A/B가 무효가 되므로 본문으로 줄이고, 실행 뒤 달라진 번호는 `rules_drift`로 보고된다.

CI(`.github/workflows/test.yml`)는 새 클론에서 pytest 전량·배포 가드·웹앱 빌드를 돌린다. 설치하는 것은 테스트 러너
pytest 하나뿐이다 — 이 설치를 빼 두었던 동안(8월~9월) CI가 매번 실패했다. 푸시 전 로컬에서 새 클론으로 한 번
돌려 보면(`git clone . /tmp/x && cd /tmp/x && python3 -m pytest -q`) '로컬에서만 초록'을 미리 잡는다.

---

- 전체 소개 → [README](../README.md)
