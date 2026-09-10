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

# 판본 폴더 안에 놓이는 변환 산출물. 루트에는 두지 않는다 — 사람이 고치는 것은 20_draft
# 하나뿐인데 파생물이 옆에 나란히 있으면 초안을 고치는 순간 넷이 함께 낡는다(R087).
# 없는 파일은 조용히 건너뛴다(팩트체크 생략 시 40_qa.md 부재 등).
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


def begin(work_dir, now=None):
    """변환 시작 시 판본 폴더를 선할당한다 (R087 — R086 `revise`의 대체).

    종전에는 변환 세트가 작업폴더 루트에 태어난 뒤 **다음** 변환 때 이력으로 내려갔다.
    그 사이 초안만 고치면 루트의 파생물 4종(40_prepared·43_convert_input·40_roundtrip·
    40_qa)이 조용히 낡았다 — '26.9.10 전수 측정에서 10건 중 4건이 그 상태였다(최대 201조각·
    12일 차이). 파생물을 처음부터 판본 폴더 안에서 만들면 루트에 낡을 파일 자체가 없다.

    아직 변환되지 않은 초안 스냅샷은 이 판본에 딸린 것이므로 함께 내린다.
    """
    work_dir = pathlib.Path(work_dir)
    rev = current_version(work_dir) + 1
    at = stamp(now)
    dst = _history(work_dir) / f"r{rev:02d}_{at}"
    dst.mkdir(parents=True, exist_ok=True)

    wip = _history(work_dir) / DRAFTS
    moved = []
    if wip.is_dir():
        holder = dst / DRAFTS
        for q in sorted(wip.iterdir()):
            if q.is_file():
                holder.mkdir(parents=True, exist_ok=True)
                shutil.move(str(q), str(holder / q.name))
                moved.append(q.name)

    draft = work_dir / "20_draft.md"
    fp = content_fingerprint(draft.read_text(encoding="utf-8")) if draft.is_file() else None
    row = {"kind": "revision", "rev": rev, "at": at, "dir": dst.name,
           "drafts": moved, "fingerprint": fp}
    append_index(work_dir, row)
    day = (now or datetime.datetime.now()).strftime("%Y%m%d")
    return {"rev": rev, "dir": str(dst), "drafts": moved,
            "hwpx_prefix": f"r{rev:02d}_{day}_"}


def status(work_dir):
    """현행 초안이 마지막으로 변환된 판본과 같은가 (R085 freshness의 이력 기반 판정).

    루트에서 40_prepared가 사라졌으므로 대조 기준을 `history/index.jsonl`의 마지막 판본
    지문으로 옮긴다. 인도본이 현재 초안과 다른 판이면 여기서 드러난다.
    """
    work_dir = pathlib.Path(work_dir)
    draft = work_dir / "20_draft.md"
    if not draft.is_file():
        return {"state": "no_draft", "rev": None}
    fp = content_fingerprint(draft.read_text(encoding="utf-8"))
    revs = [r for r in read_index(work_dir) if r.get("kind") == "revision"]
    if not revs:
        return {"state": "never_exported", "rev": None, "fingerprint": fp}
    last = revs[-1]
    same = last.get("fingerprint") == fp
    return {"state": "current" if same else "draft_ahead",
            "rev": last.get("rev"), "at": last.get("at"), "dir": last.get("dir"),
            "detail": None if same else
                      "20_draft가 마지막 변환 이후 바뀌었다 — 재변환해야 인도본이 초안과 맞는다"}


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


DERIVED = ("40_prepared.md", "43_convert_input.md", "40_roundtrip.md", "40_qa.md")


def derived_plan(work_dir, now=None):
    """루트에 남은 파생물 4종을 판본 폴더로 내리는 계획 (R087 구조 전환).

    기존 건은 파생물이 루트에 태어났다. 판본 번호는 `final/` 인도본에서 읽고, 접두어가
    아직 없으면 r01로 본다 — 판본의 진실은 파일 이름이라는 규약(R086) 그대로다.
    """
    work_dir = pathlib.Path(work_dir)
    present = [n for n in DERIVED if (work_dir / n).is_file()]
    if not present:
        return None, []
    rev = current_version(work_dir) or 1
    holder = f"{HISTORY}/r{rev:02d}_{stamp(now)}"
    return holder, [{"from": n, "to": f"{holder}/{n}"} for n in present]


def final_prefix_plan(work_dir):
    """접두어 없는 인도본에 판본 번호를 붙이는 계획 — 시각 순으로 r01부터 매긴다.

    같은 문서의 구판만 대상이다. 서로 **다른 문서**가 한 폴더에 있으면 번호가 섞이므로
    폴더를 먼저 나눠야 한다('26.9.10 실측 3건 분리) — 이 함수는 그 판정을 하지 않는다.
    """
    final = pathlib.Path(work_dir) / "final"
    if not final.is_dir():
        return []
    plain = [q for q in final.glob("*.hwpx") if not VERSIONED.match(q.name)]
    if not plain:
        return []
    start = current_version(work_dir)
    plan = []
    for i, q in enumerate(sorted(plain, key=lambda x: x.stat().st_mtime), start + 1):
        day = datetime.datetime.fromtimestamp(q.stat().st_mtime).strftime("%Y%m%d")
        plan.append({"from": f"final/{q.name}", "to": f"final/r{i:02d}_{day}_{q.name}"})
    return plan


def migrate(work_dir, apply=False):
    work_dir = pathlib.Path(work_dir)
    moves = migration_plan(work_dir)
    holder, derived = derived_plan(work_dir)
    finals = final_prefix_plan(work_dir)
    if apply and finals:
        for mv in finals:
            (work_dir / mv["from"]).rename(work_dir / mv["to"])
    if apply and (moves or derived):
        if moves:
            (_history(work_dir) / DRAFTS).mkdir(parents=True, exist_ok=True)
            for mv in moves:
                shutil.move(str(work_dir / mv["from"]), str(work_dir / mv["to"]))
        if derived:
            (work_dir / holder).mkdir(parents=True, exist_ok=True)
            for mv in derived:
                shutil.move(str(work_dir / mv["from"]), str(work_dir / mv["to"]))
            draft = work_dir / "20_draft.md"
            append_index(work_dir, {
                "kind": "revision", "rev": current_version(work_dir) or 1,
                "at": stamp(), "dir": pathlib.Path(holder).name,
                "files": [m["from"] for m in derived], "drafts": [],
                "fingerprint": (content_fingerprint(draft.read_text(encoding="utf-8"))
                                if draft.is_file() else None),
                "note": "구조 전환 이관(R087)"})
        append_index(work_dir, {"kind": "migration", "at": stamp(),
                                "moves": moves + derived})
    return {"work_dir": str(work_dir), "moves": moves + derived + finals,
            "applied": bool(apply and (moves or derived or finals))}


# --- research 평탄화 -------------------------------------------------------
# `research/fetched/{슬러그}/{파일}.md` 3단계 구조는 조사 단위를 폴더로 표현했다. 그 결과
# 한 건에 폴더 69개·매니페스트 63개가 흩어져 무엇이 있는지 목록으로 보이지 않았다
# ('26.9.10 실측). 조사 단위는 **파일명**으로 충분하다 — 시각 접두어가 순서를, 슬러그가
# 내용을 말한다. 매니페스트는 research/ 하나로 합친다.
FM_DATE = re.compile(r'^fetched_at:\s*"?(\d{4})-(\d{2})-(\d{2})', re.M)
MODE_TAG = {"provided": "제공", "vault": "vault"}


def _research_stamp(path):
    """프론트매터 fetched_at을 우선 쓰고 없으면 파일 시각 — 순서가 이름으로 읽혀야 한다."""
    try:
        m = FM_DATE.search(path.read_text(encoding="utf-8")[:2000])
        if m:
            return f"{m.group(1)}{m.group(2)}{m.group(3)}-0000"
    except (OSError, UnicodeDecodeError):
        pass
    return datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y%m%d-%H%M")


def research_plan(work_dir):
    """research/ 하위 폴더를 없애고 `{시각}_{조사내용}` 평면 이름으로 옮기는 계획."""
    root = pathlib.Path(work_dir) / "research"
    if not root.is_dir():
        return []
    moves = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name == ".DS_Store":
            continue
        rel = p.relative_to(root)
        if len(rel.parts) == 1:
            continue                                  # 이미 평면
        mode = rel.parts[0]
        # `_manifest.jsonl`은 한 곳으로 합치므로 개별 이동 대상이 아니다
        if p.name == "_manifest.jsonl":
            moves.append({"from": str(rel), "to": "_manifest.jsonl", "merge": True})
            continue
        parts = [x for x in rel.parts[1:-1] if x != "images"]
        slug = "-".join(parts + [p.stem]) if parts else p.stem
        tag = MODE_TAG.get(mode)
        if tag:
            slug = f"{tag}-{slug}"
        slug = LABEL_BAD.sub("-", slug).strip("-") or "무제"
        moves.append({"from": str(rel), "to": f"{_research_stamp(p)}_{slug}{p.suffix}"})
    return moves


def flatten_research(work_dir, apply=False):
    root = pathlib.Path(work_dir) / "research"
    moves = research_plan(work_dir)
    if apply and moves:
        # 본문의 `](images/x.png)` 상대 참조는 평탄화로 깨진다 — 옮기면서 새 이름으로 고친다.
        # 참조를 안 고치면 도식이 사라진 채 남고, 그건 파일 목록만 봐서는 드러나지 않는다.
        rename = {mv["from"]: mv["to"] for mv in moves if not mv.get("merge")}
        merged = []
        for mv in moves:
            src = root / mv["from"]
            if mv.get("merge"):
                merged.extend(src.read_text(encoding="utf-8").splitlines())
                src.unlink()
                continue
            dst = root / mv["to"]
            if dst.exists():
                dst = root / f"{dst.stem}-{len(moves)}{dst.suffix}"
                mv["to"] = dst.name
            if src.suffix == ".md":
                text = src.read_text(encoding="utf-8")
                base = pathlib.PurePosixPath(mv["from"]).parent
                for old_rel, new_name in rename.items():
                    try:
                        ref = pathlib.PurePosixPath(old_rel).relative_to(base).as_posix()
                    except ValueError:
                        continue
                    if "/" in ref and ref in text:      # `images/x.png` 형태만 대상
                        text = text.replace(f"]({ref})", f"]({new_name})")
                src.write_text(text, encoding="utf-8")
            shutil.move(str(src), str(dst))
        if merged:
            with (root / "_manifest.jsonl").open("a", encoding="utf-8") as f:
                f.write("\n".join(merged) + "\n")
        # 빈 하위 폴더는 지운다 — 구조가 남아 있으면 다음 조사가 또 그리로 들어간다.
        # .DS_Store가 남아 rmdir이 실패하는 일이 잦아 먼저 치운다(내용물이 아니다).
        for junk in root.rglob(".DS_Store"):
            junk.unlink(missing_ok=True)
        for d in sorted((q for q in root.rglob("*") if q.is_dir()), reverse=True):
            try:
                d.rmdir()
            except OSError:
                pass
    return {"work_dir": str(work_dir), "moves": moves, "applied": bool(apply and moves)}


USAGE = ("usage: archive_revision.py snapshot <work_dir> --label <사유> [--file 20_draft.md]\n"
         "       archive_revision.py begin <work_dir>          # 변환 시작 — 판본 폴더 선할당\n"
         "       archive_revision.py status <work_dir>         # 초안↔마지막 인도본 대응\n"
         "       archive_revision.py migrate <work_dir|reports_dir> [--apply]\n"
         "       archive_revision.py flatten <work_dir|reports_dir> [--apply]  # research/ 평탄화")


def main(argv=None):
    ap = argparse.ArgumentParser(description="작업폴더 이력 관리", usage=USAGE)
    ap.add_argument("mode", choices=("snapshot", "begin", "status", "migrate", "flatten"))
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
    elif args.mode == "begin":
        out = begin(root)
    elif args.mode == "status":
        out = status(root)
    else:
        # 작업폴더 하나든 reports_dir 전체든 같은 명령으로 처리한다
        targets = [root] if (root / "20_draft.md").is_file() else sorted(
            p.parent for p in root.glob("*/*/20_draft.md"))
        run = migrate if args.mode == "migrate" else flatten_research
        plans = [run(t, args.apply) for t in targets]
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
