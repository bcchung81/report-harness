#!/usr/bin/env python3
"""webapp/kca-report-hwpx/ → 배포용 .skill 패키지 (설계문서 §8-4).

## 스킬 배포 기준 (전부 통과해야 빌드된다)

1. **룰 최신성** — `references/rules.md`를 하네스 룰 원본에서 **매 빌드 재생성**한다.
   손으로 복사한 사본을 그대로 싣지 않는다(스테일 룰로 배포되는 사고 차단).
   기본 원본은 `rules-seed.md`(공개 안전). `--rules`로 축적본
   (`report/_harness/rules.md`)을 지정할 수 있다.
2. **범위 필터** — 웹앱판은 ③초안·④변환만 하므로 `[draft]`·`[export]` 태그 룰만 싣는다.
3. **드리프트 0** — 하네스에서 복사한 스크립트 4종이 원본과 바이트 동일해야 한다.
4. **dangling 참조 0** — SKILL.md·references가 가리키는 스킬 내부 경로가 실재해야 한다.
5. **사장 자산 0** — 어떤 스크립트·문서도 참조하지 않는 assets 파일이 있으면 안 된다.
6. **출처 고정** — manifest.json에 전 파일 해시와 룰 원본·개수를 박는다.
7. **서드파티 고지** — 번들한 서드파티 폴더마다 `LICENSE`가 있고 루트 `NOTICE.md`가
   그 경로를 언급해야 한다. 번들 사본은 상류 원본과 바이트 동일해야 한다.
8. **루트 SKILL.md 단일** — 패키지 안에 SKILL.md가 둘 이상이면 매니페스트가 모호해진다.
9. **PII 0** — 패키지 전 파일에 전화·이메일이 없어야 한다(외부 3플랫폼 배포물).
   `--allow-drift`로도 우회되지 않으며, 위반 시 재생성한 rules.md를 이전 내용으로 원복해
   `--rules`로 지정한 내부 축적본이 소스 트리에 남지 않게 한다.

## 배포 타깃

플랫폼마다 패키지 확장자와 바이너리 허용 여부가 다르다(조사 '26.8.7).

| 타깃 | 확장자 | 바이너리 자산 | 근거 |
|---|---|---|---|
| `claude` | `.skill` | 그대로 | claude.ai Skills |
| `chatgpt` | `.zip` | 그대로 | Plugins → Skills → Upload |
| `gemini` | `.zip` | **`.b64` 텍스트로 변환** | Gemini Apps: 바이너리 업로드 불가 |

gemini 타깃은 `assets/*.png|bmp`를 base64 텍스트로 바꿔 싣고, 변환 직전에
`scripts/decode_assets.py`가 원본으로 되돌린다(멱등이라 타 타깃에서도 무해).

usage: build_webapp_skill.py [--target claude|chatgpt|gemini|all] [-o PATH] [--rules PATH]
exit 0 성공 / 1 기준 위반 / 2 구조 오류
"""
import sys, re, json, base64, hashlib, zipfile, pathlib, argparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pii_scan import scan_dir

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "webapp" / "kca-report-hwpx"
HARNESS = ROOT / "skills" / "report-pipeline"
SEED = HARNESS / "references" / "rules-seed.md"
COPIED = ("postprocess_hwpx.py", "validate_hwpx.py",
          "prep_report_md.py", "lint_md_profile.py")
# 하네스 references와 바이트 동일해야 하는 문서 사본 — 종전에는 스크립트 4종만 검사해
# 문서 쪽이 소리 없이 갈라질 수 있었다. diagram-pool.md는 의도적 분기라 제외한다
# (웹앱판은 도식 Pool 원형 hwpx를 싣지 않아 관련 서술이 다르다 — 설계문서 §4).
SYNCED_REFS = ("md-profile.md", "style-guide.md", "table-pool.md")
SCOPE_TAGS = ("[draft]", "[export]")
TARGETS = {"claude": ".skill", "chatgpt": ".zip", "gemini": ".zip"}
BINARY_EXT = (".png", ".bmp", ".jpg", ".jpeg", ".gif", ".hwpx", ".hwp")
EXCLUDE_DIRS = {"__pycache__", ".pytest_cache"}
EXCLUDE_NAMES = {".DS_Store", "manifest.json"}

RULE_LINE = re.compile(r"^- (R\d+) ((?:\[[a-z]+\])+) ", re.M)
INNER_PATH = re.compile(r"`((?:references|scripts|assets)/[^`\s]+)`")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def label(path):
    """저장소 안이면 저장소 상대 경로, 밖이면 절대 경로로 표기한다."""
    path = path.resolve()
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


# --- 기준 1·2: 룰 재생성 -----------------------------------------------------

def render_rules(source):
    """원본에서 [draft]·[export] 룰만 뽑아 웹앱용 rules.md를 만든다."""
    text = source.read_text(encoding="utf-8")
    lines = text.splitlines()
    starts = [(m.start(), m.group(1), m.group(2)) for m in RULE_LINE.finditer(text)]
    if not starts:
        raise ValueError(f"{source}에서 룰 항목을 찾지 못했습니다")
    kept, dropped = [], 0
    for i, (pos, rid, tags) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        block = text[pos:end].rstrip()
        if any(t in tags for t in SCOPE_TAGS):
            kept.append(block)
        else:
            dropped += 1
    header = (
        "# rules — kca-report-hwpx (웹앱판)\n\n"
        f"> 자동 생성물. 원본: {label(source)}\n"
        f"> 빌드 스크립트가 매 빌드 재생성한다 — **직접 고치지 말 것**.\n"
        f"> 웹앱판 범위(③초안·④변환)에 해당하는 `[draft]`·`[export]` 룰 {len(kept)}건만 담았다"
        f"(범위 밖 {dropped}건 제외).\n\n"
    )
    return header + "\n".join(kept) + "\n", len(kept), dropped


# --- 기준 3: 드리프트 --------------------------------------------------------

def check_drift():
    out = []
    pairs = [(HARNESS / "scripts" / n, SRC / "scripts" / n) for n in COPIED] + \
            [(HARNESS / "references" / n, SRC / "references" / n) for n in SYNCED_REFS]
    for a, b in pairs:
        if not b.is_file():
            out.append({"file": b.name, "reason": "웹앱 복사본 없음"})
        elif sha(a) != sha(b):
            out.append({"file": b.name, "reason": "하네스 원본과 불일치",
                        "harness": sha(a)[:12], "webapp": sha(b)[:12]})
    return out


# --- 기준 4·5: dangling 참조 / 사장 자산 -------------------------------------

def check_references(files):
    present = {str(p.relative_to(SRC)) for p in files}
    dangling = []
    for p in files:
        if p.suffix not in (".md", ".py"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for ref in set(INNER_PATH.findall(text)):
            if ref.endswith("/"):
                continue
            if ref not in present and not any(n.startswith(ref) for n in present):
                dangling.append({"in": str(p.relative_to(SRC)), "ref": ref})
    return dangling


def check_dead_assets(files):
    assets = [p for p in files if p.relative_to(SRC).parts[0] == "assets"]
    corpus = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in files if p.suffix in (".md", ".py"))
    dead = []
    for p in assets:
        rel = p.relative_to(SRC)
        # 디렉터리 단위로 참조되는 자산(kca-header-banner/*)은 상위 이름으로 판정
        stem = p.name[:-4] if p.name.endswith(".b64") else p.name
        if stem in corpus or rel.parts[1] in corpus or str(rel) in corpus:
            continue
        dead.append(str(rel))
    return dead


THIRD_PARTY = {"references/humanizer": ROOT / "skills" / "humanizer"}


def check_third_party(files):
    """기준 7 — 라이선스 동봉·고지·상류 일치."""
    out = []
    present = {str(p.relative_to(SRC)) for p in files}
    notice = (SRC / "NOTICE.md")
    notice_text = notice.read_text(encoding="utf-8") if notice.is_file() else ""
    if not notice_text:
        out.append({"item": "NOTICE.md", "reason": "루트 서드파티 고지 파일이 없음"})
    for rel, upstream in THIRD_PARTY.items():
        if f"{rel}/LICENSE" not in present:
            out.append({"item": rel, "reason": "LICENSE 미동봉"})
        if rel not in notice_text:
            out.append({"item": rel, "reason": "NOTICE.md에 경로 미기재"})
        # 상류 원본과 바이트 동일한지 (SKILL.md는 프론트매터 제거본이라 대상 제외)
        for up in sorted(upstream.rglob("*")):
            if not up.is_file() or up.name == "SKILL.md":
                continue
            # 패키지에 담기지 않는 것은 대조 대상도 아니다 — collect()와 같은 기준을 쓴다.
            # macOS에서 상류 폴더를 Finder로 한 번 열면 생기는 .DS_Store가 "누락"으로 잡혀
            # 빌드가 통째로 실패하던 경로다.
            if up.name in EXCLUDE_NAMES or EXCLUDE_DIRS.intersection(
                    up.relative_to(upstream).parts):
                continue
            mirror = SRC / rel / up.relative_to(upstream)
            if not mirror.is_file():
                out.append({"item": str(up.relative_to(upstream)), "reason": f"{rel}에 누락"})
            elif sha(up) != sha(mirror):
                out.append({"item": str(up.relative_to(upstream)), "reason": "상류와 불일치"})
    return out


def check_single_manifest(files):
    """기준 8 — SKILL.md는 루트 하나뿐이어야 한다."""
    found = [str(p.relative_to(SRC)) for p in files if p.name == "SKILL.md"]
    return [] if found == ["SKILL.md"] else [{"found": found, "expected": ["SKILL.md"]}]


def collect():
    out = []
    for p in sorted(SRC.rglob("*")):
        if not p.is_file() or p.name in EXCLUDE_NAMES:
            continue
        if EXCLUDE_DIRS & set(p.relative_to(SRC).parts):
            continue
        out.append(p)
    return out


def write_package(target, out, files, rules_meta):
    """타깃별 패키지를 쓴다. gemini는 바이너리 자산을 base64 텍스트로 바꿔 싣는다."""
    encoded = []
    members = {}
    for p in files:
        rel = str(p.relative_to(SRC))
        data = p.read_bytes()
        if target == "gemini" and p.suffix.lower() in BINARY_EXT:
            members[rel + ".b64"] = base64.b64encode(data)
            encoded.append(rel)
        else:
            members[rel] = data
    manifest = {
        "skill": "kca-report-hwpx",
        "target": target,
        "rules": rules_meta,
        "harness_scripts": {n: sha(HARNESS / "scripts" / n) for n in COPIED},
        "base64_encoded": encoded,
        "files": {k: hashlib.sha256(v).hexdigest() for k, v in members.items()},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, data in members.items():
            z.writestr(f"kca-report-hwpx/{rel}", data)
        z.writestr("kca-report-hwpx/manifest.json",
                   json.dumps(manifest, ensure_ascii=False, indent=1))
    return {"target": target, "output": str(out), "files": len(members) + 1,
            "bytes": out.stat().st_size, "base64_encoded": encoded}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="claude",
                    choices=list(TARGETS) + ["all"],
                    help="배포 대상 플랫폼 (기본 claude)")
    ap.add_argument("-o", "--output", default=None,
                    help="출력 경로 (기본 dist/kca-report-hwpx-{target}{확장자})")
    ap.add_argument("--rules", default=str(SEED),
                    help="룰 원본 (기본: rules-seed.md, 축적본은 report/_harness/rules.md)")
    ap.add_argument("--allow-drift", action="store_true")
    a = ap.parse_args(argv)

    if not (SRC / "SKILL.md").is_file():
        print(f"error: {SRC}/SKILL.md 없음", file=sys.stderr)
        return 2
    rules_src = pathlib.Path(a.rules).resolve()
    if not rules_src.is_file():
        print(f"error: 룰 원본 없음 — {rules_src}", file=sys.stderr)
        return 2
    # 인자 정합은 rules.md를 건드리기 **전에** 끝낸다 — 렌더 뒤에 두면 여기서 빠져나갈 때
    # --rules로 지정한 내부 축적본이 추적 파일(webapp/.../rules.md)에 남는다
    targets = list(TARGETS) if a.target == "all" else [a.target]
    if a.output and len(targets) > 1:
        print("error: --output은 단일 타깃에만 쓸 수 있습니다", file=sys.stderr)
        return 2

    # 기준 1·2 — 룰 재생성 (배포 전 항상 최신화). 검사(dangling·사장 자산)가 rules.md
    # 본문을 corpus로 읽으므로 먼저 쓰되, 기준 위반으로 빌드가 실패하면 이전 내용으로
    # 원복한다 — --rules로 지정한 내부 축적본이 소스 트리에 남는 경로를 막는다.
    rendered, n_kept, n_dropped = render_rules(rules_src)
    rules_dst = SRC / "references" / "rules.md"
    rules_prev = rules_dst.read_bytes() if rules_dst.is_file() else None

    def restore_rules():
        if rules_prev is None:
            rules_dst.unlink(missing_ok=True)
        else:
            rules_dst.write_bytes(rules_prev)

    rules_dst.write_text(rendered, encoding="utf-8")
    try:
        files = collect()
        violations = {
            "drift": check_drift(),
            "dangling_refs": check_references(files),
            "dead_assets": check_dead_assets(files),
            "third_party": check_third_party(files),
            "multiple_manifests": check_single_manifest(files),
            # 패키지는 외부 3플랫폼으로 나간다 — PII가 있으면 무조건 차단 (--allow-drift 무관)
            "pii": scan_dir(SRC),
        }
        blocking = {k: v for k, v in violations.items() if v and
                    not (k == "drift" and a.allow_drift)}
        if blocking:
            restore_rules()
            print(json.dumps({"violations": blocking}, ensure_ascii=False, indent=1))
            print("FATAL: 스킬 배포 기준 위반 — 위 항목을 고친 뒤 다시 빌드하세요", file=sys.stderr)
            return 1

        rules_meta = {"source": label(rules_src), "sha256": sha(rules_src),
                      "included": n_kept, "excluded": n_dropped, "scope": list(SCOPE_TAGS)}
        results = []
        for tgt in targets:
            out = pathlib.Path(a.output) if a.output else \
                ROOT / "dist" / f"kca-report-hwpx-{tgt}{TARGETS[tgt]}"
            results.append(write_package(tgt, out, files, rules_meta))
        print(json.dumps({"rules": rules_meta, "packages": results},
                         ensure_ascii=False, indent=1))
        return 0
    except BaseException:
        # 예외로 빠져나가도 내부 축적본이 공개 저장소 워킹트리에 남으면 안 된다
        restore_rules()
        raise


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
