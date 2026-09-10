#!/usr/bin/env python3
"""작업폴더 이력 관리 — 초안 스냅샷·변환 판본 아카이브 (R086). stdlib-only.

배경('26.9.10 실측): 초안 판본 15개가 `_v6`·`.20260907-교차검증전`·`.이전판-2종` 세 갈래
표기로 현행 파일 옆에 쌓여 있었고, `final/`에 hwpx가 여럿인 건이 6건이라 어느 것이 현행본인지
파일만 보고는 판별되지 않았다. '26.8.12 설계(`docs/superpowers/specs/…-export-revision-archive-design.md`)가
이 문제를 이미 다뤘으나 구현이 없었다.

이 스크립트가 정하는 것은 **위치와 표기**뿐이다. 무엇을 언제 남길지는 사람이 정한다
(스냅샷은 게이트 시점에 사유를 붙여 명시적으로 뜬다 — 훅 자동 스냅샷은 Edit마다 쌓여
이력이 잡음이 되므로 채택하지 않았다).

폴더 규약:

    {work_dir}/
    ├── 20_draft.md …                      현행본 (이름 불변 — 각 단계의 인터페이스)
    ├── final/r01_20260907_{제목}.hwpx      인도본이 버전별로 쌓인다(접두어로 즉시 판별)
    └── history/
        ├── index.jsonl                    1건 1줄 append
        ├── drafts/                        아직 변환되지 않은 초안 스냅샷
        └── r01_20260907-0831/             그 판본 hwpx를 만든 md 세트
            ├── 20_draft.md · 40_prepared.md · 43_convert_input.md · 40_roundtrip.md · 40_qa.md
            └── drafts/                    그 판본에 딸렸던 초안 스냅샷

hwpx는 `history/`로 복사하지 않는다 — `final/`에 버전 접두어로 남으므로 중복이다.
`research/`도 복사하지 않는다(append-only 자산이라 판본마다 복사하면 원본이 중복된다).
"""
import sys
import re
import json
import shutil
import argparse
import datetime
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from prep_report_md import content_fingerprint          # noqa: E402  (같은 scripts/ 폴더)

# 판본과 함께 아카이브하는 변환 세트. 없는 파일은 조용히 건너뛴다 — 팩트체크 생략 등으로
# 40_qa.md가 없을 수 있고, 전건 필수로 두면 정상 흐름이 실패한다.
REVISION_SET = ("20_draft.md", "40_prepared.md", "43_convert_input.md",
                "40_roundtrip.md", "40_qa.md")
HISTORY = "history"
DRAFTS = "drafts"
INDEX = "index.jsonl"
# final/ 인도본 접두어 — rNN_YYYYMMDD_. 접두어가 곧 판본이라 정렬만으로 최신이 드러난다.
VERSIONED = re.compile(r"^r(\d{2,})_(\d{8})_")
LABEL_BAD = re.compile(r"[^0-9A-Za-z가-힣._-]+")


def stamp(now=None):
    return (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M")


def _history(work_dir):
    return pathlib.Path(work_dir) / HISTORY


def read_index(work_dir):
    """history/index.jsonl을 읽어 리스트로 돌려준다(없으면 빈 리스트)."""
    path = _history(work_dir) / INDEX
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except ValueError:      # 손상된 줄은 건너뛴다 — 이력이 하나 깨져도 진행은 막지 않는다
                continue
    return rows


def append_index(work_dir, row):
    path = _history(work_dir) / INDEX
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def current_version(work_dir):
    """final/ 인도본에서 읽어낸 현재 판본 번호(없으면 0).

    index.jsonl이 아니라 **파일 이름**을 진실로 삼는다 — 이력 파일이 지워져도 인도본만
    있으면 판본이 복원되고, 사람이 파일을 직접 옮겼을 때도 어긋나지 않는다.
    """
    best = 0
    for p in sorted((pathlib.Path(work_dir) / "final").glob("*.hwpx")):
        m = VERSIONED.match(p.name)
        if m:
            best = max(best, int(m.group(1)))
    return best


def versioned_name(rev, title, now=None):
    """rNN_YYYYMMDD_{제목}.hwpx — 접두어를 앞에 두어 이름이 길어져도 판본이 먼저 읽힌다."""
    day = (now or datetime.datetime.now()).strftime("%Y%m%d")
    return f"r{rev:02d}_{day}_{title}"


def snapshot(work_dir, label, filename="20_draft.md", now=None):
    """현행 초안을 history/drafts/에 사유(label)와 함께 복사한다.

    복사이지 이동이 아니다 — 현행본은 제자리에 그대로 있어야 다음 단계가 읽는다.
    """
    work_dir = pathlib.Path(work_dir)
    src = work_dir / filename
    if not src.is_file():
        raise FileNotFoundError(f"{filename}이 없다: {src}")
    tag = LABEL_BAD.sub("-", label).strip("-") or "무제"
    at = stamp(now)
    stem, suffix = src.stem, src.suffix
    dst_dir = _history(work_dir) / DRAFTS
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{stem}.{at}.{tag}{suffix}"
    shutil.copy2(src, dst)
    row = {"kind": "draft", "at": at, "label": tag, "source": filename,
           "file": f"{DRAFTS}/{dst.name}",
           "fingerprint": content_fingerprint(src.read_text(encoding="utf-8"))}
    append_index(work_dir, row)
    return row


def revise(work_dir, now=None):
    """재변환 직전 정리 — 현행 변환 세트를 판본 폴더로 내리고 다음 판본 번호를 알린다.

    인도본 hwpx는 옮기지 않는다. 접두어가 없으면(최초 변환분·레거시) 이 시점에 붙여
    `final/`이 판본 순으로 읽히게 만든다.
    """
    work_dir = pathlib.Path(work_dir)
    final = work_dir / "final"
    hwpxs = sorted(final.glob("*.hwpx")) if final.is_dir() else []
    if not hwpxs:
        # 최초 변환 — 아카이브할 직전 판본이 없다
        return {"archived": None, "next_version": 1, "renamed": [],
                "skipped": "no_delivered_hwpx"}

    rev = current_version(work_dir) or 1
    draft = work_dir / "20_draft.md"
    fp = content_fingerprint(draft.read_text(encoding="utf-8")) if draft.is_file() else None
    # 변환 없이 다시 부르면 같은 판본을 또 내리지 않는다 — 판본 폴더가 분 단위로 늘고
    # index에 중복 줄이 쌓인다. 판본 번호와 초안 지문이 둘 다 같으면 이미 내린 것이다.
    for row in read_index(work_dir):
        if row.get("kind") == "revision" and row.get("rev") == rev and row.get("fingerprint") == fp:
            return {"archived": row.get("dir"), "next_version": rev + 1, "renamed": [],
                    "skipped": "already_archived"}
    at = stamp(now)
    dst = _history(work_dir) / f"r{rev:02d}_{at}"
    dst.mkdir(parents=True, exist_ok=True)

    copied = []
    for name in REVISION_SET:
        src = work_dir / name
        if src.is_file():
            shutil.copy2(src, dst / name)
            copied.append(name)

    # 이 판본에 딸렸던 초안 스냅샷을 함께 내린다 — 다음 판본의 스냅샷과 섞이면 안 된다
    wip = _history(work_dir) / DRAFTS
    moved = []
    if wip.is_dir():
        holder = dst / DRAFTS
        for p in sorted(wip.iterdir()):
            if p.is_file():
                holder.mkdir(parents=True, exist_ok=True)
                shutil.move(str(p), str(holder / p.name))
                moved.append(p.name)

    # 접두어 없는 인도본에 판본 접두어를 붙인다(있으면 그대로 둔다 — 멱등)
    renamed = []
    for p in hwpxs:
        if VERSIONED.match(p.name):
            continue
        target = p.with_name(versioned_name(rev, p.name, now))
        if target.exists():
            continue
        p.rename(target)
        renamed.append({"from": p.name, "to": target.name})

    row = {"kind": "revision", "rev": rev, "at": at, "dir": dst.name,
           "files": copied, "drafts": moved, "renamed": renamed,
           "hwpx": [q.name for q in sorted(final.glob("*.hwpx"))],
           "fingerprint": fp}
    append_index(work_dir, row)
    return {"archived": dst.name, "next_version": rev + 1, "renamed": renamed,
            "files": copied, "drafts": moved, "skipped": None}


# --- 기존 작업폴더 1회 정리 -------------------------------------------------
# 흩어진 판본 파일을 history/drafts/로 모으는 계획을 세운다. 기본은 계획 출력만이고
# --apply를 줘야 실제로 옮긴다 — 인도 완료 건의 파일 위치를 바꾸는 일이라 승인을 받는다.
LEGACY = re.compile(r"^(?P<stem>20_draft|10_outline)"
                    r"(?:_v(?P<v>\d+)|\.(?P<tag>[^/]+?))(?P<ext>\.md)$")


def migration_plan(work_dir):
    """이 작업폴더에서 옮겨야 할 판본 파일 목록(현행본은 건드리지 않는다)."""
    work_dir = pathlib.Path(work_dir)
    moves = []
    for p in sorted(work_dir.glob("*.md")):
        m = LEGACY.match(p.name)
        if not m:
            continue                      # 20_draft.md·10_outline.md 등 현행본
        stem, ext = m.group("stem"), m.group("ext")
        if m.group("v"):
            tag, at = f"v{int(m.group('v')):02d}", ""
        else:
            raw = m.group("tag")
            # `.20260907-교차검증전` 꼴이면 날짜와 사유를 갈라 새 표기로 옮긴다
            dm = re.match(r"^(\d{8})(?:-(.*))?$", raw)
            if dm:
                at, tag = dm.group(1) + "-0000", (dm.group(2) or "무제")
            else:
                at, tag = "", raw
        tag = LABEL_BAD.sub("-", tag).strip("-") or "무제"
        at = at or datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y%m%d-%H%M")
        moves.append({"from": p.name, "to": f"{HISTORY}/{DRAFTS}/{stem}.{at}.{tag}{ext}"})
    return moves


def migrate(work_dir, apply=False):
    work_dir = pathlib.Path(work_dir)
    moves = migration_plan(work_dir)
    if apply and moves:
        dst_dir = _history(work_dir) / DRAFTS
        dst_dir.mkdir(parents=True, exist_ok=True)
        for mv in moves:
            shutil.move(str(work_dir / mv["from"]), str(work_dir / mv["to"]))
        append_index(work_dir, {"kind": "migration", "at": stamp(), "moves": moves})
    return {"work_dir": str(work_dir), "moves": moves, "applied": bool(apply and moves)}


USAGE = ("usage: archive_revision.py snapshot <work_dir> --label <사유> [--file 20_draft.md]\n"
         "       archive_revision.py revise <work_dir>\n"
         "       archive_revision.py migrate <work_dir|reports_dir> [--apply]")


def main(argv=None):
    ap = argparse.ArgumentParser(description="작업폴더 이력 관리", usage=USAGE)
    ap.add_argument("mode", choices=("snapshot", "revise", "migrate"))
    ap.add_argument("path")
    ap.add_argument("--label", help="스냅샷 사유 (snapshot 필수)")
    ap.add_argument("--file", default="20_draft.md", help="스냅샷 대상 파일")
    ap.add_argument("--apply", action="store_true", help="migrate를 실제로 수행")
    args = ap.parse_args(argv)
    root = pathlib.Path(args.path)

    if args.mode == "snapshot":
        if not args.label:
            ap.error("snapshot에는 --label(사유)이 필요하다 — 이력은 사유가 있어야 읽힌다")
        out = snapshot(root, args.label, args.file)
    elif args.mode == "revise":
        out = revise(root)
    else:
        # 작업폴더 하나든 reports_dir 전체든 같은 명령으로 처리한다
        targets = [root] if (root / "20_draft.md").is_file() else sorted(
            p.parent for p in root.glob("*/*/20_draft.md"))
        plans = [migrate(t, args.apply) for t in targets]
        out = {"targets": len(plans),
               "moves": sum(len(p["moves"]) for p in plans),
               "applied": any(p["applied"] for p in plans),
               "detail": [p for p in plans if p["moves"]]}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
