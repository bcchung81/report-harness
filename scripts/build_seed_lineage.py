#!/usr/bin/env python3
"""규칙 시드 계보 갱신 — 지금까지 배포한 시드 규칙 줄의 지문(sync_rules.fingerprint)을 모은다.

`sync_rules.py`는 이 계보로 설치자 운영본의 규칙 줄이 '손대지 않은 옛 시드 줄'인지 가린다. 계보에 있는 줄은
새 시드 줄로 바꾸고(시드 정정이 설치자에게 도달), 시드에서 폐지된 번호의 옛 줄은 지운다. 계보에 없는 줄은
설치자가 고친 것이라 건드리지 않는다. 계보가 없던 때는 0.4.0 설치자의 옛 시드 줄 7건을 '번호 충돌'로 오판해
새 값이 들어가지 않았다('26.9.25 격리 설치 재현).

    python3 scripts/build_seed_lineage.py          # 현재 시드 줄을 계보에 더한다 — 시드를 고친 뒤 커밋 전에(테스트가 강제)
    python3 scripts/build_seed_lineage.py --git    # git 이력의 모든 시드 판본에서 다시 모은다(처음 한 번·복구용)
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/report-pipeline/scripts"))
import sync_rules as sr  # noqa: E402

SEED_REL = "skills/report-pipeline/references/rules-seed.md"
ABOUT = ("배포한 적 있는 시드 규칙 줄의 지문(줄 앞뒤 공백 제거 뒤 sha1 앞 10바이트의 base32). sync_rules.py가 설치자 운영본의 줄이 "
         "손대지 않은 옛 시드 줄인지 가린다. 손으로 고치지 말고 scripts/build_seed_lineage.py로 갱신한다.")


def git_versions():
    """git 이력의 시드 판본 본문들 — 이름이 바뀐 판본도 따라간다."""
    out = subprocess.run(["git", "-C", str(ROOT), "log", "--format=@%H", "--name-only", "--follow", "--", SEED_REL],
                         capture_output=True, text=True, check=True).stdout
    rev = None
    for line in out.splitlines():
        if line.startswith("@"):
            rev = line[1:]
        elif line.strip() and rev:
            show = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{line.strip()}"],
                                  capture_output=True, text=True)
            if show.returncode == 0:
                yield show.stdout
            rev = None


def load_strict():
    """기존 계보 — 파일이 있는데 읽지 못하면 멈춘다. sync_rules.load_lineage()는 깨진 파일을 빈 계보로 넘기므로 여기서
    쓰면 현재 시드 줄만으로 덮어써 과거 지문을 말없이 잃는다('26.9.25 코드 리뷰 #3)."""
    if not sr.LINEAGE.exists():
        return {}
    try:
        return {k: set(v) for k, v in json.loads(sr.LINEAGE.read_text(encoding="utf-8"))["rules"].items()}
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        sys.exit(f"계보 파일을 읽지 못했다({e}) — 고치거나 `--git`으로 git 이력에서 다시 모은다: {sr.LINEAGE}")


def build(from_git=False):
    lineage = {} if from_git else load_strict()
    texts = list(git_versions()) if from_git else []
    texts.append((ROOT / SEED_REL).read_text(encoding="utf-8"))
    for text in texts:
        for k, line in sr.rules(text).items():
            lineage.setdefault(k, set()).add(sr.fingerprint(line))
    data = {"about": ABOUT, "rules": {k: sorted(v) for k, v in sorted(lineage.items())}}
    sr.LINEAGE.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return sum(len(v) for v in lineage.values()), len(texts)


if __name__ == "__main__":
    n, versions = build("--git" in sys.argv[1:])
    print(f"계보 갱신 — 규칙 줄 지문 {n}개(시드 판본 {versions}개 반영) → {sr.LINEAGE.relative_to(ROOT)}")
