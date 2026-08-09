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


def checks():
    out = []

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

    # ③ 스크립트 8종 존재·구문
    missing = [n for n in ("harness_config.py", "lint_md_profile.py", "prep_report_md.py",
                           "postprocess_hwpx.py", "validate_hwpx.py", "check_image_size.py",
                           "extract_format_profile.py", "consolidate_rules.py")
               if not (SCRIPTS / n).exists()]
    out.append({"항목": "결정론 스크립트 8종", "상태": OK if not missing else FATAL,
                "값": f"{8 - len(missing)}/8", "조치": f"누락: {missing}" if missing else ""})

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

    return out


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
