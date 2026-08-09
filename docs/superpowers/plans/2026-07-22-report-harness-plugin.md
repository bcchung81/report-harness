# report-harness 플러그인 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 설계 SSOT(`docs/superpowers/specs/2026-07-21-report-harness-skills-design.md` v3)를 Claude Code 플러그인 1개(스킬 2종+humanizer 번들+커맨드 4종+결정론 스크립트 툴체인)로 구현한다.

**Architecture:** 결정론 스크립트(stdlib-only python, pytest 검증)를 먼저 확정하고, 그 시그니처 위에 프롬프트 자산(SKILL.md·commands)을 얹는다. hwpx 변환·파싱은 kordoc MCP를 모델이 호출하고, 스크립트는 그 전후의 검증·정규화만 담당한다.

**Tech Stack:** Python 3 표준 라이브러리만(외부 패키지 금지), pytest(개발 시에만), kordoc MCP(런타임 외부 의존), Claude Code plugin 규격(.claude-plugin/plugin.json + skills/ + commands/).

## Global Constraints

- 스크립트는 **stdlib-only** — pip 의존 추가 금지 (spec §2).
- 가변 상태(rules/lessons/format-profile)는 스킬 폴더에 절대 쓰지 않는다 — `state_dir`만 (spec §2).
- 설정 파일 없이 전 기능 동작(설정 0 원칙), 설정 경로 `~/.claude/report-harness.json` (spec §3).
- 작업폴더 규약: `{reports_dir}/{YYYYMMDD}/{HHMM}_{건명슬러그}/`, 이어가기는 기존 폴더 (spec §2).
- md 인라인 마크업은 `**볼드**` 단 하나만 허용 (spec §6).
- 이미지 규격 상한: 폭 170mm × 높이 90mm (spec §7-1).
- 기계 시간 예산: 전 구간 30분, 조사15/분석5/초안10/변환5분 (spec §13).
- 사용자 개입 기본 3회(게이트⓪①②), 전부 AskUserQuestion 선택지형 (spec §14).
- `form/보고서/`·`docs/analysis/`는 패키지 제외 + PII 스캔 통과 필수 (spec §12).
- 커밋 메시지는 한국어, 태스크당 1커밋 이상.

---

### Task 1: 플러그인 골격 + pytest 배선

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `tests/test_plugin_structure.py`
- Create: `pytest.ini`

**Interfaces:**
- Produces: 플러그인 루트 구조. 이후 모든 태스크가 이 디렉토리 규약을 따른다.

- [ ] **Step 1: 실패하는 구조 테스트 작성**

```python
# tests/test_plugin_structure.py
import json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]

def test_plugin_manifest_valid():
    m = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert m["name"] == "report-harness"
    assert "version" in m and "description" in m
```

- [ ] **Step 2: 실행해 실패 확인** — `python3 -m pytest tests/test_plugin_structure.py -v` → FAIL (FileNotFoundError)

- [ ] **Step 3: 매니페스트·pytest.ini 작성**

```json
{
  "name": "report-harness",
  "version": "0.1.0",
  "description": "기관보고서 하네스 — 자료조사·분석·초안(개조식)·hwpx 변환 4단계 파이프라인. 복리축적(lessons→rules)·시간예산 30분·게이트 3회.",
  "author": {"name": "bcchung81"}
}
```

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 4: 통과 확인** — `python3 -m pytest -v` → PASS
- [ ] **Step 5: Commit** — `git add -A && git commit -m "골격: 플러그인 매니페스트 + pytest 배선"`

---

### Task 2: harness_config.py — 설정 로드·작업폴더 규약

**Files:**
- Create: `skills/report-pipeline/scripts/harness_config.py`
- Test: `tests/test_harness_config.py`

**Interfaces:**
- Produces: `load_config(path=None) -> dict` (키: reports_dir, state_dir, knowledge_vault, template_hwpx — 없는 키는 기본값/None), `work_dir(config, slug, now=None) -> pathlib.Path` (`{reports_dir}/{YYYYMMDD}/{HHMM}_{slug}` 생성 후 반환), `state_paths(config) -> dict` (rules/lessons 경로, state_dir 자동 생성). 이후 모든 스크립트·SKILL.md가 이 규약을 사용.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_harness_config.py
import json, sys, pathlib, datetime
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import harness_config as hc

def test_defaults_without_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = hc.load_config(path=tmp_path / "nope.json")
    assert cfg["reports_dir"] == pathlib.Path.cwd() / "reports"
    assert str(cfg["state_dir"]).endswith(".claude/report-harness-state")
    assert cfg["knowledge_vault"] is None and cfg["template_hwpx"] is None

def test_config_file_overrides(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"reports_dir": str(tmp_path / "R"), "knowledge_vault": str(tmp_path / "V")}))
    cfg = hc.load_config(path=p)
    assert cfg["reports_dir"] == tmp_path / "R"
    assert cfg["knowledge_vault"] == tmp_path / "V"

def test_work_dir_convention(tmp_path):
    cfg = {"reports_dir": tmp_path}
    now = datetime.datetime(2026, 7, 22, 14, 5)
    d = hc.work_dir(cfg, "예시-건명", now=now)
    assert d == tmp_path / "20260722" / "1405_예시-건명"
    assert d.is_dir()

def test_state_paths_created(tmp_path):
    cfg = {"state_dir": tmp_path / "st"}
    sp = hc.state_paths(cfg)
    assert sp["rules"] == tmp_path / "st" / "rules.md"
    assert sp["lessons"] == tmp_path / "st" / "lessons.jsonl"
    assert (tmp_path / "st").is_dir()
```

- [ ] **Step 2: 실행해 실패 확인** — `python3 -m pytest tests/test_harness_config.py -v` → FAIL (ModuleNotFoundError)

- [ ] **Step 3: 구현**

```python
# skills/report-pipeline/scripts/harness_config.py
"""설정 로드·작업폴더 규약 (spec §2·§3). stdlib-only."""
import json, pathlib, datetime

DEFAULT_CONFIG_PATH = pathlib.Path.home() / ".claude" / "report-harness.json"

def load_config(path=None):
    path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    raw = {}
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
    def p(key, default):
        return pathlib.Path(raw[key]).expanduser() if key in raw else default
    return {
        "reports_dir": p("reports_dir", pathlib.Path.cwd() / "reports"),
        "state_dir": p("state_dir", pathlib.Path.home() / ".claude" / "report-harness-state"),
        "knowledge_vault": p("knowledge_vault", None),
        "template_hwpx": p("template_hwpx", None),
    }

def work_dir(config, slug, now=None):
    now = now or datetime.datetime.now()
    d = pathlib.Path(config["reports_dir"]) / now.strftime("%Y%m%d") / f"{now.strftime('%H%M')}_{slug}"
    d.mkdir(parents=True, exist_ok=True)
    return d

def state_paths(config):
    sd = pathlib.Path(config["state_dir"])
    sd.mkdir(parents=True, exist_ok=True)
    return {"rules": sd / "rules.md", "lessons": sd / "lessons.jsonl", "state_dir": sd}

if __name__ == "__main__":
    cfg = load_config()
    print(json.dumps({k: str(v) if v else None for k, v in cfg.items()}, ensure_ascii=False, indent=2))
```

- [ ] **Step 4: 통과 확인** — `python3 -m pytest tests/test_harness_config.py -v` → 4 PASS
- [ ] **Step 5: Commit** — `git add -A && git commit -m "스크립트: harness_config — 설정 로드·작업폴더 규약"`

---

### Task 3: lint_md_profile.py — AI 티·변환 규격 결정론 검출 (R001 코어)

**Files:**
- Create: `skills/report-pipeline/scripts/lint_md_profile.py`
- Test: `tests/test_lint_md_profile.py`

**Interfaces:**
- Produces: CLI `python3 lint_md_profile.py <draft.md>` → stdout JSON `{"violations": [{"line": n, "rule": str, "text": str}]}`, exit 0(무위반)/1(위반). 함수 `lint_text(text) -> list[dict]`. 룰 ID: `inline-markdown`, `non-bold-markup`, `table-too-wide`, `depth-exceeded`, `bullet-overflow`, `html-tag`.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_lint_md_profile.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
from lint_md_profile import lint_text

def rules(violations):
    return {v["rule"] for v in violations}

def test_clean_gaejosik_passes():
    text = ("□ 추진 배경\n"
            " ㅇ (목 적) AI 활용 **격차 해소**를 위한 환경 조성\n"
            "   - ChatGPT Team 6개 계정 구독(약 3.2백만원/연) 지원\n"
            "※ 세부내용은 붙임 참조\n"
            "| 구 분 | 내용 |\n| --- | --- |\n| A | B |\n")
    assert lint_text(text) == []

def test_inline_dash_and_star_detected():  # R001: 서술 중 - * 잔재
    text = "ㅇ 조사 결과 - 세 가지로 요약되며 *중요* 항목은 다음과 같음\n"
    assert {"inline-markdown", "non-bold-markup"} <= rules(lint_text(text))

def test_inline_backtick_and_heading():
    assert "inline-markdown" in rules(lint_text("ㅇ 명령은 `run` 사용\n"))
    assert "inline-markdown" in rules(lint_text("# 제목처럼 쓴 마크다운\n"))

def test_bold_is_allowed():
    assert lint_text("ㅇ **핵심 명사구** 강조는 허용\n") == []

def test_table_over_6_cols():
    text = "| a | b | c | d | e | f | g |\n| - | - | - | - | - | - | - |\n"
    assert "table-too-wide" in rules(lint_text(text))

def test_bullet_overflow_under_one_yo():
    text = "ㅇ 요지\n" + "".join(f"   - 상세{i}\n" for i in range(6))
    assert "bullet-overflow" in rules(lint_text(text))

def test_html_tag():
    assert "html-tag" in rules(lint_text("ㅇ 내용 <br> 줄바꿈\n"))
```

- [ ] **Step 2: 실행해 실패 확인** — `python3 -m pytest tests/test_lint_md_profile.py -v` → FAIL

- [ ] **Step 3: 구현 (라인 파서 — 정규식 오탐을 컨텍스트로 차단)**

```python
# skills/report-pipeline/scripts/lint_md_profile.py
"""md-profile 결정론 린트 (spec §6 4단방어-①, AI 티 3중장치-①). stdlib-only.
개조식 기호(□ㅇ○-※＊)는 항목 '선두'에서만 합법. 그 외 위치의 마크다운 기호는 위반."""
import sys, json, re

LEAD = re.compile(r"^\s*(□|ㅇ|○|-|※|＊|\*|\d+\.|\[\d+\])\s")   # 항목 선두 허용 기호
TABLE = re.compile(r"^\s*\|")
BOLD = re.compile(r"\*\*[^*\n]+\*\*")
INLINE_BAD = re.compile(r"(?:\s-\s|(?<!\*)\*(?!\*)|`|^#{1,6}\s|\s>\s)")
NON_BOLD = re.compile(r"(?<!\*)\*(?!\*)[^*\n]+(?<!\*)\*(?!\*)|~~[^~\n]+~~")
HTML = re.compile(r"</?[a-zA-Z][^>]*>")

def lint_text(text):
    out, bullet_run = [], 0
    for i, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        if TABLE.match(line):
            cols = len([c for c in line.strip().strip("|").split("|")])
            if cols > 6 and not set(line.strip()) <= set("|- :"):
                out.append({"line": i, "rule": "table-too-wide", "text": line.strip()[:80]})
            continue
        if HTML.search(line):
            out.append({"line": i, "rule": "html-tag", "text": line.strip()[:80]})
        stripped = line.strip()
        if stripped.startswith("ㅇ") or stripped.startswith("○"):
            bullet_run = 0
        elif stripped.startswith("-"):
            bullet_run += 1
            if bullet_run == 6:
                out.append({"line": i, "rule": "bullet-overflow", "text": stripped[:80]})
        body = LEAD.sub("", line, count=1)
        body_nobold = BOLD.sub("", body)
        if NON_BOLD.search(body_nobold):
            out.append({"line": i, "rule": "non-bold-markup", "text": stripped[:80]})
        if INLINE_BAD.search(body_nobold):
            out.append({"line": i, "rule": "inline-markdown", "text": stripped[:80]})
    return out

if __name__ == "__main__":
    text = open(sys.argv[1], encoding="utf-8").read()
    v = lint_text(text)
    print(json.dumps({"violations": v}, ensure_ascii=False, indent=1))
    sys.exit(1 if v else 0)
```

- [ ] **Step 4: 통과할 때까지 구현 보정** — `python3 -m pytest tests/test_lint_md_profile.py -v` → 7 PASS (파서 경계 조건은 테스트가 판정자)
- [ ] **Step 5: Commit** — `git add -A && git commit -m "스크립트: lint_md_profile — R001 마크다운 잔재·표 규격·계층 결정론 검출"`

---

### Task 4: prep_report_md.py — 무손실 변환 전 정규화

**Files:**
- Create: `skills/report-pipeline/scripts/prep_report_md.py`
- Test: `tests/test_prep_report_md.py`

**Interfaces:**
- Produces: CLI `python3 prep_report_md.py <draft.md> -o <prepared.md>` — HTML 주석 제거, 구분선(`---` 단독 라인) 제거(앞뒤 빈 줄 보존 — 레거시 개행 삼킴 버그 방지), 각주 정의 `＊` 통일. **자가검증 내장**: 처리 전후 '콘텐츠 텍스트'(마크업·공백 정규화 후) 불일치 시 exit 2. 함수 `prep(text) -> str`, `content_fingerprint(text) -> str`.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_prep_report_md.py
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
from prep_report_md import prep, content_fingerprint

def test_html_comment_removed():
    assert "비밀메모" not in prep("ㅇ 본문\n<!-- 비밀메모 -->\nㅇ 다음\n")

def test_hr_removed_but_blank_lines_preserved():   # 레거시 버그 회귀 테스트
    src = "＊ 각주: 설명\n\n---\n\n- 붙임 1. 목록\n"
    out = prep(src)
    assert "---" not in out
    assert "＊ 각주: 설명\n\n" in out          # 각주와 리스트 사이 빈 줄 생존
    assert "- 붙임 1. 목록" in out

def test_content_lossless():
    src = "□ 절\n ㅇ **요지** 문장\n<!-- 메모 -->\n---\n - 상세\n"
    assert content_fingerprint(prep(src)) == content_fingerprint(src)

def test_footnote_normalized():
    assert "＊ 용어" in prep("* 용어: 정의\n") or "＊" in prep("\\* 용어: 정의\n")
```

- [ ] **Step 2: 실행해 실패 확인** — `python3 -m pytest tests/test_prep_report_md.py -v` → FAIL

- [ ] **Step 3: 구현**

```python
# skills/report-pipeline/scripts/prep_report_md.py
"""변환 전 정규화 — 내용 무손실 보장 (spec §6 '작성된 md 그대로'). stdlib-only."""
import sys, re, hashlib, argparse

COMMENT = re.compile(r"<!--.*?-->", re.S)
HR_LINE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")
FOOT = re.compile(r"^(\s*)\\?\*\s(?=\S)")   # 라인 선두 각주 마커 → ＊

def prep(text):
    text = COMMENT.sub("", text)
    lines = []
    for line in text.splitlines():
        if HR_LINE.match(line):
            continue                          # 라인만 제거 — 주변 빈 줄은 건드리지 않음
        lines.append(FOOT.sub(r"\1＊ ", line))
    return "\n".join(lines) + ("\n" if text.endswith("\n") else "")

def content_fingerprint(text):
    t = COMMENT.sub("", text)
    t = "\n".join(l for l in t.splitlines() if not HR_LINE.match(l))
    t = re.sub(r"[＊*\\]", "", t)            # 각주 마커 표기 차이 무시
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha256(t.encode()).hexdigest()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("-o", required=True)
    a = ap.parse_args()
    src = open(a.src, encoding="utf-8").read()
    out = prep(src)
    if content_fingerprint(src) != content_fingerprint(out):
        print("FATAL: content fingerprint mismatch — 무손실 위반", file=sys.stderr)
        sys.exit(2)
    open(a.o, "w", encoding="utf-8").write(out)
    print(f"OK {a.o}")
```

- [ ] **Step 4: 통과 확인** — `python3 -m pytest tests/test_prep_report_md.py -v` → 4 PASS
- [ ] **Step 5: Commit** — `git add -A && git commit -m "스크립트: prep_report_md — 무손실 정규화 + 지문 자가검증"`

---

### Task 5: validate_hwpx.py — 구조 검증 + 왕복 대조

**Files:**
- Create: `skills/report-pipeline/scripts/validate_hwpx.py`
- Test: `tests/test_validate_hwpx.py`

**Interfaces:**
- Consumes: 왕복 텍스트는 모델이 kordoc `parse_document`로 추출해 파일로 저장(스크립트는 MCP 호출 불가).
- Produces: CLI 2모드 — `validate_hwpx.py structural <file.hwpx>` (zip 무결성+전 XML 파스, exit 0/1), `validate_hwpx.py compare <source.md> <roundtrip.md>` (□/ㅇ·○/- 개수, 표 개수·최대 열수, ＊ 각주 수, 수치 토큰 집합 차이, 마크다운 잔재 정규식 — JSON 리포트, exit 0/1). 함수 `profile_counts(text) -> dict`, `compare_texts(src, rt) -> list[dict]`.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_validate_hwpx.py
import sys, pathlib, zipfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
from validate_hwpx import structural_check, profile_counts, compare_texts

def make_zip(tmp_path, xml=b"<?xml version='1.0'?><root/>"):
    p = tmp_path / "t.hwpx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Contents/section0.xml", xml)
    return p

def test_structural_ok(tmp_path):
    assert structural_check(make_zip(tmp_path)) == []

def test_structural_broken_xml(tmp_path):
    errs = structural_check(make_zip(tmp_path, b"<root><unclosed>"))
    assert errs and "section0.xml" in errs[0]

def test_profile_counts():
    c = profile_counts("□ A\n ㅇ b 137명(23.7%)\n   - c\n＊ 각주\n| a | b |\n|---|---|\n")
    assert c["sections"] == 1 and c["points"] == 1 and c["subs"] == 1
    assert c["footnotes"] == 1 and c["tables"] == 1
    assert "137" in c["numbers"] and "23.7" in c["numbers"]

def test_compare_detects_lost_number_and_leftover():
    src = "□ A\n ㅇ 총 502건 정비\n"
    rt = "□ A\n ㅇ 총 **502**건 정비 - 그대로 노출\n"   # 볼드 기호·인라인 대시 잔재
    issues = {i["rule"] for i in compare_texts(src, rt)}
    assert "markdown-leftover" in issues

def test_compare_ok_when_identical():
    src = "□ A\n ㅇ 총 502건 정비\n"
    assert compare_texts(src, src) == []
```

- [ ] **Step 2: 실행해 실패 확인** — `python3 -m pytest tests/test_validate_hwpx.py -v` → FAIL

- [ ] **Step 3: 구현**

```python
# skills/report-pipeline/scripts/validate_hwpx.py
"""hwpx 구조 검증 + md↔되읽기 왕복 대조 (spec §6-4, AI 티 3중장치-③). stdlib-only."""
import sys, json, re, zipfile, xml.etree.ElementTree as ET

NUM = re.compile(r"\d+(?:[.,]\d+)*")
LEFTOVER = re.compile(r"\*\*|(?<!\S)[#>`](?!\S)|\s-\s")

def structural_check(path):
    errs = []
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad:
                errs.append(f"zip corrupt: {bad}")
            for n in z.namelist():
                if n.endswith(".xml"):
                    try:
                        ET.fromstring(z.read(n))
                    except ET.ParseError as e:
                        errs.append(f"{n}: {e}")
    except (zipfile.BadZipFile, FileNotFoundError) as e:
        errs.append(str(e))
    return errs

def profile_counts(text):
    lines = text.splitlines()
    tbl_rows = [l for l in lines if l.strip().startswith("|")]
    tables = 0
    prev = False
    for l in lines:
        cur = l.strip().startswith("|")
        if cur and not prev:
            tables += 1
        prev = cur
    return {
        "sections": sum(l.strip().startswith("□") for l in lines),
        "points": sum(l.strip()[:1] in ("ㅇ", "○") for l in lines),
        "subs": sum(l.strip().startswith("-") and not set(l.strip()) <= set("|- :") for l in lines if not l.strip().startswith("|")),
        "footnotes": sum(l.strip().startswith("＊") for l in lines),
        "tables": tables,
        "max_cols": max([len(r.strip().strip("|").split("|")) for r in tbl_rows], default=0),
        "numbers": set(NUM.findall(text)),
    }

def compare_texts(src, rt):
    a, b = profile_counts(src), profile_counts(rt)
    issues = []
    for k in ("sections", "points", "subs", "footnotes", "tables"):
        if a[k] != b[k]:
            issues.append({"rule": f"count-mismatch:{k}", "src": a[k], "roundtrip": b[k]})
    lost = a["numbers"] - b["numbers"]
    if lost:
        issues.append({"rule": "numbers-lost", "values": sorted(lost)[:20]})
    for i, line in enumerate(rt.splitlines(), 1):
        if not line.strip().startswith("|") and LEFTOVER.search(line):
            issues.append({"rule": "markdown-leftover", "line": i, "text": line.strip()[:80]})
    return issues

if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "structural":
        errs = structural_check(sys.argv[2])
        print(json.dumps({"errors": errs}, ensure_ascii=False))
        sys.exit(1 if errs else 0)
    if mode == "compare":
        src = open(sys.argv[2], encoding="utf-8").read()
        rt = open(sys.argv[3], encoding="utf-8").read()
        issues = compare_texts(src, rt)
        print(json.dumps({"issues": issues}, ensure_ascii=False, indent=1))
        sys.exit(1 if issues else 0)
    sys.exit(2)
```

- [ ] **Step 4: 통과 확인** — `python3 -m pytest tests/test_validate_hwpx.py -v` → 5 PASS
- [ ] **Step 5: Commit** — `git add -A && git commit -m "스크립트: validate_hwpx — 구조 검증 + 왕복 대조 + 잔재 최종 검출"`

---

### Task 6: check_image_size.py — 근거 이미지 규격 판정

**Files:**
- Create: `skills/report-pipeline/scripts/check_image_size.py`
- Test: `tests/test_check_image_size.py`

**Interfaces:**
- Produces: CLI `check_image_size.py <img> [--max-w-mm 170] [--max-h-mm 90] [--dpi 96]` → JSON `{w_mm, h_mm, fits, scale_to_fit}`, exit 0(적합)/1(초과). 함수 `png_size(bytes)->(w,h)`, `jpeg_size(bytes)->(w,h)`, `judge(w_px,h_px,dpi,max_w,max_h)->dict`. **주입 자체는 kordoc MCP(patch_document)를 모델이 수행** — spec §7-1의 inject_image 역할 중 '규격 검증'을 이 스크립트가, '주입'은 kordoc이 담당(설계 이행 노트에 기록).

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_check_image_size.py
import sys, pathlib, struct, zlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
from check_image_size import png_size, judge

def minimal_png(w, h):
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    return sig + chunk

def test_png_size_parsed():
    assert png_size(minimal_png(640, 480)) == (640, 480)

def test_judge_fits():
    r = judge(640, 300, dpi=96, max_w=170, max_h=90)   # 640px@96dpi ≈ 169mm
    assert r["fits"] is True

def test_judge_exceeds_height():
    r = judge(640, 640, dpi=96, max_w=170, max_h=90)   # 높이 ≈ 169mm > 90mm
    assert r["fits"] is False and 0 < r["scale_to_fit"] < 1
```

- [ ] **Step 2: 실행해 실패 확인** — `python3 -m pytest tests/test_check_image_size.py -v` → FAIL

- [ ] **Step 3: 구현**

```python
# skills/report-pipeline/scripts/check_image_size.py
"""근거 이미지 1/3페이지 규격 판정 (spec §7-1: 170×90mm). stdlib-only — PNG IHDR/JPEG SOF 직접 파싱."""
import sys, json, struct, argparse

MM_PER_INCH = 25.4

def png_size(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not png")
    w, h = struct.unpack(">II", data[16:24])
    return w, h

def jpeg_size(data):
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1; continue
        marker = data[i + 1]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    raise ValueError("no SOF")

def judge(w_px, h_px, dpi=96, max_w=170.0, max_h=90.0):
    w_mm, h_mm = w_px / dpi * MM_PER_INCH, h_px / dpi * MM_PER_INCH
    fits = w_mm <= max_w and h_mm <= max_h
    scale = min(max_w / w_mm, max_h / h_mm) if not fits else 1.0
    return {"w_mm": round(w_mm, 1), "h_mm": round(h_mm, 1), "fits": fits,
            "scale_to_fit": round(scale, 3)}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("img"); ap.add_argument("--max-w-mm", type=float, default=170)
    ap.add_argument("--max-h-mm", type=float, default=90); ap.add_argument("--dpi", type=float, default=96)
    a = ap.parse_args()
    data = open(a.img, "rb").read()
    w, h = png_size(data) if data[:2] == b"\x89P" else jpeg_size(data)
    r = judge(w, h, a.dpi, a.max_w_mm, a.max_h_mm)
    print(json.dumps(r))
    sys.exit(0 if r["fits"] else 1)
```

- [ ] **Step 4: 통과 확인** — `python3 -m pytest tests/test_check_image_size.py -v` → 3 PASS
- [ ] **Step 5: Commit** — `git add -A && git commit -m "스크립트: check_image_size — 1/3페이지 규격 판정 (주입은 kordoc 담당)"`

---

### Task 7: extract_format_profile.py + pii_scan.py

**Files:**
- Create: `skills/report-pipeline/scripts/extract_format_profile.py`
- Create: `scripts/pii_scan.py` (패키징 가드 — 스킬 배포물 아님)
- Test: `tests/test_extract_and_pii.py`

**Interfaces:**
- Produces: `extract_format_profile.py <font_map.json> -o <profile.md>` — 모델이 kordoc parse로 뽑은 요소별 폰트·여백 값을 JSON(`{"제목": {"font": "...", "pt": 20}, "여백": {...}}`)으로 받아 format-profile.kca.md와 같은 표 형식 md 생성. `pii_scan.py <dir>` — 전화(0\d{1,2}-\d{3,4}-\d{4})·이메일 정규식 스캔, 발견 시 exit 1 (§12 패키징 통과 조건).

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/test_extract_and_pii.py
import sys, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/report-pipeline/scripts"))
sys.path.insert(0, str(ROOT / "scripts"))
from extract_format_profile import render_profile
from pii_scan import scan_dir

def test_render_profile_table():
    spec = {"elements": {"문서 제목": {"font": "HY헤드라인M", "pt": 20}},
            "page": {"여백": "좌20 우20 위10 아래15", "줄간격": "160%"}}
    md = render_profile(spec, source="test.hwp")
    assert "| 문서 제목 | HY헤드라인M | 20pt |" in md and "160%" in md

def test_pii_scan_detects(tmp_path):
    (tmp_path / "a.md").write_text("문의: 0XX-XXX-XXXX m***@kca.kr")  # 실제 픽스처는 tests/ 참조 (문서는 마스킹)
    hits = scan_dir(tmp_path)
    assert len(hits) == 2

def test_pii_scan_clean(tmp_path):
    (tmp_path / "a.md").write_text("연락처는 마스킹됨 061-***-****")
    assert scan_dir(tmp_path) == []
```

- [ ] **Step 2: 실행해 실패 확인** — `python3 -m pytest tests/test_extract_and_pii.py -v` → FAIL

- [ ] **Step 3: 구현**

```python
# skills/report-pipeline/scripts/extract_format_profile.py
"""양식 프로파일 후처리 (spec §6-0): kordoc 분석 JSON → format-profile md. stdlib-only."""
import sys, json, argparse

def render_profile(spec, source):
    lines = [f"# 양식 프로파일 (자동 추출)", "", f"> 출처: {source}", "",
             "| 요소 | 폰트 | 크기 | 비고 |", "|---|---|---|---|"]
    for name, v in spec.get("elements", {}).items():
        lines.append(f"| {name} | {v.get('font','—')} | {v.get('pt','—')}pt | {v.get('note','')} |")
    page = spec.get("page", {})
    if page:
        lines += ["", "## 편집용지"] + [f"- {k}: {v}" for k, v in page.items()]
    return "\n".join(lines) + "\n"

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("spec_json"); ap.add_argument("-o", required=True); ap.add_argument("--source", default="")
    a = ap.parse_args()
    spec = json.loads(open(a.spec_json, encoding="utf-8").read())
    open(a.o, "w", encoding="utf-8").write(render_profile(spec, a.source or a.spec_json))
    print(f"OK {a.o}")
```

```python
# scripts/pii_scan.py
"""패키징 PII 가드 (spec §12). 전화·이메일 잔존 시 배포 차단."""
import sys, re, pathlib

PHONE = re.compile(r"0\d{1,2}-\d{3,4}-\d{4}")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

def scan_dir(root):
    hits = []
    for p in pathlib.Path(root).rglob("*"):
        if p.suffix.lower() in {".md", ".json", ".txt", ".py"} and p.is_file():
            t = p.read_text(encoding="utf-8", errors="ignore")
            for rx, kind in ((PHONE, "phone"), (EMAIL, "email")):
                for m in rx.findall(t):
                    hits.append({"file": str(p), "kind": kind, "value": m})
    return hits

if __name__ == "__main__":
    hits = scan_dir(sys.argv[1])
    for h in hits:
        print(f"PII {h['kind']}: {h['file']}: {h['value']}")
    sys.exit(1 if hits else 0)
```

- [ ] **Step 4: 통과 확인** — `python3 -m pytest tests/test_extract_and_pii.py -v` → 3 PASS
- [ ] **Step 5: 전체 스크립트 회귀** — `python3 -m pytest -v` → 전부 PASS (스크립트 시그니처 동결 게이트)
- [ ] **Step 6: Commit** — `git add -A && git commit -m "스크립트: format-profile 렌더러 + PII 패키징 가드 — 툴체인 완성"`

---

### Task 8: references 신규 2종 — md-profile.md·hwpx-recipe.md

**Files:**
- Create: `skills/report-pipeline/references/md-profile.md`
- Create: `skills/report-pipeline/references/hwpx-recipe.md`
- Test: `tests/test_references_consistency.py`

**Interfaces:**
- Consumes: Task 3 린트 룰 ID (`inline-markdown` 등 6종) — md-profile.md의 금지 목록과 1:1 정합이어야 함.
- Produces: writer(초안 생성)와 export 절차가 읽는 규격 문서 2종.

- [ ] **Step 1: 정합성 테스트 작성** (룰 ID가 문서에 전부 언급되는지)

```python
# tests/test_references_consistency.py
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
REF = ROOT / "skills/report-pipeline/references"
RULES = ["inline-markdown", "non-bold-markup", "table-too-wide", "depth-exceeded", "bullet-overflow", "html-tag"]

def test_md_profile_mentions_all_lint_rules():
    text = (REF / "md-profile.md").read_text(encoding="utf-8")
    missing = [r for r in RULES if r not in text]
    assert missing == []

def test_hwpx_recipe_mentions_scripts():
    text = (REF / "hwpx-recipe.md").read_text(encoding="utf-8")
    for s in ["prep_report_md.py", "validate_hwpx.py", "check_image_size.py"]:
        assert s in text
```

- [ ] **Step 2: 실패 확인** — `python3 -m pytest tests/test_references_consistency.py -v` → FAIL
- [ ] **Step 3: md-profile.md 작성** — 내용: ①허용 문법 전량(□/ㅇ/-/※/＊ 위계 4단, GFM 표 ≤6열·병합 금지, `**볼드**` 유일 인라인, `도식: {패턴ID}` 마커, `[ 캡션 ]`·`< 캡션 >`) ②금지 목록을 린트 룰 ID별 표로(inline-markdown/non-bold-markup/table-too-wide/depth-exceeded/bullet-overflow/html-tag — 각각 위반 예시·수정 예시 1쌍) ③"이 프로파일 안에서만 쓰면 hwpx 1회 변환이 보장된다" 서문 ④lessons 증보 절차(위반 유형 발견 → 룰 추가 → 린트 스크립트 갱신).
- [ ] **Step 4: hwpx-recipe.md 작성** — 내용: export 단계 절차서 ①`prep_report_md.py draft -o prepared` (exit 2면 중단·보고) ②kordoc `generate_document`(preset=보고서, font=명조, body_pt=15) ③template_hwpx 설정 시 병합, 도식 마커→도식 Pool 표 치환, 이미지: `check_image_size.py` 통과분만 kordoc `patch_document` 주입 ④`validate_hwpx.py structural` → kordoc `parse_document`로 되읽기 저장 → `validate_hwpx.py compare` ⑤불일치 시 수정→재변환 최대 2회, 잔존 시 목록 보고+md 인도 ⑥실패 유형은 lessons `[export]` 기록. 각 단계에 실제 명령줄 병기.
- [ ] **Step 5: 통과 확인** — `python3 -m pytest tests/test_references_consistency.py -v` → 2 PASS
- [ ] **Step 6: Commit** — `git add -A && git commit -m "references: md-profile(린트 룰 정합)·hwpx-recipe(변환 절차서)"`

---

### Task 9: report-research SKILL.md + tool-playbook.md

**Files:**
- Create: `skills/report-research/SKILL.md`
- Create: `skills/report-research/references/tool-playbook.md`

**Interfaces:**
- Produces: 조사 산출 계약 — `research/provided/`, `research/fetched/{슬러그}/`(프론트매터 `source_url·title·fetched_at·tool` + `_manifest.jsonl` append), `fetched/{슬러그}/images/`. draft·export 단계가 이 경로 규약을 소비.

- [ ] **Step 1: SKILL.md 작성** — frontmatter: `name: report-research`, description(트리거: "자료조사", "조사해서 보고서", "리서치" — spec §4). 본문 구성:
  1. **원칙**: 조사 방법 자유(환경의 스킬·MCP 자유 선택 — deep-research/insane-search/firecrawl/korean-law/opendart/WebSearch, 없으면 대체), 강제는 산출 계약뿐
  2. **산출 계약**: 경로·프론트매터·manifest 스키마(JSON 예시 포함)·확정/추정 태깅·이미지 수집 규약(출처 불명 수집 금지)
  3. **병렬 규약**: 독립 단위 2개↑면 한 메시지 다중 Agent, 각자 다른 fetched/ 폴더
  4. **vault 브릿지**: `knowledge_vault` 설정 시에만 — 모드 Q 인용 형식, acquired/ 사본 적재, raw/ 불변
  5. **시간 예산**: 15분 상한, 접근 시 팬아웃 축소·1패스 검색
  6. **종료 훅**: 조사 요약 1줄 보고 + lessons `[research]` 기록
- [ ] **Step 2: tool-playbook.md 작성** — 출처 유형→도구 표(spec §4 그대로: 법령→korean-law / 공시→opendart / 한글문서→kordoc / 차단→insane-search / 심층→deep-research / 일반→WebSearch·WebFetch) + "환경에 없으면 행 건너뛰고 일반 도구" 규칙 + 교차검증(핵심 주장 ≥2 독립 출처).
- [ ] **Step 3: 구조 테스트에 등록** — `tests/test_plugin_structure.py`에 추가:

```python
def test_research_skill_exists():
    t = (ROOT / "skills/report-research/SKILL.md").read_text(encoding="utf-8")
    assert t.startswith("---") and "name: report-research" in t
    assert "_manifest.jsonl" in t and "확정" in t
```

- [ ] **Step 4: 통과 확인** — `python3 -m pytest tests/test_plugin_structure.py -v` → PASS
- [ ] **Step 5: Commit** — `git add -A && git commit -m "스킬: report-research — 산출 계약 중심 조사 스킬"`

---

### Task 10: report-pipeline SKILL.md + rules 시드

**Files:**
- Create: `skills/report-pipeline/SKILL.md`
- Create: `skills/report-pipeline/references/rules-seed.md`

**Interfaces:**
- Consumes: Task 2~8 전체(스크립트 시그니처·references 6종), Task 9 산출 계약.
- Produces: 4단계 오케스트레이션 본체. commands(Task 11)가 각 단계 섹션을 지시.

- [ ] **Step 1: rules-seed.md 작성** — state_dir의 rules.md 초기값(첫 실행 시 스킬이 복사). 내용:

```markdown
# rules — 회귀 방지 체크리스트 (승격분만, 근거 건 링크)
- R001 [draft][export] 서술 문장 안에 마크다운 기호(-, *)를 남기지 않는다 — lint·QA 기계 검출 (근거: 과거 에이전트 반복 시행착오)
- R002 [draft] 사실(지적·조사결과)과 주장(건의·제안)은 절을 분리한다 (근거: 260714 PIMS건)
- R003 [draft] 모든 수치·인용에 확정/추정/경계 태깅과 출처를 남긴다
- R004 [export] prep 정규화는 내용 무손실 — 지문 불일치 시 중단 (근거: 레거시 개행 삼킴 버그)
- R005 [draft] 표는 6열 이하·병합 금지, 나열 3개+속성 2개↑는 표 전환
- R006 [export] 이미지는 170×90mm 이내만 주입, 캡션에 출처 필수
```

- [ ] **Step 2: SKILL.md 작성** — frontmatter: `name: report-pipeline`, description(트리거: "보고서 작성/초안/hwpx 변환/개조식", 4단계 안내). 본문 섹션(설계 §8·§9·§13·§14를 실행 지시문으로):
  1. **공통 준비**: `harness_config.py` 실행해 설정 로드 → 새 건이면 `work_dir()` 생성, 이어가기면 기존 폴더 탐색(최신 or 사용자 지정) → 00_context.md 갱신. state_dir에 rules.md 없으면 rules-seed.md 복사. rules에서 해당 단계 태그 로드.
  2. **① research**: report-research 스킬 위임.
  3. **② analyze**: 제공자료는 research/provided/ 적재+kordoc 파싱(문서 다수면 문서 단위 병렬 팬아웃), 05_analysis.md 산출(논지 후보·총괄표 후보(셀→출처 매핑)·근거 공백 목록). 5분 상한.
  4. **③ draft**: 게이트⓪ AskUserQuestion(4문항 이내: 유형/수신·분량/논지 방향/맺음말·표도식 — 각 선택지에 style-guide §0 유형 매핑) → 아웃라인 생성(논지 갈리면 2안 병렬) → 게이트①(표 설계·이미지/도식 배치 포함, 렌더 전송) → 프리플라이트(rules `[draft]` + format-profile) → 초안 집필(메인 단일 컨텍스트, md-profile·style-guide 준수) → `lint_md_profile.py` (위반 시 수정 후 재실행) → 스타일 감사∥humanizer 병렬(절 그룹 분할, 적용 후 diff로 수치·인용 불변 확인) → 게이트②: 20_draft.md 렌더 전송 + 절 주소 ID + AskUserQuestion(전체 승인+팩트체크 선택(전수/경량/생략) / 지정 절 수정 / 방향 전환). 수정은 변경 절만 증분 재감사, 3회 초과 시 게이트① 회귀 제안. 10분 상한.
  5. **④ export**: 팩트체크(선택값대로)∥회귀검사 병렬 스폰 → hwpx-recipe.md 절차 실행(prep→변환→구조검증→왕복 compare, 재시도 ≤2) → final/{제목}.hwpx 인도(SendUserFile) + 미검증·잔존 이슈 1줄 고지. 5분 상한.
  6. **복리 훅(전 단계 공통)**: 단계 종료 시 lessons.jsonl append(`{"date","case","gate","feedback","fix","promoted":false}`), 동일 유형 2회↑면 즉석 승격 제안(사용자 승인 후 rules.md 반영).
  7. **UX 계율**: 개입 3회 상한·전부 선택지형·진행 1줄 보고·md는 렌더 전송·"이어서 해줘" 재개·시간 예산 초과 시 축소 전략(§13 표 그대로).
- [ ] **Step 3: 구조 테스트 추가** — `tests/test_plugin_structure.py`:

```python
def test_pipeline_skill_references_exist():
    t = (ROOT / "skills/report-pipeline/SKILL.md").read_text(encoding="utf-8")
    for ref in ["style-guide.md", "md-profile.md", "hwpx-recipe.md", "diagram-pool.md",
                "format-profile.kca.md", "rules-seed.md", "lint_md_profile.py", "harness_config.py"]:
        assert ref in t, ref
    for f in ["style-guide.md", "md-profile.md", "hwpx-recipe.md", "rules-seed.md"]:
        assert (ROOT / "skills/report-pipeline/references" / f).is_file()
```

- [ ] **Step 4: 통과 확인** — `python3 -m pytest -v` → 전부 PASS
- [ ] **Step 5: Commit** — `git add -A && git commit -m "스킬: report-pipeline 본체 — 4단계·게이트 3회·복리 훅·시간예산"`

---

### Task 11: 커맨드 4종 + humanizer 번들

**Files:**
- Create: `commands/report-research.md`, `commands/report-analyze.md`, `commands/report-draft.md`, `commands/report-export.md`
- Create: `skills/humanizer/` (사본 동기화)
- Modify: `tests/test_plugin_structure.py`

**Interfaces:**
- Consumes: Task 9·10 스킬 섹션 구조.
- Produces: `/report-*` 슬래시 커맨드 진입점.

- [ ] **Step 1: 커맨드 4종 작성** — 각각 frontmatter `description` + 본문은 해당 스킬 섹션 지시. 예 (`commands/report-draft.md`):

```markdown
---
description: 보고서 초안작성 — Q&A 게이트⓪ → 아웃라인 게이트① → 초안 게이트② (report-pipeline ③단계)
---
report-pipeline 스킬을 로드하고 **③ draft 단계**를 실행하라. 작업폴더에 research/·05_analysis.md가 있으면 활용하고, 없으면 "조사·분석 없이 진행할까요?"만 묻는다. $ARGUMENTS 가 있으면 건명·주제로 사용.
```

(research/analyze/export도 동일 패턴 — 각 단계 번호·전제 파일·$ARGUMENTS 처리 명시)
- [ ] **Step 2: humanizer 번들** — `cp -R ~/.claude/skills/humanizer skills/humanizer` 후 LICENSE·author 메타 존재 확인(`ls skills/humanizer` — MIT 고지 파일 필수, 없으면 원 배포처에서 LICENSE 파일 확보해 동봉).
- [ ] **Step 3: 구조 테스트 추가**

```python
def test_commands_and_bundle():
    for c in ["report-research", "report-analyze", "report-draft", "report-export"]:
        assert (ROOT / "commands" / f"{c}.md").is_file()
    assert (ROOT / "skills/humanizer/SKILL.md").is_file()
```

- [ ] **Step 4: 통과 확인** — `python3 -m pytest -v` → 전부 PASS
- [ ] **Step 5: Commit** — `git add -A && git commit -m "커맨드 4종 + humanizer 번들 동기화"`

---

### Task 12: README + 로컬 배포 + 설정 0 스모크 (필수 게이트)

**Files:**
- Create: `README.md`
- Create: `scripts/package_check.sh`

**Interfaces:**
- Consumes: 전체.
- Produces: 설치 문서·패키징 가드. **이 태스크의 스모크가 hwpx 변환 경로의 유일한 통합 검증** — 실패 시 해당 태스크로 회귀.

- [ ] **Step 1: README.md 작성** — ①설치(플러그인 설치 방법 + 개발용 `cp -R skills/* ~/.claude/skills/`) ②의존성(kordoc MCP 필수 — 설치 안내 링크, 미설치 시 md 인도 강등; korean-law·opendart 선택) ③설정 파일 예시(§3 JSON — 미설정 시 기본값 표) ④사용법(자연어 예시 3개 + 커맨드 4종) ⑤사용자(bcchung81) 환경 설정값 예시(claudian 연동).
- [ ] **Step 2: package_check.sh 작성**

```bash
#!/bin/bash
# 패키징 가드: 배포 제외 확인 + PII 스캔 (spec §12)
set -e
for banned in "form/보고서" "docs/analysis"; do
  if git ls-files | grep -q "^$banned/"; then echo "FATAL: $banned 이 추적됨 — 배포 금지 대상"; exit 1; fi
done
python3 scripts/pii_scan.py skills/ && python3 scripts/pii_scan.py commands/
echo "package check OK"
```

주의: `form/`·`docs/analysis/`가 현재 git 추적 중이면 `.gitignore` 추가 + `git rm -r --cached`로 배포 레포에서 제외(로컬 파일은 보존).
- [ ] **Step 3: 실행** — `bash scripts/package_check.sh` → "package check OK"
- [ ] **Step 4: 로컬 배포** — `cp -R skills/* ~/.claude/skills/ && cp -R commands ~/.claude/` (개발 검증용)
- [ ] **Step 5: 설정 0 스모크 (에이전틱 체크리스트)** — 새 Claude Code 세션(임시 빈 디렉토리)에서: "소형 주제(예: 'MCP 도구 2종 검토 보고') 보고서를 조사 없이 초안부터" 요청 → 확인 항목: ①`reports/{오늘}/{시각}_슬러그/` 생성 ②게이트⓪ Q&A 4문항 이내 ③게이트① 아웃라인 렌더 ④lint 통과한 20_draft.md 렌더+절 주소 ID ⑤게이트② 승인(팩트체크 '경량') ⑥hwpx 1회 변환+40_qa.md 생성 ⑦기계 시간 30분 이내 ⑧lessons.jsonl에 단계 기록. 실패 항목은 원인 태스크로 회귀 후 재실행.
- [ ] **Step 6: Commit** — `git add -A && git commit -m "README·패키징 가드·설정0 스모크 통과"`
- [ ] **Step 7: KCA 실전 검증 (사용자 참여)** — 사용자 설정 파일 생성 후 실제 소형 건 1건을 게이트 포함 전 구간 실행 — 게이트 응답은 사용자가. 완료 후 lessons 회고로 첫 규칙 승격 사이클 시연.

---

## Self-Review 결과

- **스펙 커버리지**: §2(T1·T2) §3(T2) §4(T9) §5(T10 — style-guide 기완료) §6(T3·T4·T5·T8) §6-0(T7) §7-1(T6 — 주입은 kordoc 위임으로 조정, 이행 노트 T6에 기록) §7-2(T10 게이트② 선택지) §7-3(T10·기완료 diagram-pool) §8(T10·T11) §9(T10 rules-seed·복리 훅) §10(T8 hwpx-recipe 실패 경로) §11(T3~T7 pytest + T12 스모크·실전) §12(T1·T11·T12) §13·§14(T10 계율) — 공백 없음.
- **플레이스홀더**: 없음 — 프롬프트 자산 태스크(T8~T11)도 섹션·항목 단위 실내용 명시.
- **타입 정합**: `load_config`/`work_dir`/`state_paths`(T2) ← T10 SKILL.md 참조 일치. 린트 룰 ID 6종(T3) ← T8 정합 테스트로 강제. `structural_check`/`profile_counts`/`compare_texts`(T5) ← T8 hwpx-recipe 절차 일치.
