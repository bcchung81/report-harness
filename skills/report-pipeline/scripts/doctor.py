#!/usr/bin/env python3
"""하네스 자가진단 (R070) — 첫 실행 이탈을 막는다.

배경: 첫 실행에서 `kordoc`이 연결되지 않으면 **hwpx가 안 나오고 md만 나오는데**,
처음 쓰는 사람은 그게 실패인지도 모른 채 결과를 받는다. README에 증상 표가 있지만
수동 대조라 실패 지점을 스스로 찾아야 했다. 이 스크립트가 순서대로 찍어 **어디서
막혔는지 지목**한다.

MCP는 스크립트가 직접 호출할 수 없으므로(모델만 호출 가능) 여기서는 **실행 환경과
파일 계약까지** 검사하고, MCP 연결 확인은 모델이 이어서 수행하도록 안내를 낸다.

사용: doctor.py [--json]
종료: 0 = 이상 없음 / 1 = 경고 있음(동작은 함) / 2 = 치명(파이프라인 불가)
"""
import sys
import os
import json
import shutil
import subprocess
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "skills/report-pipeline/scripts"
REFS = ROOT / "skills/report-pipeline/references"

FATAL, WARN, OK = "치명", "경고", "정상"


def _v(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return (r.stdout + r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr) else ""
    except Exception:
        return ""


def harness_version(root=None):
    """하네스 버전 — 플러그인 매니페스트에서 읽는다. 문의·버그 보고 때 먼저 묻는 값이다('26.9.25). 스킬 사본으로 돌면
    매니페스트가 없어 None."""
    try:
        return json.loads(((root or ROOT) / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def checks():
    out = []

    # ⓪ 하네스 버전 — 갱신은 버전으로 판단된다(같은 버전이면 claude plugin update가 새 커밋을 받지 않는다)
    ver = harness_version()
    out.append({"항목": "하네스 버전", "상태": OK, "값": ver or "알 수 없음(스킬 사본 — 플러그인 매니페스트 없음)",
                "조치": ""})

    # ① 파이썬 — 스크립트 실행 주체
    ok = sys.version_info >= (3, 9)
    out.append({"항목": "Python 3.9+", "상태": OK if ok else FATAL,
                "값": ".".join(map(str, sys.version_info[:3])),
                "조치": "" if ok else "Python 3.9 이상 설치 후 재시도"})

    # ② Node/npx — kordoc MCP 실행 주체
    npx = shutil.which("npx")
    out.append({"항목": "npx (Node 18+)", "상태": OK if npx else FATAL,
                "값": _v(["node", "-v"]) or "없음",
                "조치": "" if npx else "Node.js 18+ 설치 — kordoc MCP가 npx로 실행된다"})

    # ③ 결정론 스크립트 존재·구문 (audit_style·archive_revision이 인벤토리에서 빠져 있었다)
    expected = ("harness_config.py", "lint_md_profile.py", "prep_report_md.py",
                "postprocess_hwpx.py", "validate_hwpx.py", "check_image_size.py",
                "extract_format_profile.py", "consolidate_rules.py",
                "audit_style.py", "archive_revision.py",
                "to_kordoc_input.py", "qa_report.py")
    missing = [n for n in expected if not (SCRIPTS / n).exists()]
    out.append({"항목": f"결정론 스크립트 {len(expected)}종", "상태": OK if not missing else FATAL,
                "값": f"{len(expected) - len(missing)}/{len(expected)}",
                "조치": f"누락: {missing}" if missing else ""})

    # ④ 규약 문서
    miss_ref = [n for n in ("style-guide.md", "md-profile.md", "hwpx-recipe.md",
                            "format-profile.kca.md", "rules-seed.md") if not (REFS / n).exists()]
    out.append({"항목": "규약 문서", "상태": OK if not miss_ref else FATAL,
                "값": f"{5 - len(miss_ref)}/5", "조치": f"누락: {miss_ref}" if miss_ref else ""})

    # ⑤ 설정 해석 — 산출물이 어디에 쌓이는지
    try:
        cfg = json.loads(subprocess.run([sys.executable, str(SCRIPTS / "harness_config.py")],
                                        capture_output=True, text=True, timeout=20).stdout)
        rd = cfg.get("reports_dir", "")
        out.append({"항목": "설정·산출물 경로", "상태": OK if rd else WARN,
                    "값": rd or "해석 실패", "조치": "" if rd else "harness_config.py 직접 실행해 확인"})
        vault = cfg.get("knowledge_vault")
        out.append({"항목": "vault 브릿지(선택)", "상태": OK,
                    "값": vault or "미설정 — 정상(없어도 전 구간 동작)", "조치": ""})
    except Exception as e:
        out.append({"항목": "설정·산출물 경로", "상태": FATAL, "값": str(e)[:40],
                    "조치": "harness_config.py 실행 오류 — Python 환경 확인"})

    # ⑥ 인증 방식 — 과금이 갈리는 지점이라 명시적으로 알린다
    key = os.environ.get("ANTHROPIC_API_KEY")
    out.append({"항목": "인증 방식", "상태": OK,
                "값": "API 키(종량제)" if key else "구독(OAuth)",
                "조치": "" if key else "팀 배포 시 API 키 종량제 검토 — README §4-0-1"})

    # ⑦ 규칙 체계 건전성
    try:
        r = subprocess.run([sys.executable, str(SCRIPTS / "consolidate_rules.py"), "--check"],
                           capture_output=True, text=True, timeout=20)
        out.append({"항목": "규칙 체계", "상태": OK if r.returncode == 0 else WARN,
                    "값": r.stdout.strip().splitlines()[0] if r.stdout else "",
                    "조치": "" if r.returncode == 0 else "consolidate_rules.py --check 참조"})
    except Exception:
        out.append({"항목": "규칙 체계", "상태": WARN, "값": "점검 실패", "조치": ""})

    # ⑧ 조치 예고된 미승격 lesson — 잊히는 경로를 눈에 보이게 한다
    out.append(pending_lessons_check())

    # ⑩ 설치 사본 신선도 — 저장소 체크아웃에서 돌릴 때만(개발 노트북: 스킬을 ~/.claude/skills 사본으로 쓰는 경우)
    cp = installed_copy_check()
    if cp:
        out.append(cp)

    # ⑨ 규칙 시드 동기화 — 플러그인이 갱신한 규칙이 운영본에 들어왔는가(설치자 환경)
    try:
        r = subprocess.run([sys.executable, str(SCRIPTS / "sync_rules.py")], capture_output=True, text=True, timeout=30)
        res = json.loads(r.stdout)
        added, upd, sup, col, changed, retired = (res.get(k, []) for k in
                                                  ("added", "updated", "superseded", "collision", "changed", "retired"))
        hist = res.get("history_added", [])     # 경위 로그에 없는 결번 기록 — 없으면 규칙 점검이 죽은 참조로 본다
        if res.get("missing"):
            out.append({"항목": "규칙 동기화", "상태": OK, "값": "운영 규칙 없음 — 첫 실행 때 시드를 복사한다", "조치": ""})
        else:
            parts = [f"새 규칙 {len(added)}건" if added else "", f"시드 갱신 {len(upd)}건" if upd else "",
                     f"폐지 {len(retired)}건" if retired else "", f"대체·정정 {len(sup)}건" if sup else "",
                     f"번호 충돌 {len(col)}건({', '.join(col[:3])})" if col else "",
                     f"본문 다른 규칙 {len(changed)}건" if changed else "",
                     f"경위 로그 {len(hist)}절" + (" (파일 없음)" if res.get("history_missing") else "") if hist else "",
                     f"통합 마커 → {res['marker']}" if res.get("marker") else ""]
            val = " · ".join(x for x in parts if x) or "시드와 일치"
            todo = added or upd or retired or sup or col or hist or res.get("marker")
            out.append({"항목": "규칙 동기화", "상태": WARN if todo else OK, "값": val,
                        "조치": ("로컬 규칙을 R9NN으로 옮긴 뒤 " if col else "") + ("sync_rules.py --apply" if todo else "")})
    except Exception:
        out.append({"항목": "규칙 동기화", "상태": WARN, "값": "점검 실패", "조치": ""})

    return out


# fix란이 '앞으로 고치겠다'로 읽히는 표현 — kind 필드가 없는 옛 기록('26.9.25 이전)을 참고로만 셀 때 쓴다.
PLEDGE = ("항구 대책", "보강", "필요", "검토", "해야", "추가 검토")
OPEN_KINDS = ("defect", "feature")      # 하네스 코드로 고칠 일 — 해결되면 resolved_by(커밋·R번호)를 단다


def installed_copy_check(repo=None, installed=None, files=None):
    """저장소의 하네스 스킬과 `~/.claude/skills` 사본이 같은가 — 다르면 새 세션이 옛 하네스로 돈다.

    '26.9.15 설치본에 factcheck.md가 없어 게이트①이 참조를 못 한 사고가 있었다. 저장소 체크아웃(.git)에서 돌릴 때만
    본다 — 플러그인 설치나 사본 안에서 돌리면 비교할 원본이 없어 None. files는 테스트용(기본: git ls-files skills).
    대상 스킬은 저장소 `skills/`의 하위 폴더 전부다 — 이름 목록을 따로 두면 새 스킬(cross-verify)이 빠졌다(리뷰 #2)."""
    repo = pathlib.Path(repo) if repo else ROOT
    installed = pathlib.Path(installed) if installed else pathlib.Path.home() / ".claude" / "skills"
    if files is None:
        if not (repo / ".git").exists():
            return None
        try:
            files = subprocess.run(["git", "-C", str(repo), "ls-files", "--", "skills"],
                                   capture_output=True, text=True, timeout=20).stdout.splitlines()
        except Exception:
            return None
    stale, present = [], False
    for f in files:
        parts = pathlib.PurePosixPath(f).parts
        if len(parts) < 3 or parts[0] != "skills" or not (installed / parts[1]).is_dir():
            continue
        present = True
        copy = installed / pathlib.Path(*parts[1:])
        if not copy.is_file() or copy.read_bytes() != (repo / f).read_bytes():
            stale.append("/".join(parts[1:]))
    if not present:
        return None                       # 사본을 쓰지 않는 환경(플러그인 설치)
    if not stale:
        return {"항목": "설치 사본", "상태": OK, "값": "~/.claude/skills 사본이 저장소와 일치", "조치": ""}
    return {"항목": "설치 사본", "상태": WARN, "값": f"사본과 다른 파일 {len(stale)}개 (예: {stale[0]})",
            "조치": "커밋 뒤 `git archive HEAD skills/…`로 ~/.claude/skills 사본 교체"}


def classify_lessons(rows):
    """(미해결 결함·기능, 옛 기록의 조치 예고 문구) — 두 목록.

    lesson에는 kind(content·defect·feature·preference)가 붙는다('26.9.25 스키마). 결함·기능은 규칙 승격 경로
    (2회 반복 → R0NN)를 타지 않아 잊히기 쉬우니 resolved_by가 없는 것을 센다. kind가 없는 옛 기록은
    harness_defect 표시만 결함으로 보고, 나머지는 fix란 키워드로 '참고' 목록에만 올린다 — 키워드는 끝난 조치
    ("…하도록 보강 — 적용")까지 세어 '26.9.25 자가진단의 '미조치 43건'이 부풀었다."""
    open_, legacy = [], []
    for row in rows:
        if row.get("resolved_by") or row.get("promoted"):
            continue
        kind = row.get("kind")
        if kind in OPEN_KINDS or (kind is None and row.get("harness_defect")):
            open_.append(row)
        elif kind is None and any(k in (row.get("fix") or "") for k in PLEDGE):
            legacy.append(row)
    return open_, legacy


def pending_lessons_check(path=None):
    """미해결 하네스 결함·기능 요청을 센다 — 강제하지 않고 보여만 준다(판단은 사람이 한다).

    실제로 '26.9.8 미승격 7건 중 둘이 '26.9.10 전수 검증에서 그대로 재현됐다(em대시 미검출·＊ 0건 문서에서
    후처리 전면 중단). 경로를 주지 않으면 설정의 state_dir/lessons.jsonl을 쓴다."""
    if path is None:
        try:
            cfg = json.loads(subprocess.run([sys.executable, str(SCRIPTS / "harness_config.py")],
                                            capture_output=True, text=True, timeout=20).stdout)
            path = pathlib.Path(cfg["state_dir"]) / "lessons.jsonl"
        except Exception:
            return {"항목": "미조치 lesson", "상태": OK, "값": "확인 불가 — 설정 해석 실패", "조치": ""}
    path = pathlib.Path(path)
    if not path.exists():
        return {"항목": "미조치 lesson", "상태": OK, "값": "축적본 없음 — 신규 설치", "조치": ""}
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line)) if line.strip() else None
        except ValueError:
            continue
    open_, legacy = classify_lessons(rows)
    note = f" · 옛 기록 조치 예고 문구 {len(legacy)}건(참고)" if legacy else ""
    if not open_:
        return {"항목": "미조치 lesson", "상태": OK, "값": "미해결 결함·기능 없음" + note, "조치": ""}
    oldest = min(r.get("date", "") for r in open_)
    return {"항목": "미조치 lesson", "상태": WARN,
            "값": f"미해결 결함·기능 {len(open_)}건 (가장 오래된 것 {oldest}){note}",
            "조치": "lessons.jsonl에서 kind=defect·feature이고 resolved_by가 없는 건을 고치고 resolved_by(커밋·R번호)를 단다"}


def main():
    res = checks()
    if "--json" in sys.argv:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        w = max(len(c["항목"]) for c in res)
        print("하네스 자가진단\n")
        for c in res:
            mark = {OK: "✓", WARN: "!", FATAL: "✗"}[c["상태"]]
            print(f"  {mark} {c['항목']:<{w}}  {c['값']}")
            if c["조치"]:
                print(f"    → {c['조치']}")
        print("\n  ※ kordoc MCP 연결은 스크립트가 확인할 수 없다(모델만 호출 가능) —")
        print("     `/mcp`로 kordoc이 connected인지 보고, 아니면 `npx -y kordoc mcp`를")
        print("     터미널에서 직접 실행해 오류를 확인한다. 미연결 시 hwpx 없이 md만 나온다.")
    fatal = sum(1 for c in res if c["상태"] == FATAL)
    warn = sum(1 for c in res if c["상태"] == WARN)
    return 2 if fatal else (1 if warn else 0)


if __name__ == "__main__":
    sys.exit(main())
