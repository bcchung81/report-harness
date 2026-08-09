"""하네스 죽은 코드·미실행 경로 감사 (R070 자가진단의 정적 버전).

문서가 없는 기능을 있다고 하거나, 스크립트가 아무에게도 안 불리거나, 하네스와 웹앱 사본이
갈라지면 여기서 실패한다. 사람이 주기적으로 훑는 대신 테스트가 훑는다 —
'26.8.8 감사에서 실제로 `--star-indent`(CLI에서 제거됐는데 문서는 쓸 수 있다고 서술)와
죽은 훅(참조 대상이 전부 사라진 채 매 Bash마다 실행)이 나왔다.
"""
import ast, hashlib, pathlib, re, zipfile
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
COPIED = ("postprocess_hwpx.py", "validate_hwpx.py", "prep_report_md.py", "lint_md_profile.py")
# 플래그를 '없어졌다'고 알리는 문맥 — 사용 안내가 아니므로 유령이 아니다
REMOVED_CTX = re.compile(r"제거|폐기|거부|exit 2|쓰지 않는|사용하지")


def _scripts():
    for g in ("skills/report-pipeline/scripts/*.py", "scripts/*.py", "hooks/*.py",
              "webapp/kca-report-hwpx/scripts/*.py"):
        yield from ROOT.glob(g)


def test_no_orphan_scripts():
    """어느 문서·훅·테스트도 부르지 않는 스크립트가 있으면 안 된다."""
    callers = "".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for g in ("skills/*/SKILL.md", "skills/*/references/*.md", "commands/*.md",
                  "hooks/*", "tests/*.py", "scripts/*.py", "docs/*.md",
                  "webapp/kca-report-hwpx/SKILL.md")
        for p in ROOT.glob(g)) + (ROOT / "README.md").read_text(encoding="utf-8")
    assert [str(p) for p in _scripts() if p.name not in callers] == []


def test_no_uncalled_functions():
    """정의만 되고 저장소 어디서도 부르지 않는 함수가 있으면 안 된다.

    호출자 탐색은 추적 대상 소스로 한정한다 — rglob 전체를 돌면 gitignore된
    report/ 로컬 산출물이 우연히 같은 이름을 담아 죽은 함수를 가린다(머신별 결과 상이)."""
    corpus = list(_scripts()) + list(ROOT.glob("tests/*.py"))
    dead = []
    for f in _scripts():
        src = f.read_text(encoding="utf-8")
        defs = {n.name for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef)}
        for d in defs - set(re.findall(r"\b(\w+)\s*\(", src)) - {"main"}:
            if not any(d in o.read_text(encoding="utf-8", errors="ignore")
                       for o in corpus if o != f):
                dead.append(f"{f.name}:{d}")
    assert dead == []


def test_documented_cli_flags_exist():
    """문서가 쓸 수 있다고 서술한 플래그는 실제로 받아야 한다.

    '제거됐다'고 알리는 문맥은 예외 — 없어진 사실을 적는 것은 정확한 문서다."""
    real = set()
    for p in _scripts():
        s = p.read_text(encoding="utf-8")
        real |= set(re.findall(r'"(--[a-z-]+)"', s)) | set(re.findall(r"'(--[a-z-]+)'", s))
    ghost = []
    for p in list(ROOT.glob("skills/report-pipeline/references/*.md")) + list(ROOT.glob("skills/*/SKILL.md")):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for fl in re.findall(r"`(--[a-z][a-z-]{2,})`", line):
                if fl in real or fl == "--version" or REMOVED_CTX.search(line):
                    continue
                ghost.append(f"{p.name}:{i}:{fl}")
    assert ghost == []


def test_no_ghost_rule_references():
    """시드에 없는 R번호를 문서·코드가 참조하면 안 된다 (결번 이력 기재분은 예외)."""
    ref_dir = ROOT / "skills/report-pipeline/references"
    seed = set(re.findall(r"^- (R\d+) ",
                          (ref_dir / "rules-seed.md").read_text(encoding="utf-8"), re.M))
    retired = set(re.findall(r"^## (R\d+)",
                             (ref_dir / "rules-history.md").read_text(encoding="utf-8"), re.M))
    refs = set()
    for p in list(ROOT.glob("skills/**/*.md")) + list(ROOT.glob("skills/**/*.py")) + \
             list(ROOT.glob("hooks/*.py")) + [ROOT / "README.md"]:
        if "rules-seed" in str(p) or "rules-history" in str(p) or "humanizer" in str(p):
            continue
        refs |= set(re.findall(r"\bR0\d\d\b", p.read_text(encoding="utf-8", errors="ignore")))
    assert sorted(refs - seed - retired) == []


@pytest.mark.skipif(not (ROOT / "dist").is_dir(), reason="배포 패키지 미빌드")
def test_dist_packages_are_current():
    """빌드해 둔 패키지가 현재 스크립트를 담고 있어야 한다 — 구버전 배포 차단.

    복사본 4종 전부를 대조한다 — 1종만 보면 나머지가 stale인 패키지가 통과한다."""
    stale = []
    for name in COPIED:
        cur = hashlib.sha256(
            (ROOT / "skills/report-pipeline/scripts" / name).read_bytes()).hexdigest()
        stale += [f"{f.name}:{name}" for f in ROOT.glob("dist/*")
                  if hashlib.sha256(zipfile.ZipFile(f).read(f"kca-report-hwpx/scripts/{name}")).hexdigest() != cur]
    assert stale == []
