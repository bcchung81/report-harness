#!/usr/bin/env python3
"""하네스 실전 점검 — 가상 자료로 파이프라인 전 구간(자료 → 초안 → hwpx)을 헤드리스로 돌리고 결정론으로 채점한다.

'26.9.25 처음 돌려 CI가 못 보는 결함 3건(R054 절 어휘 경고·머리말 그림 오계수·승인 뒤 압축)을 찾았다. 회귀 테스트는
스크립트를 부품별로 보지만, 이 점검은 LLM이 SKILL.md를 읽고 실제로 끝까지 가는지를 본다. 규칙 판본을 바꿔 돌리면
규칙 문구 슬림화 같은 변경의 A/B가 된다(`--rules`).

    python3 scripts/smoke_pipeline.py [--runs N] [--rules <rules.md>] [--out <dir>] [--model <m>]
    python3 scripts/smoke_pipeline.py --score-only <out dir>      # 이미 돈 결과만 다시 채점

- 격리: 실행마다 임시 폴더에 설정 파일을 두고 `REPORT_HARNESS_CONFIG`로 가리킨다 — 산출물·규칙·교훈이 운영 폴더
  (`~/.claude/report-harness.json`의 reports_dir·state_dir)에 섞이지 않는다.
- 헤드리스 세션은 `claude -p … --dangerously-skip-permissions`로 돈다. 자기 하네스와 이 스크립트의 가상 자료로만
  쓰고, CI에서는 돌리지 않는다(로그인된 Claude Code와 kordoc MCP가 필요하다. 1회 약 10분·수 달러).
- 게이트 질문은 요청문에 미리 답해 둔다 — 사람이 답할 수 없다.
- 세션은 이 저장소가 아니라 설치된 하네스(`~/.claude/skills` 사본 또는 플러그인)를 읽는다 — 사본이 저장소와 다르면
  멈춘다(`--allow-stale`로 넘김). 안전망 훅 2종은 플러그인으로 설치돼 있을 때만 돈다.
- `--rules` 판본은 시드의 규칙 번호를 모두 담아야 한다 — 빠진 번호는 첫 단계(`sync_rules.py --apply`)가 되살려 A/B가
  무효가 된다. 줄이는 것은 본문으로 하고, 실행 뒤 운영본이 판본과 달라진 번호를 `rules_drift`로 보고한다.

exit 0: 모든 실행이 인도·검증 통과 | 1: 하나라도 실패 | 2: 인자·환경 오류
"""
import argparse
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/report-pipeline/scripts"
sys.path.insert(0, str(SCRIPTS))
import sync_rules  # noqa: E402  (규칙 줄 파서 단독 출처)

FIXTURE = """# 사내 생성형 AI 문서 초안 도우미 시범운영 결과 (가상 자료 — 하네스 점검용)

- 시범 기간: 2026. 7. 1. ~ 8. 31. (2개월), 대상: 3개 부서 42명
- 이용 실적: 문서 초안 생성 1,260건, 1인당 월평균 15건
- 처리 시간: 보도자료 초안 작성 평균 95분 → 38분(60% 단축, 20건 표본 실측)
- 검수 시간: AI 초안 검수에 건당 평균 12분 추가 소요 — 순절감은 건당 45분
- 만족도: 설문 응답 37명 중 30명(81%) '계속 사용 희망'
- 문제점: 수치·인용 오류가 초안 100건 중 7건 발견(검수 단계에서 모두 수정), 개인정보 입력 차단 기능 부재
- 비용: 시범 기간 사용료 월 180만 원(총 360만 원)
- 부서 의견: 반복 문서(회의록·결과보고) 효과가 크고, 정책 판단 문서는 효과 작음
- 요청 사항: 전사 확대 여부와 개인정보 차단 기능 도입을 10월 경영회의에서 결정받아야 함
"""

PROMPT = """report-pipeline 스킬로 이 폴더의 `자료.md`를 근거로 기관보고서(개조식) 1쪽 '결과 보고' 초안을 작성하고 hwpx로 변환해 인도해줘.

이 실행은 하네스 자동 점검이라 사람이 답할 수 없다. 질문(AskUserQuestion)을 쓰지 말고 아래 답으로 진행해 끝까지 인도한다.
- 게이트⓪: 문서 유형 = 결과 보고, 수신 = 부서장, 분량 = 1쪽 내외, 상황 전제 = 없음(확인함 — 발주·계약 전, 대응할 외부 지적 없음, 상위 계획서 없음), 조사 = 제공자료만(외부 조사 생략).
- 게이트①(아웃라인): 승인함. 게이트②(초안): 승인함, 팩트체크 = 경량.
- 라이브 리뷰어(review_server)는 띄우지 않는다 — 사람이 보지 않는다.
- 작업은 현재 폴더와 설정된 reports_dir·state_dir 안에서만 한다.
마지막에 산출 파일 경로(20_draft.md, hwpx)와 검증 결과(lint·audit·structural·compare)를 요약한다.
"""


def _run(*args):
    r = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)
    return r.returncode, r.stdout


def _rules(path):
    return sync_rules.rules(pathlib.Path(path).read_text(encoding="utf-8")) if pathlib.Path(path).is_file() else {}


def _json(text):
    try:
        return json.loads(text)
    except ValueError:
        return {}


def score(run_dir):
    """한 실행 폴더를 채점한다 — 사람 판단 없이 스크립트 결과만 모은다."""
    run_dir = pathlib.Path(run_dir)
    out = {"run": run_dir.name, "delivered": False}
    session = _json((run_dir / "session.json").read_text(encoding="utf-8")) if (run_dir / "session.json").exists() else {}
    out.update({k: session.get(k) for k in ("num_turns", "total_cost_usd", "duration_ms", "is_error")})
    out["session_ok"] = bool(session) and session.get("is_error") is False
    variant = run_dir / "rules_variant.md"
    if variant.is_file():                      # A/B 판본이 세션 동안 바뀌었나 — 되살아난·고쳐진 번호
        before, after = _rules(variant), _rules(run_dir / "state" / "rules.md")
        out["rules_drift"] = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    wds = sorted(p.parent for p in (run_dir / "reports").rglob("00_context.md"))
    out["work_dirs"] = len(wds)
    if len(wds) != 1:
        return out
    wd = wds[0]
    draft = wd / "20_draft.md"
    if draft.exists():
        rc, _ = _run(SCRIPTS / "lint_md_profile.py", draft)
        out["lint_ok"] = rc == 0
        audit = _json(_run(SCRIPTS / "audit_style.py", draft)[1])
        out["audit_violations"] = len(audit.get("violations", []))
        out["audit_warnings"] = sorted({w["rule"] for w in audit.get("warnings", [])})
    out["craft_missing"] = [k for k in ("context", "analysis", "outline") if _run(SCRIPTS / "check_craft.py", k, wd)[0] != 0]
    finals = sorted((wd / "final").glob("*.hwpx")) if (wd / "final").exists() else []
    out["revisions"] = len(finals)
    if finals:
        hwpx = finals[-1]
        out["structural_ok"] = _run(SCRIPTS / "validate_hwpx.py", "structural", hwpx)[0] == 0
        rev = sorted(wd.glob("history/r*/"))
        rt = sorted(wd.glob("history/r*/40_roundtrip.md"))
        if rt and draft.exists():
            rc, text = _run(SCRIPTS / "validate_hwpx.py", "compare", draft, rt[-1], "--hwpx", hwpx)
            cmp_ = _json(text)
            out["compare_issues"] = [i.get("rule") for i in cmp_.get("issues", [])]
            out["compare_ok"] = rc == 0            # 출력이 JSON이 아니어도(검사 자체가 깨져도) 통과로 세지 않는다
        post = sorted(wd.glob("history/r*/*postprocess*.json"))      # 이름은 실행마다 다르다(40_·42_)
        layout = _json(post[-1].read_text(encoding="utf-8")).get("layout", {}) if post else {}
        out["est_pages"] = layout.get("est_pages")
        out["delivered"] = (out["session_ok"] and bool(out.get("structural_ok")) and bool(out.get("compare_ok"))
                            and bool(rev))
    return out


def preflight(rules=None, allow_stale=False):
    """실행 전 확인 → 오류 문구 목록. 설치 사본이 저장소와 다르면 세션이 옛 하네스로 돌아 결과가 이 저장소를 말하지
    않는다. 규칙 판본은 시드 번호를 모두 담아야 한다('26.9.25 코드 리뷰 #4)."""
    errors = []
    if shutil.which("claude") is None:
        errors.append("claude CLI가 없다")
    if rules:
        if not rules.is_file():
            errors.append(f"규칙 파일 없음 {rules}")
        else:
            missing = sorted(set(sync_rules.rules(sync_rules.SEED.read_text(encoding="utf-8"))) - set(_rules(rules)))
            if missing:
                errors.append(f"규칙 판본에 시드 번호 {len(missing)}개가 없다({', '.join(missing[:5])}…) — 첫 단계가 되살려"
                              " A/B가 무효. 번호는 두고 본문을 줄인다")
    if not allow_stale:
        import doctor
        copy = doctor.installed_copy_check(ROOT)
        if copy and copy["상태"] != doctor.OK:
            errors.append(f"설치 사본이 저장소와 다르다({copy['값']}) — 사본을 교체하거나 --allow-stale")
    return errors


def run_once(run_dir, rules=None, model=None, max_turns=150, timeout=2700):
    run_dir = pathlib.Path(run_dir)
    if run_dir.exists() and any(run_dir.iterdir()):
        raise FileExistsError(f"이미 결과가 있는 폴더 — 다른 --out을 준다: {run_dir}")
    for sub in ("cwd", "reports", "state"):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)
    (run_dir / "cwd" / "자료.md").write_text(FIXTURE, encoding="utf-8")
    if rules:
        shutil.copyfile(rules, run_dir / "state" / "rules.md")      # 판본 규칙 — sync_rules가 빠진 번호를 되살린다
        shutil.copyfile(rules, run_dir / "rules_variant.md")         # 채점 때 되살아난·고쳐진 번호를 본다
    cfg = run_dir / "config.json"
    cfg.write_text(json.dumps({"reports_dir": str(run_dir / "reports"), "state_dir": str(run_dir / "state")},
                              ensure_ascii=False), encoding="utf-8")
    cmd = ["claude", "-p", PROMPT, "--dangerously-skip-permissions", "--max-turns", str(max_turns),
           "--output-format", "json"] + (["--model", model] if model else [])
    t0 = time.time()
    try:
        r = subprocess.run(cmd, cwd=run_dir / "cwd", env=dict(os.environ, REPORT_HARNESS_CONFIG=str(cfg)),
                           capture_output=True, text=True, timeout=timeout)
        (run_dir / "session.json").write_text(r.stdout, encoding="utf-8")
        (run_dir / "session.err").write_text(r.stderr, encoding="utf-8")
    except subprocess.TimeoutExpired:
        (run_dir / "session.err").write_text(f"timeout {timeout}s", encoding="utf-8")
    result = score(run_dir)
    result["wall_sec"] = int(time.time() - t0)
    return result


def summarize(results):
    keys = ("run", "delivered", "session_ok", "lint_ok", "audit_violations", "craft_missing", "compare_issues",
            "est_pages", "revisions", "num_turns", "total_cost_usd", "rules_drift")
    lines = [" | ".join(keys)]
    for r in results:
        lines.append(" | ".join(str(r.get(k)) for k in keys))
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="하네스 실전 점검(헤드리스 파이프라인 + 결정론 채점)")
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--rules", type=pathlib.Path, help="state_dir에 미리 둘 rules.md 판본(A/B용)")
    ap.add_argument("--out", type=pathlib.Path, help="결과 폴더(기본: 임시 폴더 아래 시각별)")
    ap.add_argument("--model")
    ap.add_argument("--max-turns", type=int, default=150)
    ap.add_argument("--timeout", type=int, default=2700)
    ap.add_argument("--score-only", type=pathlib.Path, help="이미 돈 결과 폴더(또는 실행 폴더 하나)를 다시 채점")
    ap.add_argument("--allow-stale", action="store_true", help="설치 사본이 저장소와 달라도 돌린다")
    a = ap.parse_args(argv)
    if a.score_only:
        if not a.score_only.is_dir():
            print(f"error: 폴더 없음 {a.score_only}", file=sys.stderr)
            return 2
        runs = ([a.score_only] if (a.score_only / "reports").is_dir() else
                sorted(p for p in a.score_only.iterdir() if p.is_dir() and (p / "reports").exists()))
        if not runs:
            print(f"error: 채점할 실행 폴더(reports/ 포함)가 없다 {a.score_only}", file=sys.stderr)
            return 2
        results = [score(p) for p in runs]
    else:
        errors = preflight(a.rules, a.allow_stale)
        if errors:
            for e in errors:
                print(f"error: {e}", file=sys.stderr)
            return 2
        out = a.out or pathlib.Path(tempfile.gettempdir()) / "report-harness-smoke" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        try:
            results = [run_once(out / f"run{i + 1}", a.rules, a.model, a.max_turns, a.timeout) for i in range(a.runs)]
        except FileExistsError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        (out / "summary.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"결과 폴더: {out}")
    print(summarize(results))
    return 0 if results and all(r.get("delivered") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
