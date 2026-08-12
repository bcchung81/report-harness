# export 판본 보존 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `final/`에 hwpx가 이미 있는 상태의 재변환이 직전 변환 세트를 `revisions/rNN/`으로 보존한 뒤 진행하게 한다.

**Architecture:** 결정론 스크립트 `archive_revision.py`가 보존 실체이고, `hwpx-recipe.md` §0.5가 정상 경로에서 이를 부르며, PreToolUse 훅이 미호출 시 대신 뜬다. 저장소가 이미 쓰는 "스크립트 + 훅 안전망" 패턴(`verify_hwpx_hook.py`)을 그대로 따른다.

**Tech Stack:** Python 3 stdlib only (저장소 전 스크립트 공통 제약 — MCP 미호출, 외부 의존 없음), pytest.

**Spec:** `docs/superpowers/specs/2026-08-12-export-revision-archive-design.md`

## Global Constraints

- 모든 스크립트는 **stdlib-only**. 외부 패키지 import 금지.
- 경로 규약: 문서에 쓰는 스크립트 호출은 반드시 `"$SKILL_DIR/scripts/…"` 형태. 저장소 상대경로를 쓰면 플러그인 설치 환경(cwd가 사용자 프로젝트)에서 깨진다.
- exit 코드 의미론은 `postprocess_hwpx.py`와 통일: **0 = 처리함 / 1 = 대상 0건 / 2 = 인자·파일·IO 오류**.
- 아카이브 세트 6종 고정: `20_draft.md` · `40_prepared.md` · `43_convert_input.md` · `40_roundtrip.md` · `40_qa.md` · `final/*.hwpx`. 없는 파일은 건너뛴다.
- `research/`·`tools/`·`00_context.md`는 **복사하지 않는다**.
- 복사 의미론은 **copy**이고, `final/` 삭제는 복사와 index append가 **모두 성공한 뒤에만** 한다.
- 신규 규칙 번호는 **R073**. `report/_harness/rules.md`와 `skills/report-pipeline/references/rules-seed.md`에 **동일 문안으로 동시 반영**(`test_value_drift.test_seed_carries_every_operational_rule`이 강제).
- 훅은 실패해도 파이프라인을 막지 않는다 — 스크립트를 못 찾으면 stderr에 흔적만 남기고 통과.
- 테스트는 `pytest.ini`의 `testpaths = tests` 규약에 따라 `tests/` 아래 둔다. 스크립트 import는 `sys.path.insert(0, ROOT / "skills/report-pipeline/scripts")` 관례를 따른다(`tests/test_prep_report_md.py:1-3` 참조).

**Phase 1 (Task 1~4)** 만으로 기능이 완결된다. **Phase 2 (Task 5)** 는 안전망이며 생략해도 Phase 1은 동작한다.

---

## Task 1: `archive_revision.py` — 보존 스크립트

**Files:**
- Create: `skills/report-pipeline/scripts/archive_revision.py`
- Test: `tests/test_archive_revision.py`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces:
  - `SET_FILES: tuple[str, ...]` — 아카이브 대상 md 5종
  - `sha256(path: pathlib.Path) -> str`
  - `next_rev(index_path: pathlib.Path) -> int`
  - `research_fingerprint(work_dir: pathlib.Path) -> dict | None`
  - `plan(work_dir: pathlib.Path) -> tuple[list[pathlib.Path], list[pathlib.Path]]` — `(hwpx 목록, md 목록)`
  - `archive(work_dir, reason="", now=None, dry_run=False) -> dict` — 요약 JSON
  - `ArchiveError(Exception)`
  - `main(argv) -> int` — exit 코드
  - CLI: `archive_revision.py <work_dir> [--reason TEXT] [--dry-run]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_archive_revision.py`:

```python
"""개정 시 판본 보존 (R073).

배경: 산출물 6건 전수 대조에서 재변환이 일어난 2건이 어긋나 있었다 — 20260730/2046은
hwpx가 8/4에 재생성됐는데 40_roundtrip.md가 7/30 그대로였고(현행 draft와 유사도 0.524),
20260807/2242는 서로 다른 보고서 hwpx 2개가 final/에 공존해 계보 추적이 불가능했다.
"""
import json, pathlib, subprocess, sys, zipfile
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/report-pipeline/scripts/archive_revision.py"
sys.path.insert(0, str(ROOT / "skills/report-pipeline/scripts"))
from archive_revision import archive, plan, next_rev, sha256, ArchiveError


def make_work_dir(tmp_path, *, hwpx_names=("보고서.hwpx",), docs=None, research_lines=0):
    """세트가 갖춰진 work_dir을 만든다. docs=None이면 5종 전건."""
    d = tmp_path / "20260812" / "1030_테스트건"
    (d / "final").mkdir(parents=True)
    names = ("20_draft.md", "40_prepared.md", "43_convert_input.md",
             "40_roundtrip.md", "40_qa.md") if docs is None else docs
    for n in names:
        (d / n).write_text(f"내용 {n}\n", encoding="utf-8")
    for n in hwpx_names:
        with zipfile.ZipFile(d / "final" / n, "w") as z:
            z.writestr("mimetype", "application/hwp+zip")
    if research_lines:
        (d / "research").mkdir()
        (d / "research" / "_manifest.jsonl").write_text(
            "".join(json.dumps({"i": i}, ensure_ascii=False) + "\n"
                    for i in range(research_lines)), encoding="utf-8")
    return d


def read_index(work_dir):
    p = work_dir / "revisions" / "index.jsonl"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_no_hwpx_is_noop(tmp_path):
    """최초 변환 — 보존할 것이 없으면 revisions/를 만들지 않는다."""
    d = make_work_dir(tmp_path, hwpx_names=())
    s = archive(d)
    assert s["archived"] is False
    assert not (d / "revisions").exists()


def test_full_set_archived_and_final_emptied(tmp_path):
    d = make_work_dir(tmp_path)
    s = archive(d, reason="의견 반영")
    dest = d / "revisions" / s["dir"]
    for n in ("20_draft.md", "40_prepared.md", "43_convert_input.md",
              "40_roundtrip.md", "40_qa.md", "보고서.hwpx"):
        assert (dest / n).is_file(), n
    assert list((d / "final").glob("*.hwpx")) == []
    assert (d / "20_draft.md").is_file()          # 원본은 복사이므로 남는다
    entries = read_index(d)
    assert len(entries) == 1
    assert entries[0]["rev"] == 1
    assert entries[0]["reason"] == "의견 반영"


def test_two_hwpx_both_archived(tmp_path):
    """2242 형태 — final/에 서로 다른 판본 hwpx가 2개 공존하는 경우."""
    d = make_work_dir(tmp_path, hwpx_names=("구판.hwpx", "신판.hwpx"))
    s = archive(d)
    assert sorted(s["hwpx"]) == ["구판.hwpx", "신판.hwpx"]
    assert list((d / "final").glob("*.hwpx")) == []


def test_missing_optional_file_skipped(tmp_path):
    """팩트체크 생략 등으로 40_qa.md가 없어도 성공한다."""
    d = make_work_dir(tmp_path, docs=("20_draft.md", "40_prepared.md"))
    s = archive(d)
    assert s["archived"] is True
    assert "40_qa.md" not in read_index(d)[0]["files"]
    assert not (d / "revisions" / s["dir"] / "40_qa.md").exists()


def test_consecutive_runs_increment_rev(tmp_path):
    d = make_work_dir(tmp_path)
    first = archive(d)
    with zipfile.ZipFile(d / "final" / "보고서.hwpx", "w") as z:
        z.writestr("mimetype", "application/hwp+zip")
    second = archive(d)
    assert first["dir"].startswith("r01_") and second["dir"].startswith("r02_")
    assert [e["rev"] for e in read_index(d)] == [1, 2]


def test_sha256_matches_copy(tmp_path):
    d = make_work_dir(tmp_path)
    s = archive(d)
    files = read_index(d)[0]["files"]
    for name, digest in files.items():
        assert sha256(d / "revisions" / s["dir"] / name) == digest


def test_research_not_copied_but_fingerprinted(tmp_path):
    d = make_work_dir(tmp_path, research_lines=12)
    s = archive(d)
    assert not (d / "revisions" / s["dir"] / "research").exists()
    assert read_index(d)[0]["research"]["manifest_lines"] == 12


def test_research_absent_is_null(tmp_path):
    d = make_work_dir(tmp_path)
    archive(d)
    assert read_index(d)[0]["research"] is None


def test_dry_run_touches_nothing(tmp_path):
    d = make_work_dir(tmp_path)
    s = archive(d, dry_run=True)
    assert s["dry_run"] is True and s["archived"] is False
    assert s["dir"].startswith("r01_")
    assert not (d / "revisions").exists()
    assert (d / "final" / "보고서.hwpx").is_file()


def test_missing_work_dir_raises(tmp_path):
    with pytest.raises(ArchiveError):
        archive(tmp_path / "없는폴더")


def test_final_survives_index_append_failure(tmp_path):
    """index append가 실패하면 final/을 비우지 않는다 — 순서가 뒤집히면 원본이 사라진다.

    index.jsonl 자리에 디렉터리를 놓아 open(..., "a")를 IsADirectoryError로 만든다.
    """
    d = make_work_dir(tmp_path)
    (d / "revisions" / "index.jsonl").mkdir(parents=True)
    with pytest.raises(OSError):
        archive(d)
    assert (d / "final" / "보고서.hwpx").is_file()


def test_cli_exit_codes(tmp_path):
    d = make_work_dir(tmp_path)
    r = subprocess.run([sys.executable, str(SCRIPT), str(d)],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert json.loads(r.stdout)["archived"] is True

    r2 = subprocess.run([sys.executable, str(SCRIPT), str(d)],
                        capture_output=True, text=True)
    assert r2.returncode == 1        # hwpx 0건 = 대상 없음

    r3 = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "없음")],
                        capture_output=True, text=True)
    assert r3.returncode == 2
    assert "FATAL" in r3.stderr
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python3 -m pytest tests/test_archive_revision.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'archive_revision'`

- [ ] **Step 3: 스크립트를 구현한다**

`skills/report-pipeline/scripts/archive_revision.py`:

```python
"""개정 시 판본 보존 (R073). stdlib-only.

final/에 hwpx가 이미 있는 상태의 재변환은 직전 변환 세트를 revisions/rNN/으로 복사해 남기고
final/을 비운다 — 현행본이 파일만 보고 판별되게 하기 위해서다.

## 왜 복사이고 왜 research/는 빼는가

이동이 아니라 복사인 이유: 재변환이 실패해도 직전 정본이 final/에 남아야 한다. 삭제는 복사와
index append가 모두 성공한 뒤에만 한다.

research/를 빼는 이유: append-only 자산이라 판본마다 복사하면 원본 PDF·이미지가 판본 수만큼
중복된다. 대신 _manifest.jsonl의 줄 수와 지문만 index에 남겨 그 시점의 조사 범위를 재구성한다.

files의 sha256이 이 스크립트의 핵심이다 — '26.8.12 실측에서 어느 초안이 어느 hwpx를 낳았는지
밝힌 근거가 바이트 일치였다(파일명 규약은 이미 깨져 있었다).
"""
import sys, json, shutil, hashlib, argparse, datetime, pathlib

SET_FILES = ("20_draft.md", "40_prepared.md", "43_convert_input.md",
             "40_roundtrip.md", "40_qa.md")


class ArchiveError(Exception):
    pass


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def next_rev(index_path):
    """index.jsonl의 유효 줄 수 + 1. 파일이 없으면 1."""
    if not index_path.is_file():
        return 1
    lines = index_path.read_text(encoding="utf-8").splitlines()
    return sum(1 for l in lines if l.strip()) + 1


def research_fingerprint(work_dir):
    """research/_manifest.jsonl의 줄 수·지문. 조사가 없으면 None."""
    m = work_dir / "research" / "_manifest.jsonl"
    if not m.is_file():
        return None
    lines = [l for l in m.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {"manifest_lines": len(lines), "manifest_sha256": sha256(m)}


def plan(work_dir):
    """(final/ hwpx 목록, 존재하는 세트 md 목록). 없는 파일은 조용히 빠진다."""
    final = work_dir / "final"
    hwpx = sorted(final.glob("*.hwpx")) if final.is_dir() else []
    docs = [work_dir / n for n in SET_FILES if (work_dir / n).is_file()]
    return hwpx, docs


def archive(work_dir, reason="", now=None, dry_run=False):
    work_dir = pathlib.Path(work_dir)
    if not work_dir.is_dir():
        raise ArchiveError(f"work_dir 없음 — {work_dir}")
    hwpx, docs = plan(work_dir)
    now = now or datetime.datetime.now()
    revisions = work_dir / "revisions"
    index_path = revisions / "index.jsonl"
    rev = next_rev(index_path)
    name = f"r{rev:02d}_{now.strftime('%Y%m%d-%H%M')}"
    summary = {"archived": False, "dry_run": dry_run, "rev": rev, "dir": name,
               "hwpx": [p.name for p in hwpx], "docs": [p.name for p in docs]}
    if not hwpx or dry_run:
        return summary

    dest = revisions / name
    dest.mkdir(parents=True)
    files = {}
    for p in docs + hwpx:
        shutil.copy2(p, dest / p.name)
        files[p.name] = sha256(p)
    entry = {"rev": rev, "at": now.isoformat(timespec="seconds"), "reason": reason,
             "dir": name, "hwpx": [p.name for p in hwpx], "files": files,
             "research": research_fingerprint(work_dir)}
    with open(index_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    # 복사·append가 모두 성공한 뒤에만 현행본 자리를 비운다 — 순서가 뒤집히면 append 실패 시
    # 원본이 사라진다
    for p in hwpx:
        p.unlink()
    summary["archived"] = True
    summary["files"] = files
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description="개정 시 직전 변환 세트를 revisions/로 보존한다 (R073)")
    ap.add_argument("work_dir")
    ap.add_argument("--reason", default="", help="개정 사유. 훅이 대신 뜬 경우 unattended")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        s = archive(a.work_dir, reason=a.reason, dry_run=a.dry_run)
    except ArchiveError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        print(f"FATAL: IO 실패 — {e}", file=sys.stderr)
        return 2
    print(json.dumps(s, ensure_ascii=False))
    return 0 if s["hwpx"] else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/test_archive_revision.py -v`
Expected: PASS — 12개 전건

- [ ] **Step 5: 커밋**

```bash
git add skills/report-pipeline/scripts/archive_revision.py tests/test_archive_revision.py
git commit -m "판본 보존 스크립트 — 개정 시 변환 세트를 revisions/rNN/으로 아카이브 (R073)"
```

---

## Task 2: R073 규칙 등재 + 스크립트 인벤토리

**Files:**
- Modify: `report/_harness/rules.md` (파일 끝, R072 다음 줄)
- Modify: `skills/report-pipeline/references/rules-seed.md` (동일 문안)
- Modify: `skills/report-pipeline/scripts/doctor.py:53-56`

**Interfaces:**
- Consumes: Task 1의 `archive_revision.py` 파일 존재
- Produces: 없음 (규약·인벤토리 갱신)

- [ ] **Step 1: 기존 회귀 테스트가 아직 통과하는지 확인한다**

Run: `python3 -m pytest tests/test_value_drift.py tests/test_references_consistency.py tests/test_no_dead_code.py -v`
Expected: PASS (기준선 확보 — 여기서 이미 깨져 있으면 이 계획과 무관한 문제이므로 멈추고 보고)

- [ ] **Step 2: R073을 두 파일에 동시 추가한다**

`report/_harness/rules.md`와 `skills/report-pipeline/references/rules-seed.md` 양쪽 끝에 **똑같이** 한 줄로 넣는다. 한쪽만 고치면 `test_value_drift.test_seed_carries_every_operational_rule`이 실패한다 — R062 정정 때 시드를 놓쳐 새 설치가 틀린 값을 물려받을 뻔한 사고의 회귀 방지 장치다.

```markdown
- R073 [export] **`final/`에 hwpx가 이미 있는 상태의 재변환은 직전 변환 세트를 먼저 보존한다** — `archive_revision.py`가 `20_draft.md`·`40_prepared.md`·`43_convert_input.md`·`40_roundtrip.md`·`40_qa.md`·`final/*.hwpx` 6종을 `revisions/rNN_{YYYYMMDD-HHMM}/`으로 복사(이동 아님 — 재변환 실패 시 정본 보존)하고 `revisions/index.jsonl`에 sha256 지문과 함께 1줄 남긴 뒤 `final/`을 비운다. `research/`는 append-only 자산이라 복사 대상이 아니며 `_manifest.jsonl` 줄 수·지문만 기록한다. 정상 경로는 hwpx-recipe §0.5가 부르고, 미호출 시 PreToolUse 훅이 `--reason unattended`로 대신 뜬다. 배경: 재변환이 일어난 2건에서 `40_roundtrip.md`가 구판으로 남거나(20260730/2046 — 현행 draft와 유사도 0.524) 서로 다른 판본 hwpx가 `final/`에 공존해(20260807/2242) 계보 추적이 불가능했다 (근거[실측]: '26.8.12 산출물 6건 전수 대조)
```

- [ ] **Step 3: `doctor.py`의 스크립트 존재 검사에 추가한다**

`skills/report-pipeline/scripts/doctor.py:53-56`의 튜플에 `"archive_revision.py"`를 넣는다:

```python
    missing = [n for n in ("harness_config.py", "lint_md_profile.py", "prep_report_md.py",
                           "postprocess_hwpx.py", "validate_hwpx.py", "check_image_size.py",
                           "extract_format_profile.py", "consolidate_rules.py",
                           "archive_revision.py")
               if not (SCRIPTS / n).exists()]
```

- [ ] **Step 4: 시드 정합 회귀가 통과하는지 확인한다**

Run: `python3 -m pytest tests/test_value_drift.py tests/test_consolidate_rules.py -v`
Expected: PASS — 특히 `test_seed_carries_every_operational_rule`. 여기서 실패하면 두 파일의 R073 문안이 글자 단위로 다르다는 뜻이므로 맞춘다.

Run: `python3 skills/report-pipeline/scripts/consolidate_rules.py --check`
Expected: exit 0 — 통합 마커가 `consolidated-at: R068`이고 R069~R073 누적 5건이라 10건 임계 미달

- [ ] **Step 5: 커밋**

```bash
git add report/_harness/rules.md skills/report-pipeline/references/rules-seed.md \
        skills/report-pipeline/scripts/doctor.py
git commit -m "R073 등재 — 판본 보존 규칙, doctor 스크립트 인벤토리 확장"
```

---

## Task 3: 규약 문서 — 정상 경로에 절차를 박는다

**Files:**
- Modify: `skills/report-pipeline/references/hwpx-recipe.md` (§0 다음에 §0.5 신설, 부록 CLI 표에 행 추가)
- Modify: `skills/report-pipeline/SKILL.md:229` (④ export 1번 앞에 0단계 삽입), `:339` 부근 참조 목록
- Modify: `commands/report-export.md:5`
- Test: `tests/test_references_consistency.py:15-17`

**Interfaces:**
- Consumes: Task 1의 CLI `archive_revision.py <work_dir> [--reason TEXT] [--dry-run]`, exit 0/1/2
- Produces: 없음

- [ ] **Step 1: 실패하는 검사를 먼저 넣는다**

`tests/test_references_consistency.py:15-17`의 스크립트 목록을 확장한다:

```python
def test_hwpx_recipe_mentions_scripts():
    text = (REF / "hwpx-recipe.md").read_text(encoding="utf-8")
    for s in ["prep_report_md.py", "validate_hwpx.py", "check_image_size.py",
              "archive_revision.py"]:
        assert s in text
```

- [ ] **Step 2: 검사가 실패하는지 확인한다**

Run: `python3 -m pytest tests/test_references_consistency.py::test_hwpx_recipe_mentions_scripts -v`
Expected: FAIL — 레시피가 아직 `archive_revision.py`를 언급하지 않음

- [ ] **Step 3: `hwpx-recipe.md`에 §0.5를 넣는다**

`## 1. prep 정규화` 바로 앞에 삽입:

```markdown
## 0.5. 판본 보존 — 재변환이면 직전 세트를 먼저 남긴다 (R073)

```
python3 "$SKILL_DIR/scripts/archive_revision.py" {work_dir} --reason "{개정 사유}"
```

- **exit 1**(`archived:false`)이면 최초 변환이라 보존할 것이 없다는 뜻 — 정상이므로 그대로 §1로
  진행한다. 이 경우는 실패가 아니다.
- **exit 0**이면 직전 세트 6종(`20_draft.md`·`40_prepared.md`·`43_convert_input.md`·
  `40_roundtrip.md`·`40_qa.md`·`final/*.hwpx`)이 `{work_dir}/revisions/rNN_{YYYYMMDD-HHMM}/`으로
  복사되고 `final/`이 비워졌다. 이제 새 산출물이 `final/`의 유일한 hwpx가 된다.
- **exit 2**면 사유를 그대로 보고하고 변환을 중단한다.
- `research/`는 복사 대상이 아니다 — append-only 자산이라 판본마다 복사하면 원본이 중복된다.
  그 시점의 조사 범위는 `index.jsonl`의 `research.manifest_lines`·`manifest_sha256`로 남는다.
- `--reason`에는 왜 다시 변환하는지를 짧게 적는다(`"정보보호팀 지적 4건 반영"`). 이 값이 비면
  나중에 판본 목록만 보고는 개정 경위를 알 수 없다. PreToolUse 훅이 대신 뜬 경우에는
  `unattended`가 들어가며, 이는 사유 공백이 아니라 **레시피를 타지 않은 경로로 변환됐다**는
  신호다(R072 이탈 계수용).
- 이 절은 hwpx를 만드는 모든 호출에 적용된다(R072와 같은 판단 기준 — 입력이 아니라 출력이 hwpx인가).
```

부록 CLI 표(`## 부록 — 스크립트 CLI 시그니처·exit 코드`)에 행 추가:

```markdown
| `archive_revision.py` | `archive_revision.py <work_dir> [--reason TEXT] [--dry-run]` | 직전 세트 보존 완료(요약 JSON) | 보존 대상 없음(최초 변환) | work_dir 부재·IO 오류 |
```

- [ ] **Step 4: `SKILL.md` ④ export에 0단계를 넣는다**

`## ④ export — hwpx 변환` 절의 `1. **팩트체크(…)` 앞에 새 항목을 넣고, 기존 1·2·3·4·5를 그대로 둔 채 번호 없는 선행 단계로 표기한다:

```markdown
0. **판본 보존 (R073)** — `final/`에 hwpx가 이미 있으면 재변환이므로 직전 세트를 먼저 남긴다.

   ```
   python3 "$SKILL_DIR/scripts/archive_revision.py" {work_dir} --reason "{개정 사유}"
   ```

   exit 1은 최초 변환(보존 대상 없음)이라는 뜻이므로 그대로 진행한다. exit 0이면 `final/`이
   비워진 상태로 아래 변환이 이어진다. 절차 상세는 `hwpx-recipe.md` §0.5.
```

같은 파일의 참조 목록(`- \`scripts/harness_config.py\` — …` 가 있는 블록)에 한 줄 추가:

```markdown
- `scripts/archive_revision.py` — 개정 시 판본 보존(R073). 재변환 직전 변환 세트를
  `revisions/rNN/`으로 복사하고 `final/`을 비운다.
```

- [ ] **Step 5: `commands/report-export.md`에 1줄 반영한다**

`:5`의 서술에서 변환 절차 나열 부분을 고친다 — `hwpx-recipe 절차로 변환한다(prep 정규화→…` 를 `hwpx-recipe 절차로 변환한다(판본 보존→prep 정규화→…` 로 바꾸고, 문장 끝에 한 줄 덧붙인다:

```markdown
재변환(= `final/`에 hwpx가 이미 있음)이면 `archive_revision.py`가 직전 세트를 `revisions/rNN/`으로 먼저 보존한다(R073).
```

- [ ] **Step 6: Step 2에서 실패시켜 둔 검사가 통과하는지 확인한다**

Run: `python3 -m pytest tests/test_references_consistency.py tests/test_no_dead_code.py -v`
Expected: PASS — `test_hwpx_recipe_mentions_scripts` 통과(레시피가 이제 스크립트를 언급), `test_no_dead_code`의 "안 불리는 스크립트" 감사도 통과(레시피·SKILL이 부른다)

- [ ] **Step 7: 커밋**

```bash
git add skills/report-pipeline/references/hwpx-recipe.md skills/report-pipeline/SKILL.md \
        commands/report-export.md tests/test_references_consistency.py
git commit -m "변환 레시피 §0.5 판본 보존 — export 정상 경로에 절차 등재"
```

---

## Task 4: Phase 1 통합 검증 + CHANGELOG

**Files:**
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: Task 1~3 전체
- Produces: 없음

- [ ] **Step 1: 전체 테스트를 돌린다**

Run: `python3 -m pytest -q`
Expected: PASS 전건. 실패가 있으면 이 계획 밖 원인인지부터 확인하고, 이 계획이 만든 실패면 해당 태스크로 돌아간다.

- [ ] **Step 2: 자가진단을 돌린다**

Run: `python3 skills/report-pipeline/scripts/doctor.py`
Expected: `archive_revision.py`가 스크립트 점검에 나타나고 missing 없음

- [ ] **Step 3: 실제 산출물로 dry-run 한다**

Run: `python3 skills/report-pipeline/scripts/archive_revision.py "report/20260807/2242_xmos-펌웨어-보안검증" --dry-run`
Expected: exit 0, JSON의 `hwpx` 배열 길이 2(`데스크톱형 AI 로봇 도입 보안성 종합 검토결과.hwpx`·`데스크톱형 AI 로봇 오디오 펌웨어 보안 검증결과.hwpx`), `dry_run: true`, `archived: false`, 파일 시스템 무변경.

확인: `git status --short report/` 가 비어 있어야 한다. **`--dry-run` 없이 실행하지 말 것** — 실제 산출물의 소급 정리는 이 계획 밖이다(spec §11).

- [ ] **Step 4: CHANGELOG에 항목을 넣는다**

`CHANGELOG.md` 최상단 미출시 절에 추가:

```markdown
- 개정 시 판본 보존 (R073) — `final/`에 hwpx가 있는 상태의 재변환은 직전 변환 세트 6종을
  `revisions/rNN_{YYYYMMDD-HHMM}/`으로 복사하고 sha256 지문을 `revisions/index.jsonl`에
  남긴 뒤 `final/`을 비운다. `research/`는 복사하지 않고 manifest 지문만 기록한다.
```

- [ ] **Step 5: 커밋**

```bash
git add CHANGELOG.md
git commit -m "CHANGELOG — 판본 보존(R073)"
```

**여기까지가 Phase 1이다. 기능은 완결됐고, Task 5는 생략해도 동작한다.**

---

## Task 5: PreToolUse 훅 안전망 (Phase 2)

**Files:**
- Create: `hooks/archive_revision_hook.py`
- Modify: `hooks/hooks.json`
- Test: `tests/test_archive_revision_hook.py`

**Interfaces:**
- Consumes: Task 1의 CLI `archive_revision.py <work_dir> --reason unattended`
- Produces:
  - `find_script() -> str | None`
  - `strings(v) -> Iterator[str]`
  - `work_dir_for(paths: list[str]) -> str | None`
  - `recently_archived(work_dir: str, now: datetime.datetime) -> bool`
  - `RECENT_SECONDS = 600`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_archive_revision_hook.py`:

```python
"""판본 보존 PreToolUse 훅 — 레시피 §0.5를 안 부르고 재변환하는 경로를 대신 막는다.

'26.8.12 실측: 재변환 2건이 모두 규약대로 진행되지 않았다(roundtrip 미갱신, 입력 파일명
규약 이탈). 규약 문서만으로는 새는 것이 이 저장소의 실증된 실패 모드다.
"""
import datetime, json, os, pathlib, shutil, subprocess, sys, zipfile
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "archive_revision_hook.py"


def run_hook(payload, plugin_root=str(ROOT)):
    env = dict(os.environ)
    if plugin_root:
        env["CLAUDE_PLUGIN_ROOT"] = plugin_root
    else:
        env.pop("CLAUDE_PLUGIN_ROOT", None)
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload),
                          capture_output=True, text=True, env=env)


def payload_for(output_path, tool="mcp__kordoc__generate_document"):
    return {"tool_name": tool, "tool_input": {"markdown": "…", "output_path": str(output_path)}}


def make_work_dir(tmp_path, hwpx_names=("보고서.hwpx",)):
    d = tmp_path / "20260812" / "1030_테스트건"
    (d / "final").mkdir(parents=True)
    (d / "20_draft.md").write_text("초안\n", encoding="utf-8")
    for n in hwpx_names:
        with zipfile.ZipFile(d / "final" / n, "w") as z:
            z.writestr("mimetype", "application/hwp+zip")
    return d


def test_first_conversion_is_noop(tmp_path):
    """final/이 비어 있으면(최초 변환) 아무것도 하지 않는다."""
    d = make_work_dir(tmp_path, hwpx_names=())
    r = run_hook(payload_for(d / "final" / "새보고서.hwpx"))
    assert r.returncode == 0 and r.stdout.strip() == ""
    assert not (d / "revisions").exists()


def test_reconversion_archives_unattended(tmp_path):
    d = make_work_dir(tmp_path)
    r = run_hook(payload_for(d / "final" / "보고서.hwpx"))
    assert r.returncode == 0
    entries = [json.loads(l) for l
               in (d / "revisions" / "index.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(entries) == 1
    assert entries[0]["reason"] == "unattended"
    assert list((d / "final").glob("*.hwpx")) == []


def test_recent_archive_suppresses_hook(tmp_path):
    """정상 경로가 이미 보존했거나 재변환 루프가 도는 중이면 이중 판본을 만들지 않는다."""
    d = make_work_dir(tmp_path)
    (d / "revisions").mkdir()
    recent = datetime.datetime.now() - datetime.timedelta(seconds=60)
    (d / "revisions" / "index.jsonl").write_text(
        json.dumps({"rev": 1, "at": recent.isoformat(timespec="seconds"), "reason": "수동"},
                   ensure_ascii=False) + "\n", encoding="utf-8")
    run_hook(payload_for(d / "final" / "보고서.hwpx"))
    entries = (d / "revisions" / "index.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(entries) == 1                      # 늘지 않았다
    assert (d / "final" / "보고서.hwpx").is_file()  # 지우지도 않았다


def test_stale_archive_does_not_suppress(tmp_path):
    d = make_work_dir(tmp_path)
    (d / "revisions").mkdir()
    old = datetime.datetime.now() - datetime.timedelta(hours=3)
    (d / "revisions" / "index.jsonl").write_text(
        json.dumps({"rev": 1, "at": old.isoformat(timespec="seconds"), "reason": "예전"},
                   ensure_ascii=False) + "\n", encoding="utf-8")
    run_hook(payload_for(d / "final" / "보고서.hwpx"))
    entries = (d / "revisions" / "index.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(entries) == 2


def test_patch_document_not_watched(tmp_path):
    """patch_document은 final/의 파일을 제자리 수정한다 — 훅이 지우면 입력이 사라진다."""
    d = make_work_dir(tmp_path)
    run_hook(payload_for(d / "final" / "보고서.hwpx", tool="mcp__kordoc__patch_document"))
    assert (d / "final" / "보고서.hwpx").is_file()
    assert not (d / "revisions").exists()


def test_non_final_path_ignored(tmp_path):
    """final/ 밖 산출물은 work_dir 규약 밖이므로 건드리지 않는다."""
    out = tmp_path / "Downloads"
    out.mkdir()
    r = run_hook(payload_for(out / "임시.hwpx"))
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_missing_script_is_silent_passthrough(tmp_path):
    """스크립트를 못 찾으면 파이프라인을 막지 않는다 — 흔적만 stderr에 남긴다.

    find_script()는 CLAUDE_PLUGIN_ROOT 다음에 '훅 파일의 상위 디렉터리'를 폴백으로 본다.
    저장소 안의 훅을 그대로 돌리면 그 폴백이 진짜 스크립트를 찾아내므로, 훅을 격리된
    임시 디렉터리로 복사해 두 경로 모두 비게 만든다.
    """
    d = make_work_dir(tmp_path)
    isolated = tmp_path / "iso" / "hooks"
    isolated.mkdir(parents=True)
    shutil.copy2(HOOK, isolated / HOOK.name)
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(tmp_path / "빈루트"))
    r = subprocess.run([sys.executable, str(isolated / HOOK.name)],
                       input=json.dumps(payload_for(d / "final" / "보고서.hwpx")),
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0 and r.stdout.strip() == ""
    assert "미발견" in r.stderr
    assert (d / "final" / "보고서.hwpx").is_file()   # 지우지 않았다


def test_bad_payload_is_silent(tmp_path):
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(ROOT))
    r = subprocess.run([sys.executable, str(HOOK)], input="not json",
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0 and r.stdout.strip() == ""
    assert "파싱 실패" in r.stderr
```

- [ ] **Step 2: 테스트가 실패하는지 확인한다**

Run: `python3 -m pytest tests/test_archive_revision_hook.py -v`
Expected: FAIL — `hooks/archive_revision_hook.py` 없음 (`can't open file`)

- [ ] **Step 3: 훅을 구현한다**

`hooks/archive_revision_hook.py`:

```python
#!/usr/bin/env python3
"""PreToolUse 훅 — 재변환 직전 판본 보존이 누락된 경우 대신 뜬다 (R073). stdlib-only.

## 왜 필요한가

hwpx-recipe.md §0.5가 재변환 전 `archive_revision.py` 호출을 요구하지만, 규약 문서만으로는
샌다 — '26.8.12 실측에서 재변환이 일어난 2건이 모두 어긋나 있었다(roundtrip 미갱신, 입력
파일명 규약 이탈). verify_hwpx_hook.py와 같은 자리의 안전망이다.

## 왜 generate_document만 보는가

훅은 보존 후 final/을 비운다. patch_document은 레시피 §3에서 바로 그 파일을 제자리 수정하므로
여기서 지우면 입력이 사라진다. generate_document은 항상 patch_document 앞에 오므로 그 시점의
보존으로 충분하고, R072가 다룬 이탈 경로도 generate_document 직접 호출이었다.

## 이중 실행 방지

정상 경로가 이미 §0.5를 불렀거나 재변환 루프(레시피 §5, 최대 2회)가 도는 중이면 판본이
불필요하게 는다. index.jsonl 마지막 항목이 RECENT_SECONDS 이내면 뜨지 않는다.
"""
import sys, os, re, json, datetime, subprocess

HWPX = re.compile(r"[^\s\"']+\.hwpx")
RECENT_SECONDS = 600   # 재변환 루프(최대 2회)를 넉넉히 덮는 어림값 — 이중 판본 관찰 시 조정


def find_script():
    """플러그인 루트 우선, 없으면 저장소 상대 경로 (verify_hwpx_hook.py와 동일 규약)."""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    here = os.path.dirname(os.path.abspath(__file__))
    for base in (root, os.path.dirname(here)):
        if not base:
            continue
        p = os.path.join(base, "skills", "report-pipeline", "scripts", "archive_revision.py")
        if os.path.isfile(p):
            return p
    return None


def strings(v):
    """tool_input 안의 모든 문자열. MCP 도구는 경로 인자 이름이 제각각이라 값 전체를 훑는다."""
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from strings(x)
    elif isinstance(v, list):
        for x in v:
            yield from strings(x)


def work_dir_for(paths):
    """final/ 아래 hwpx 경로에서 work_dir을 역산한다. 규약 밖 경로면 None."""
    for p in paths:
        d = os.path.dirname(os.path.abspath(p.strip("'\"")))
        if os.path.basename(d) == "final":
            return os.path.dirname(d)
    return None


def recently_archived(work_dir, now):
    idx = os.path.join(work_dir, "revisions", "index.jsonl")
    if not os.path.isfile(idx):
        return False
    try:
        with open(idx, encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
        at = datetime.datetime.fromisoformat(json.loads(lines[-1])["at"])
    except (OSError, ValueError, KeyError, IndexError):
        return False
    return (now - at).total_seconds() < RECENT_SECONDS


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("archive_revision_hook: stdin 페이로드 파싱 실패 — 판본 보존을 건너뜀",
              file=sys.stderr)
        return
    tool = data.get("tool_name") or ""
    if not (tool.startswith("mcp__") and "generate_document" in tool):
        return
    paths = [m for s in strings(data.get("tool_input") or {}) for m in HWPX.findall(s)]
    work_dir = work_dir_for(paths)
    if work_dir is None:
        return
    try:
        existing = [f for f in os.listdir(os.path.join(work_dir, "final"))
                    if f.endswith(".hwpx")]
    except OSError:
        return
    if not existing:
        return                                     # 최초 변환
    if recently_archived(work_dir, datetime.datetime.now()):
        return                                     # 정상 경로가 이미 보존함
    script = find_script()
    if script is None:
        print("archive_revision_hook: archive_revision.py 미발견 — 판본 보존 없이 통과함",
              file=sys.stderr)
        return
    try:
        subprocess.run([sys.executable, script, work_dir, "--reason", "unattended"],
                       capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"archive_revision_hook: 판본 보존 실패 — {e}. "
              "archive_revision.py를 수동 실행할 것", file=sys.stderr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트가 통과하는지 확인한다**

Run: `python3 -m pytest tests/test_archive_revision_hook.py -v`
Expected: PASS — 8개 전건

- [ ] **Step 5: `hooks.json`에 등록한다**

`hooks/hooks.json`의 `hooks` 객체에 `PreToolUse` 키를 추가하고 `description`을 갱신한다:

```json
{
  "description": "hwpx 판본 보존·검증 안전망. PreToolUse는 재변환(final/에 hwpx가 이미 있음)을 감지해 직전 변환 세트를 revisions/rNN/으로 보존한다(R073, generate_document만 — patch_document은 제자리 수정이라 제외). PostToolUse는 hwpx를 만들거나 고친 호출을 Bash와 kordoc MCP 양쪽에서 감지해, 정합 단계(postprocess_hwpx.py·md2hwpx.py)는 구조 검증과 후처리 흔적(R043 필수 멤버)까지 확인해 실패 시 block하고, 생성 단계(MCP)는 zip·XML 무결성만 보고 남은 후처리·검증을 비차단 리마인더로 돌려준다. 스크립트를 못 찾으면 아무 것도 하지 않는다.",
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "mcp__.*__generate_document",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/archive_revision_hook.py\""
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash|mcp__.*__(generate_document|patch_document)",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/verify_hwpx_hook.py\""
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 6: 전체 테스트 + 패키징 가드를 돌린다**

Run: `python3 -m pytest -q`
Expected: PASS 전건 (`test_plugin_structure.py`·`test_no_dead_code.py`가 새 훅을 문제 삼지 않는지 특히 확인 — 죽은 훅 감사가 있다)

Run: `python3 -c "import json;json.load(open('hooks/hooks.json'))"`
Expected: 오류 없음

- [ ] **Step 7: 커밋**

```bash
git add hooks/archive_revision_hook.py hooks/hooks.json tests/test_archive_revision_hook.py
git commit -m "판본 보존 PreToolUse 훅 — 레시피 §0.5 미호출 시 대신 보존 (R073)"
```

---

## 완료 확인

- [ ] `python3 -m pytest -q` 전건 통과
- [ ] `python3 skills/report-pipeline/scripts/doctor.py` exit 0
- [ ] `git status --short report/` 비어 있음 (실산출물 무변경 — 소급 정리는 이 계획 밖)
- [ ] `grep -c "R073" report/_harness/rules.md skills/report-pipeline/references/rules-seed.md` 양쪽 1

## 이 계획이 하지 않는 것

- `20260730/2046`·`20260807/2242`의 소급 정리 (spec §11)
- 판본 간 diff·롤백 기능
- 웹앱(`webapp/kca-report-hwpx/`) 반영 — work_dir 개념이 없다
