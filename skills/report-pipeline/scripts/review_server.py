#!/usr/bin/env python3
"""라이브 리뷰 서버 — 보고서 목록(허브)과 건마다 모든 md 문서를 창 하나에서 리뷰한다. stdlib-only.

허브('26.9.25 사용자 선택 A안 + 모든 md 리뷰): http://127.0.0.1:3333/ 이 보고서 목록이고, 건을 열면 문서
(초안·아웃라인·분석·맥락·research·부속 문서)를 골라 본다. 초안은 hwpx 양식 보기(render_review_html), 나머지는
문서 보기(md_view). 코멘트는 serve로 등록한 건만 받고(다른 건은 보기 전용), 맥락(00)은 코멘트만·research는
메모 코멘트만 받는다. `serve`를 두 번째로 부르면 떠 있는 허브에 그 건이 합류한다(서버를 새로 띄우지 않는다).

배경('26.9.24 사용자 요청): plannotator는 피드백을 보내면 세션 서버가 끝나(공식 문서 Session
lifetime — Send Feedback·Approve·Close 모두) 화면이 잠기고, 수정본은 새 창으로 다시 띄워야 했다.
실시간 반영 모드는 없다. 이 서버는 127.0.0.1에서만 돌며 요청마다 `20_draft.md`·`figures/`를 다시
그려(render_review_html) 보여 주고, 브라우저는 변경을 감지하면 스크롤을 유지한 채 새로 그리며
바뀐 항목을 표시한다. 코멘트는 창을 닫지 않고 몇 번이든 보낸다.

    serve   <work_dir> [--port N] [--no-open]   서버 기동(백그라운드 실행, 기본 포트 3333) — 브라우저를 연다
    wait    <work_dir> | --all [--timeout 초]   새 코멘트·결정이 올 때까지 대기 → JSON 출력 후 종료
                                                (--all: 허브에서 리뷰 중인 건 전부 — 항목마다 case·work_dir)
    resolve <work_dir> ID…                      코멘트를 '반영됨'으로 표시하고 열린 화면을 새로 그린다
    refresh <work_dir>                          열린 화면을 지금 새로 그린다(수정 끝 신호)
    stop    <work_dir>                          이 건 리뷰 닫기(처리 세션 임대도 푼다)
    lock    acquire|release|status [--why 사유] 규칙 승격·하네스 코드 수정·변환은 한 번에 한 건만
    sum                                         하네스 지문 — 서브에이전트에 코멘트 처리를 넘긴 전후 대조

여러 보고서를 함께 열 때의 안전장치('26.9.25 사용자 선택): 건마다 **처리 세션 임대**
(`history/drafts/.review_owner.json` — 다른 세션이 잡은 건은 wait가 exit 3으로 거부해 같은 코멘트를 두 번
고치지 않는다) · 화면의 **CLI 상태 표시**(대기 중·처리 중·없음 — 처리 주체 없는 코멘트를 숨기지 않는다) ·
**인도된 건은 개정으로만 연다**(열 때 초안 스냅샷, 다음 인도가 새 판) · 규칙·코드 수정은 **하네스 잠금**.

화면은 **CLI가 '반영 완료'를 알릴 때만**(refresh·resolve) 바뀐다('26.9.24 사용자 선택 — 1초 주기
갱신 대신). 서버가 초안을 다시 그려 마지막으로 보낸 화면과 항목 단위로 비교하고, 바뀐 항목의 조각만
열어 둔 연결(SSE)로 보낸다. 브라우저는 주기 요청을 하지 않고, 받은 항목만 바꿔 끼운다 — 스크롤·
작성 중인 코멘트 카드·쓰던 글은 그대로다. 렌더러 코드는 파일이 바뀌면 다음 신호 때 다시 읽고(재기동
불필요), 서버를 같은 포트로 다시 띄우면 열린 탭이 스스로 다시 붙어 기준본을 받는다.

`wait`가 끝나면 Claude Code가 백그라운드 완료 알림을 받는다 — 사용자가 "다 봤다"고 말할 필요가 없다.
기록은 `history/drafts/26_review.{시작시각}.jsonl`(1줄 1건: feedback·decision·status)에 쌓고
작업폴더 루트에는 쓰지 않는다(R087). 외부 URL·외부 전송이 없다.
"""
import os
import sys
import json
import time
import signal
import socket
import getpass
import re
import queue
import hashlib
import argparse
import contextlib
import importlib.util
import datetime
import pathlib
import threading
import webbrowser
import urllib.request
import urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from harness_config import history_paths, load_config           # noqa: E402  (경로 규약 단독 출처)
import archive_revision                                           # noqa: E402  (인도 건을 개정으로 열 때 초안 스냅샷)
import postprocess_hwpx                                           # noqa: E402  (핫 리로드 순서의 첫째)
import render_diagram                                             # noqa: E402
import diagram_table                                              # noqa: E402  (표 도식 — 리뷰와 변환 공용)
import render_review_html                                         # noqa: E402  (리뷰 화면 단독 출처 — 초안 양식 보기)
import md_view                                                    # noqa: E402  (문서 보기 — 초안 밖 md)
import lint_md_profile                                            # noqa: E402  (직접 수정 뒤 표기 검사)
import audit_style                                                # noqa: E402  (직접 수정 뒤 문체 감사)

STATE = ".review_server.json"
DEFAULT_PORT = 3333          # 고정 주소 http://127.0.0.1:3333/ — 즐겨찾기로 다시 열 수 있게('26.9.24 사용자 지정)
POLL_SEC = 1.0
OWNER = ".review_owner.json"   # 건별 처리 세션 임대(history/drafts/)
HARNESS_LOCK = ".harness_lock.json"   # 규칙·하네스 코드 수정·변환 잠금(state_dir/)
LEASE_SEC = 1800             # 임대 유지 — 마지막 신호 뒤 이 시간이 지나고 세션 프로세스도 없으면 빈 것으로 본다
BEAT_SEC = 20                # wait가 기다리는 동안 남기는 신호 간격
WAITING_FRESH_SEC = 60       # 이 안에 신호가 있으면 '대기 중'
CLI_WATCH_SEC = 3
GRACE_SEC = 5                # 보낸 코멘트는 이 시간 뒤에 CLI로 넘긴다 — 그 사이 화면에서 되돌릴 수 있다('26.9.25)            # 서버가 건별 CLI 상태를 다시 보는 간격(바뀔 때만 화면에 보낸다)
STATUS_LABEL = {"sent": "보냄", "delivered": "확인 중", "resolved": "반영됨", "withdrawn": "취소됨"}


# ---------------------------------------------------------------------------
# 기록(jsonl) — 서버·wait·resolve가 같은 파일을 1줄씩 append 한다
# ---------------------------------------------------------------------------

def _drafts(work_dir):
    d = history_paths(pathlib.Path(work_dir).resolve())["drafts"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def _state(work_dir):
    p = _drafts(work_dir) / STATE
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def _log_path(work_dir):
    st = _state(work_dir)
    if st and st.get("log"):
        return pathlib.Path(st["log"])
    logs = sorted(_drafts(work_dir).glob("26_review.*.jsonl"))
    return logs[-1] if logs else None


_LOCK = threading.Lock()


def append_event(log, event):
    event = dict(event, at=datetime.datetime.now().isoformat(timespec="seconds"))
    with _LOCK, open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read_events(log):
    if not log or not pathlib.Path(log).is_file():
        return []
    out = []
    for line in pathlib.Path(log).read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def items(log):
    """코멘트·결정 목록과 현재 상태 — status 이벤트가 나중에 덮어쓴다."""
    evs = read_events(log)
    status = {}
    for e in evs:
        if e.get("type") == "status":
            status[e["id"]] = e["status"]
    return [dict(e, status=status.get(e["id"], "sent")) for e in evs if e.get("type") in ("feedback", "decision", "edit")]


@contextlib.contextmanager
def _xlock(path, timeout=5.0):
    """프로세스 사이 잠금 — 잠금 파일을 배타 생성(O_EXCL)한다. threading.Lock은 한 프로세스 안에서만 막으므로
    wait(별도 프로세스) 둘이 같은 '보냄'을 함께 읽고 둘 다 넘기는 일을 막지 못했다. 오래된 잠금(30초)은 치운다."""
    lock, end = pathlib.Path(str(path) + ".lock"), time.time() + timeout
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 30:
                    lock.unlink(missing_ok=True)
                    continue
            except OSError:
                continue
            if time.time() > end:
                raise OSError(f"잠금을 얻지 못했다: {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def _age(x):
    try:
        return (datetime.datetime.now() - datetime.datetime.fromisoformat(x.get("at", ""))).total_seconds()
    except ValueError:
        return float("inf")


def collect_pending(log, grace=0):
    """아직 Claude에 넘기지 않은 코멘트·결정 → 'delivered'로 표시하고 돌려준다(wait의 본체).
    읽기와 표시를 프로세스 사이 잠금으로 묶는다 — 같은 코멘트가 두 번 넘어가지 않는다.
    grace초가 안 된 코멘트는 남겨 둔다 — CLI가 1초 안에 가져가 '보내기 취소'가 거의 통하지 않았다."""
    if not log:
        return []
    with _xlock(log):
        pending = [x for x in items(log) if x["status"] == "sent" and (x.get("type") != "feedback" or _age(x) >= grace)]
        for x in pending:
            append_event(log, {"type": "status", "id": x["id"], "status": "delivered"})
    return pending


# ---------------------------------------------------------------------------
# 처리 세션 임대 — 한 건은 한 세션만 처리한다('26.9.25 여러 보고서 동시 정리의 안전장치)
# ---------------------------------------------------------------------------

def session_owner():
    """처리 세션 — Claude Code 세션 ID와 그 프로세스(없으면 사용자·호스트·부모 프로세스)."""
    pid = os.environ.get("CLAUDE_PID") or str(os.getppid())
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID") or f"{getpass.getuser()}@{socket.gethostname()}:{pid}"
    return {"owner": sid, "pid": int(pid) if pid.isdigit() else None}


def _alive(pid):
    """프로세스가 살아 있나 — 모르면 None. Windows의 os.kill(pid, 0)은 프로세스를 끝내므로 쓰지 않는다."""
    if not pid or os.name == "nt":
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def lease_state(path, now=None):
    """임대 상태 — waiting(wait가 기다리는 중)·working(세션이 처리 중)·none(처리할 세션 없음)."""
    try:
        cur = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "none"}
    age = (now or time.time()) - float(cur.get("seen", 0))
    if _alive(cur.get("pid")) is False or age > LEASE_SEC:
        return {"state": "none"}
    st = "waiting" if cur.get("waiting") and age <= WAITING_FRESH_SEC else "working"
    return dict(cur, state=st)


def lease_claim(path, me, waiting=False, **extra):
    """임대를 잡거나 갱신한다 → (True, None) 또는 다른 세션이 잡고 있으면 (False, 그 임대)."""
    path = pathlib.Path(path)
    with _xlock(path):
        cur = lease_state(path)
        if cur["state"] != "none" and cur.get("owner") != me["owner"]:
            return False, cur
        now = time.time()
        row = dict(extra, owner=me["owner"], pid=me["pid"], waiting=bool(waiting), seen=now,
                   since=cur.get("since", now) if cur.get("owner") == me["owner"] else now)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(row, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    return True, None


def lease_release(path, me=None):
    """임대를 푼다 — me를 주면 내 임대일 때만."""
    path = pathlib.Path(path)
    with _xlock(path):
        cur = lease_state(path)
        if me is None or cur.get("owner") in (None, me["owner"]):
            path.unlink(missing_ok=True)
            return True
    return False


def _owner_path(work_dir):
    return _drafts(work_dir) / OWNER


# 렌더러 모듈 — 파일이 바뀌면 이 순서로 다시 읽는다(뒤 모듈이 앞 모듈의 상수를 from-import 하므로)
RENDER_MODULES = (lint_md_profile, audit_style, postprocess_hwpx, render_diagram, diagram_table, render_review_html, md_view)
_RENDER_LOCK = threading.RLock()
_MOD_SIG = {}
LINE_ATTR = re.compile(r' id="L\d+" data-line="\d+"')
KEEPALIVE_SEC = 15


def _stat(p):
    p = pathlib.Path(p)
    try:
        st = p.stat()
        return (str(p), st.st_mtime_ns, st.st_size)
    except OSError:
        return (str(p), 0, 0)


def reload_renderers():
    """렌더러 코드가 바뀌었으면 다시 읽는다 — 서버를 다시 띄우지 않아도 고친 양식이 화면에 나온다."""
    sig = tuple(_stat(m.__file__) for m in RENDER_MODULES)
    if _MOD_SIG.get("sig") == sig:
        return False
    if "sig" in _MOD_SIG:
        for m in RENDER_MODULES:                 # 원래 파일에서 다시 실행 — sys.path 순서로 다른 사본을 잡지 않게
            importlib.util.spec_from_file_location(m.__name__, m.__file__).loader.exec_module(m)
    _MOD_SIG["sig"] = sig
    return True


DRAFT = "20_draft.md"
COMMENT_ONLY = {"00_context.md"}           # 파이프라인이 단계마다 덧붙이는 결정 기록 — 직접 수정 대신 코멘트(정정 요청)
DOC_LABELS = {"00_context.md": "맥락", "05_analysis.md": "분석", "10_outline.md": "아웃라인", DRAFT: "초안"}


def list_docs(work_dir):
    """건의 리뷰 대상 문서 — 루트 md(파이프라인 순서대로 파일명 정렬) + research/*.md. 숨김·history는 뺀다."""
    wd = pathlib.Path(work_dir)
    root = sorted(p.name for p in wd.glob("*.md") if not p.name.startswith("."))
    res = sorted("research/" + p.name for p in (wd / "research").glob("*.md")) if (wd / "research").is_dir() else []
    return root + res


def _front_title(path):
    """research 파일 프론트매터의 title(앞 4천 자 안에서만 찾는다). 없으면 빈 문자열."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(4096)
    except OSError:
        return ""
    m = re.match(r"---\n(.*?)\n---", head, re.S)
    t = re.search(r"^title:[ \t]*(.+)$", m.group(1), re.M) if m else None
    t = t.group(1).strip() if t else ""
    return t[1:-1] if len(t) > 1 and t[0] == t[-1] and t[0] in "'\"" else t


def _split_title(t):
    """'주제목 (기관, 시점 — 부연) 설명' → ('주제목', '기관, 시점'). 괄호가 없으면 보조 줄은 비운다."""
    m = re.match(r"(.+?)\s\(([^()]*)\)", t)
    return (m.group(1).strip(), m.group(2).split(" — ")[0].strip()) if m else (t, "")


def doc_meta(work_dir, doc):
    """탐색 서랍·문서 보기의 이름 — num(파일 번호)·label(주 이름)·sub(보조 줄)·title(전체 이름).
    파일명(밑줄·시각 접두어)을 그대로 보이면 읽히지 않는다 — research는 프론트매터 title을 쓴다."""
    stem = doc.rsplit("/", 1)[-1][:-3]
    if doc in DOC_LABELS:
        return {"num": doc[:2], "label": DOC_LABELS[doc], "sub": "", "title": f"{doc[:2]} {DOC_LABELS[doc]}"}
    if doc.startswith("research/"):
        full = _front_title(pathlib.Path(work_dir) / doc)
        if full:
            label, sub = _split_title(full)
        else:
            name = re.sub(r"^\d{8}-\d{4}_", "", stem)
            given = name.startswith("제공-")
            label, sub = (name[3:] if given else name).replace("_", " "), "제공 자료" if given else ""
            full = label
        return {"num": "", "label": label, "sub": sub, "title": full}
    m = re.match(r"(\d{2})_(.+)", stem)
    num, label = (m.group(1), m.group(2).replace("_", " ")) if m else ("", stem)
    return {"num": num, "label": label, "sub": "", "title": f"{num} {label}".strip()}


def case_title(name):
    """작업폴더 이름 '1127_AI성과측정-요약본-부서장' → ('AI성과측정 요약본 부서장', '11:27')."""
    m = re.match(r"(\d{2})(\d{2})_(.+)", name)
    if not m:
        return name.replace("_", " "), ""
    return re.sub(r"[-_]+", " ", m.group(3)).strip(), f"{m.group(1)}:{m.group(2)}"


def doc_group(doc):
    """탐색 서랍의 무리 — 파이프라인 단계 문서·부속 문서·research."""
    if doc.startswith("research/"):
        return "research"
    return "stage" if doc in DOC_LABELS else "extra"


def doc_mode(doc):
    """초안은 양식 보기(hwpx 모양·쪽 나눔), 나머지는 문서 보기."""
    return "form" if doc == DRAFT else "doc"


def is_record(work_dir, doc):
    """초안이 생긴 뒤의 아웃라인·분석 — 앞 게이트의 기록(archive_revision.RECORDS). 직접 고치지 않는다."""
    return doc in archive_revision.RECORDS and (pathlib.Path(work_dir) / DRAFT).is_file()


def doc_perm(doc, active, record=False):
    """코멘트는 리뷰가 열린 건(active)만. 직접 수정은 결정 기록(00)·research(원문 발췌)·앞 게이트 기록을 뺀 문서만."""
    edit = active and not record and doc not in COMMENT_ONLY and not doc.startswith("research/")
    return {"comment": bool(active), "edit": bool(edit), "approve": bool(active and doc == DRAFT)}


def _doc_note(doc, active, drift=None):
    if not active:
        return "보기 전용 — 리뷰가 열린 건(serve로 등록)만 코멘트를 받습니다."
    if drift is not None:
        n = drift.get("n", 0)
        return ("앞 게이트의 기록 — 초안이 생긴 뒤에는 20_draft.md가 기준입니다. 직접 고치지 않고, 코멘트는 초안에 반영합니다."
                + (f" 초안과 어긋남 {n}곳 — 게이트② 승인 때 '반영 결과'가 이 문서 끝에 덧붙습니다." if n else ""))
    if doc in COMMENT_ONLY:
        return "결정 기록 — 직접 고치지 않고 코멘트로 정정을 요청하면 CLI가 새 줄로 덧붙입니다."
    if doc.startswith("research/"):
        return "research 원문 발췌 — 고칠 수 없습니다. 코멘트는 판단 메모(신뢰·제외 등)로 전달됩니다."
    return ""


def snapshot(work_dir, doc=DRAFT, active=True):
    """문서의 화면 조각과 그 버전(조각 전체의 지문)."""
    wd = pathlib.Path(work_dir)
    text = (wd / doc).read_text(encoding="utf-8")
    if doc_mode(doc) == "form":
        return snapshot_text(text, wd)
    with _RENDER_LOCK:
        reload_renderers()
        drift = archive_revision.drift(wd).get(doc) if is_record(wd, doc) else None
        parts = md_view.render_parts(text, doc_meta(wd, doc)["title"], _doc_note(doc, active, drift))
    return parts, _fingerprint(parts)


def snapshot_text(text, work_dir=None):
    with _RENDER_LOCK:
        reload_renderers()
        parts = render_review_html.render_parts(text, work_dir)
    return parts, _fingerprint(parts)


def _fingerprint(parts):
    h = hashlib.sha256(parts["css"].encode("utf-8"))
    for pg in parts["pages"]:
        for x in pg:
            h.update(x["html"].encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def diff_parts(old, new, page_html=None):
    """바뀐 항목만 — 쪽 모양(주소 순서)이 같으면 항목 단위, 다르면 그 쪽 통째, 쪽 수가 다르면 전부.

    줄 번호만 밀린 항목은 다시 그리지 않고 번호(`lines`)만 고친다 — 위에 한 줄을 넣어도 아래 항목이
    전부 바뀐 것으로 번쩍이지 않게. page_html은 보기 종류별 쪽 틀(양식 보기 기본)."""
    page_html = page_html or render_review_html.page_html
    out = {"changed": []}
    if old["css"] != new["css"]:
        out["css"] = new["css"]
    if old["title"] != new["title"]:
        out["title"] = new["title"]
    def keyed(pages):                         # 같은 주소가 둘 이상일 수 있다(붙임 배너와 '끝.') — 순번을 붙여 구분
        seen, out_ = {}, {}
        for pg in pages:
            for x in pg:
                if x["addr"]:
                    n = seen[x["addr"]] = seen.get(x["addr"], 0) + 1
                    out_[(x["addr"], n)] = LINE_ATTR.sub("", x["html"])
        return out_
    before, after = keyed(old["pages"]), keyed(new["pages"])
    out["changed"] = list(dict.fromkeys(a for (a, n), h in after.items() if before.get((a, n)) != h))
    if len(old["pages"]) != len(new["pages"]):
        out["all"] = [page_html(pg) for pg in new["pages"]]
        return out
    pages, blocks, lines = {}, [], []
    for pi, (op, np) in enumerate(zip(old["pages"], new["pages"])):
        if [x["addr"] for x in op] != [x["addr"] for x in np]:
            pages[pi] = page_html(np)
            continue
        for bi, (ox, nx) in enumerate(zip(op, np)):
            if LINE_ATTR.sub("", ox["html"]) != LINE_ATTR.sub("", nx["html"]):
                blocks.append({"p": pi, "i": bi, "html": nx["html"]})
            elif ox["line"] != nx["line"]:
                lines.append({"p": pi, "i": bi, "line": nx["line"]})
    out.update({k: v for k, v in (("pages", pages), ("blocks", blocks), ("lines", lines)) if v})
    return out


def ui_version():
    """패널 코드(overlay.html) 지문 — 바뀌면 브라우저가 패널까지 새로 읽는다."""
    return hashlib.sha256(OVERLAY_FILE.read_bytes()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# 브라우저 쪽 — 리뷰 HTML에 덧붙이는 라이브 패널(정적 파일 25_review.html에는 넣지 않는다)
# ---------------------------------------------------------------------------

OVERLAY_FILE = pathlib.Path(__file__).resolve().parent.parent / "assets" / "review" / "overlay.html"
KINDS = ("수정", "삭제", "질문", "좋음")            # plannotator의 주석 유형(댓글·삭제·빠른 라벨·Looks good) 대응
FACTCHECK = ("경량", "전수", "생략")               # 게이트② 선택지 1의 팩트체크 값
SCOPES = ("doc", "rule")                          # 적용 범위 — 이 보고서만(기본) · 앞으로도(규칙 후보, lessons 기록)


def overlay():
    """패널 UI(assets/review/overlay.html) — 요청마다 읽으므로 화면을 고쳐도 서버를 다시 띄울 필요가 없다."""
    return OVERLAY_FILE.read_text(encoding="utf-8")


class Live:
    """한 문서의 화면 기준본과 열린 탭 연결 — 화면은 CLI 신호(refresh·resolve) 때만 바뀐다('26.9.24 사용자 선택).

    기준본은 마지막으로 보낸 화면이다. 새로 연 탭도 기준본을 보여 주므로, Claude가 문서를 고치는 도중의
    반쯤 고친 상태는 신호가 오기 전까지 어디에도 나타나지 않는다."""

    def __init__(self, work_dir, doc=DRAFT, case=None):
        self.wd = pathlib.Path(work_dir)
        self.doc = doc
        self.case = case
        self.lock = threading.Lock()
        self.subs = []
        self.parts = self.version = None
        self.boot = case.boot if case else f"{time.time_ns():x}"   # 서버를 다시 띄우면 바뀐다 — 열린 탭이 기준본을 다시 받는다
        self.stop = case.stop if case else threading.Event()

    def _active(self):
        return self.case.active if self.case else True

    def _write_static(self, parts):
        # 사본은 리뷰를 연 건만 — 보기 전용으로 열기만 해도 인도 끝난 건 폴더에 history/drafts와 사본이 생겼다
        # ('26.9.25 실측 4건). HTML은 파이프라인 산출물이 아니라 게이트①·②의 보기 화면이다.
        if doc_mode(self.doc) == "form" and self._active():
            (_drafts(self.wd) / "25_review.html").write_text(render_review_html.document(parts), encoding="utf-8")

    def _snap(self):
        return snapshot(self.wd, self.doc, self._active())

    def current(self):
        with self.lock:
            if self.parts is None:
                self.parts, self.version = self._snap()
                self._write_static(self.parts)
            return self.parts, self.version

    def page(self):
        parts, ver = self.current()
        drift = archive_revision.drift(self.wd)
        base = self.case.prefix if self.case else ""
        rv = {"ver": ver, "boot": self.boot, "base": base, "doc": self.doc, "mode": doc_mode(self.doc), "grace": GRACE_SEC,
              "perm": doc_perm(self.doc, self._active(), is_record(self.wd, self.doc)),
              "case": dict(zip(("title", "time"), case_title(self.wd.name)), date=self.wd.parent.name,
                           name=self.wd.name, active=self._active(), stage=_stage(self.wd)),
              "docs": [dict(doc_meta(self.wd, d), doc=d, group=doc_group(d),
                            perm=doc_perm(d, self._active(), is_record(self.wd, d)),
                            record=is_record(self.wd, d), drift=drift.get(d, {}).get("n", 0))
                       for d in list_docs(self.wd)]}
        mod = render_review_html if doc_mode(self.doc) == "form" else md_view
        doc_html = mod.document(parts)
        return doc_html.replace("</body>", f"<script>window.__RV={json.dumps(rv, ensure_ascii=False)};</script>"
                                + overlay() + "</body>", 1)

    def refresh(self):
        """문서를 다시 그려 기준본과 비교하고, 바뀐 항목만 열린 탭에 보낸다."""
        new, ver = self._snap()
        with self.lock:
            old, old_ver = self.parts, self.version
            self.parts, self.version = new, ver
        self._write_static(new)
        if old is None or ver == old_ver:
            return {"changed": []}
        page = render_review_html.page_html if doc_mode(self.doc) == "form" else md_view.page_html
        patch = dict(diff_parts(old, new, page), **{"from": old_ver, "to": ver})
        self.send("patch", patch)
        return patch

    def send(self, event, data):
        msg = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        with self.lock:
            subs = list(self.subs)
        for q in subs:
            q.put(msg)

    def stream(self, wfile, hello):
        """이벤트 스트림(SSE) — 연결 하나를 열어 두고 보낼 것이 있을 때만 쓴다(주기 요청 없음)."""
        q = queue.Queue()
        with self.lock:
            self.subs.append(q)
        try:
            wfile.write(f"retry: 1000\nevent: hello\ndata: {json.dumps(hello, ensure_ascii=False)}\n\n".encode("utf-8"))
            wfile.flush()
            while not self.stop.is_set():
                try:
                    msg = q.get(timeout=KEEPALIVE_SEC)
                except queue.Empty:
                    msg = ": 연결 유지\n\n"
                wfile.write(msg.encode("utf-8"))
                wfile.flush()
        except OSError:
            pass
        finally:
            with self.lock:
                self.subs.remove(q)


def continue_log(work_dir):
    """승인 전 리뷰 기록은 이어 쓴다 — 서버를 다시 띄울 때마다 새 기록을 열면 패널 이력이 비고, 앞선 코멘트를
    `resolve`할 수 없었다('26.9.24 실측: 재기동 뒤 f4 반영 표시 실패). 마지막 기록에 승인이 있으면 새 회차로 연다."""
    for log in sorted(_drafts(work_dir).glob("26_review.*.jsonl"), reverse=True):
        evs = read_events(log)
        if not evs:
            continue                              # 기록 없이 끝난 회차(재기동만 한 것)는 건너뛴다
        if any(e.get("type") == "decision" and e.get("decision") == "approved" for e in evs):
            return None
        return log
    return None


# ---------------------------------------------------------------------------
# 허브 — 3333 하나에 여러 보고서(건)·건마다 여러 문서('26.9.25 사용자 선택 A안 + 모든 md 리뷰)
# ---------------------------------------------------------------------------
# 주소: /  → 보고서 목록 · /r/{날짜}/{폴더}/d/{문서} → 문서 화면 · /r/{날짜}/{폴더}/api/… → 그 건의 API(문서는 doc 인자).
# 코멘트는 serve로 등록한(리뷰가 열린) 건만 받는다 — 목록에서 연 다른 건은 보기 전용. 기록은 건마다 따로
# (history/drafts/26_review.*.jsonl), 코멘트에는 doc이 붙는다.

class Case:
    def __init__(self, work_dir, active, boot, stop_event):
        self.wd = pathlib.Path(work_dir).resolve()
        self.key = f"{self.wd.parent.name}/{self.wd.name}"
        self.prefix = "/r/" + urllib.parse.quote(self.wd.parent.name) + "/" + urllib.parse.quote(self.wd.name)
        self.active = False
        self.log = None
        self.seq = {"feedback": 0, "decision": 0, "edit": 0}
        self.lives = {}
        self.snapped = set()
        self.boot = boot
        self.stop = stop_event
        self.lock = threading.Lock()
        if active:
            self.activate()

    def activate(self):
        if self.active:
            return
        log = continue_log(self.wd) or _drafts(self.wd) / f"26_review.{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"
        evs = read_events(log)
        self.seq = {k: sum(1 for e in evs if e.get("type") == k) for k in ("feedback", "decision", "edit")}
        self.log = log
        self.active = True

    def live(self, doc):
        with self.lock:
            if doc not in self.lives:
                self.lives[doc] = Live(self.wd, doc, self)
            return self.lives[doc]

    def items(self):
        return items(self.log) if self.log else []

    def send_items(self):
        its = self.items()
        for lv in list(self.lives.values()):
            lv.send("items", its)

    def cli(self):
        """이 건을 처리하는 CLI 세션 — waiting·working·none. 리뷰가 닫힌 건은 none."""
        if not self.active:
            return {"state": "none"}
        st = lease_state(_owner_path(self.wd))
        return {"state": st["state"], "seen": st.get("seen"), "since": st.get("since")}


def _stage(wd):
    """목록에 보일 단계 — 인도본·초안·아웃라인·분석 순으로 가장 앞선 산출물."""
    finals = sorted((wd / "final").glob("*.hwpx")) if (wd / "final").is_dir() else []
    if finals:
        m = re.match(r"^(r\d+)_", finals[-1].name)
        return f"인도 {m.group(1)}" if m else "인도"
    for name, lab in ((DRAFT, "초안"), ("10_outline.md", "아웃라인"), ("05_analysis.md", "분석")):
        if (wd / name).is_file():
            return lab
    return "조사"


class Hub:
    def __init__(self, work_dir):
        self.boot = f"{time.time_ns():x}"
        self.stop = threading.Event()
        self.cases = {}
        self.primary = self.case(work_dir, active=True)
        root = self.primary.wd.parent.parent
        self.root = root if re.fullmatch(r"\d{8}", self.primary.wd.parent.name) else None

    def case(self, work_dir, active=False):
        wd = pathlib.Path(work_dir).resolve()
        key = f"{wd.parent.name}/{wd.name}"
        c = self.cases.get(key)
        if c is None:
            c = self.cases[key] = Case(wd, active, self.boot, self.stop)
        elif active:
            c.activate()
        return c

    def find(self, date, slug):
        """주소의 건 — 등록된 건이 아니면 보고서 폴더 아래 실제 폴더일 때만 보기 전용으로 연다."""
        key = f"{date}/{slug}"
        if key in self.cases:
            return self.cases[key]
        if self.root and re.fullmatch(r"\d{8}", date):
            wd = self.root / date / slug
            if wd.is_dir() and list_docs(wd):
                return self.case(wd)
        return None

    def listing(self):
        """보고서 목록 — 등록 건 + 보고서 폴더의 건(최근 날짜 먼저)."""
        seen, out = set(), []
        dirs = [c.wd for c in self.cases.values()]
        if self.root and self.root.is_dir():
            for d in sorted(self.root.iterdir(), reverse=True):
                if d.is_dir() and re.fullmatch(r"\d{8}", d.name):
                    dirs += [x for x in sorted(d.iterdir(), reverse=True) if x.is_dir() and not x.name.startswith("_")]
        for wd in dirs:
            key = f"{wd.parent.name}/{wd.name}"
            if key in seen or not list_docs(wd):
                continue
            seen.add(key)
            c = self.cases.get(key)
            its = c.items() if c else []
            open_n = sum(1 for x in its if x.get("type") == "feedback" and x["status"] in ("sent", "delivered"))
            mtimes = [p.stat().st_mtime for p in wd.glob("*.md")]
            title, hhmm = case_title(wd.name)
            out.append({"key": key, "date": wd.parent.name, "name": wd.name, "title": title, "time": hhmm,
                        "active": bool(c and c.active), "cli": c.cli()["state"] if c else "none", "wd": str(wd),
                        "stage": _stage(wd), "docs": len(list_docs(wd)), "open": open_n,
                        "updated": datetime.datetime.fromtimestamp(max(mtimes)).strftime("%m.%d %H:%M") if mtimes else "",
                        "url": "/r/" + urllib.parse.quote(wd.parent.name) + "/" + urllib.parse.quote(wd.name) + "/"})
        out.sort(key=lambda x: (not x["active"], x["key"]), reverse=False)
        act = [x for x in out if x["active"]]
        rest = sorted([x for x in out if not x["active"]], key=lambda x: x["key"], reverse=True)
        return act + rest


def make_server(work_dir, port=0):
    hub = Hub(work_dir)
    primary = hub.primary

    def state(case, doc):
        return {"boot": hub.boot, "ui": ui_version(), "version": case.live(doc).current()[1], "items": case.items(),
                "perm": doc_perm(doc, case.active, is_record(case.wd, doc)), "cli": case.cli()}

    def watch_cli():
        """건별 CLI 상태가 바뀌면(wait 시작·끝, 세션 종료, 임대 만료) 열린 탭에 알린다 — 브라우저는 묻지 않는다."""
        last = {}
        while not hub.stop.wait(CLI_WATCH_SEC):
            for c in list(hub.cases.values()):
                cur = c.cli()
                if last.get(c.key) != cur["state"]:
                    last[c.key] = cur["state"]
                    for lv in list(c.lives.values()):
                        lv.send("cli", cur)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):          # 콘솔 소음 제거
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _json(self, code, obj):
            return self._send(code, json.dumps(obj, ensure_ascii=False))

        def _route(self):
            """(건, 나머지 경로, 질의) — /r/{날짜}/{폴더}/… 아니면 옛 주소(/api/…)는 처음 등록한 건으로."""
            u = urllib.parse.urlparse(self.path)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            path = urllib.parse.unquote(u.path)
            m = re.match(r"^/r/([^/]+)/([^/]+)(/.*)?$", path)
            if m:
                return hub.find(m.group(1), m.group(2)), (m.group(3) or "/"), q
            return (primary if path.startswith("/api/") else None), path, q

        def _doc(self, case, doc):
            doc = doc or DRAFT
            if doc not in list_docs(case.wd):
                raise ValueError(f"문서가 없다: {doc}")
            return doc

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path in ("/", "/index.html"):           # 목록 화면은 두지 않는다 — 보고서·문서는 왼쪽 탐색 서랍이 맡는다
                act = [c for c in hub.cases.values() if c.active] or [primary]
                return self._send(302, "", "text/plain", {"Location": act[0].prefix + "/"})
            if u.path == "/api/hub":
                return self._json(200, {"hub": True, "boot": hub.boot, "cases": hub.listing()})
            case, rest, q = self._route()
            if case is None:
                return self._json(404, {"error": "not found"})
            try:
                if rest == "/":                          # 건 첫 화면 — 초안이 있으면 초안
                    docs = list_docs(case.wd)
                    first = DRAFT if DRAFT in docs else (docs[0] if docs else "")
                    return self._send(302, "", "text/plain", {"Location": case.prefix + "/d/" + urllib.parse.quote(first)})
                if rest.startswith("/d/"):
                    doc = self._doc(case, rest[3:])
                    return self._send(200, case.live(doc).page(), "text/html; charset=utf-8")
                doc = self._doc(case, q.get("doc"))
                if rest == "/api/state":
                    return self._json(200, state(case, doc))
                if rest == "/api/events":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    return case.live(doc).stream(self.wfile, state(case, doc))
                if rest == "/api/source":
                    src = source_of(case.wd, int(q.get("line", "0")), int(q["row"]) if "row" in q else None,
                                    int(q["col"]) if "col" in q else None, doc)
                    return self._json(200, src)
            except (ValueError, OSError, StopIteration) as e:
                return self._json(400, {"error": str(e)})
            self._json(404, {"error": "not found"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json(400, {"error": "json"})
            u = urllib.parse.urlparse(self.path)
            if u.path == "/api/hub/activate":            # 이미 떠 있는 허브에 건을 등록(serve를 두 번째로 부른 경우)
                wd = pathlib.Path(str(body.get("work_dir", "")))
                if not wd.is_dir():
                    return self._json(400, {"error": "작업폴더가 없다"})
                c = hub.case(wd, active=True)
                return self._json(200, {"url": c.prefix + "/", "log": str(c.log), "key": c.key})
            if u.path == "/api/exit":
                self._json(200, {"ok": True})
                hub.stop.set()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return None
            case, rest, _ = self._route()
            if case is None or not rest.startswith("/api/"):
                return self._json(404, {"error": "not found"})
            name = rest[5:]
            try:
                doc = self._doc(case, body.get("doc"))
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            perm = doc_perm(doc, case.active, is_record(case.wd, doc))
            kind = body.get("kind", "수정")
            comment = str(body.get("comment", "")).strip()
            if name == "feedback" and kind in KINDS and (comment or kind in ("삭제", "좋음")):
                if not perm["comment"]:
                    return self._json(403, {"error": "보기 전용 건입니다"})
                case.seq["feedback"] += 1
                e = append_event(case.log, {"type": "feedback", "id": f"f{case.seq['feedback']}", "doc": doc, "kind": kind,
                                            "scope": body.get("scope") if body.get("scope") in SCOPES else "doc",
                                            "addr": str(body.get("addr", ""))[:40], "line": int(body.get("line") or 0),
                                            "quote": str(body.get("quote", ""))[:400],
                                            "comment": (comment or {"삭제": "삭제 요청", "좋음": "좋음"}[kind])[:2000]})
                case.send_items()
                return self._json(200, {"id": e["id"]})
            if name == "withdraw":
                # 아직 Claude가 받지 않은('보냄') 코멘트만 취소된다 — plannotator의 '보내기 전 삭제' 대응
                cur = {x["id"]: x["status"] for x in case.items()}
                if cur.get(body.get("id")) != "sent":
                    return self._json(409, {"error": "이미 전달된 코멘트"})
                append_event(case.log, {"type": "status", "id": body["id"], "status": "withdrawn"})
                case.send_items()
                return self._json(200, {"ok": True})
            if name == "decision" and body.get("decision") in ("approved",) and body.get("factcheck", "경량") in FACTCHECK:
                if not perm["approve"]:
                    return self._json(403, {"error": "승인은 리뷰 중인 건의 초안에서만"})
                case.seq["decision"] += 1
                e = append_event(case.log, {"type": "decision", "id": f"d{case.seq['decision']}", "decision": body["decision"],
                                            "factcheck": body.get("factcheck", "경량"), "note": str(body.get("note", ""))[:2000]})
                case.send_items()
                return self._json(200, {"id": e["id"]})
            if name == "edit":                          # 리뷰 화면 직접 수정 — 문서 한 줄만 바꾸고 곧바로 다시 그린다
                if not perm["edit"]:
                    return self._json(403, {"error": "이 문서는 직접 고칠 수 없습니다 — 코멘트로 요청해 주세요"})
                try:
                    if doc not in case.snapped:          # 문서별 첫 직접 수정 전 사본(R087 history/drafts)
                        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
                        (_drafts(case.wd) / f"{pathlib.Path(doc).stem}.{stamp}.리뷰직접수정전.md").write_text(
                            (case.wd / doc).read_text(encoding="utf-8"), encoding="utf-8")
                        case.snapped.add(doc)
                    line, old, new = apply_edit(case.wd, dict(body, doc=doc))
                except EditConflict as e:
                    return self._json(409, {"error": str(e)})
                except (ValueError, OSError) as e:
                    return self._json(400, {"error": str(e)})
                if new == old:
                    return self._json(200, {"ok": True, "changed": False})
                case.seq["edit"] += 1
                append_event(case.log, {"type": "edit", "id": f"e{case.seq['edit']}", "doc": doc, "addr": str(body.get("addr", ""))[:40],
                                        "line": line, "before": old.strip()[:2000], "after": new.strip()[:2000]})
                issues = check_line((case.wd / doc).read_text(encoding="utf-8"), line) if doc == DRAFT else []
                try:
                    case.live(doc).refresh()
                except (OSError, ValueError):
                    pass
                case.send_items()
                return self._json(200, {"ok": True, "changed": True, "issues": issues})
            if name == "refresh":                       # CLI '반영 완료' — 열린 문서마다 바뀐 항목만 보낸다
                changed = []
                try:
                    for d, lv in list(case.lives.items()):
                        if (case.wd / d).is_file():
                            changed += lv.refresh().get("changed", [])
                    if DRAFT not in case.lives and (case.wd / DRAFT).is_file():
                        changed += case.live(DRAFT).refresh().get("changed", [])
                except (OSError, ValueError) as e:
                    return self._json(500, {"error": str(e)})
                case.send_items()
                return self._json(200, {"ok": True, "changed": changed})
            if name == "activate":                      # 서랍의 '이 보고서 리뷰 열기' — 인도된 건은 개정으로만 연다
                if not case.active:
                    if _stage(case.wd).startswith("인도"):
                        rev = archive_revision.current_version(case.wd)
                        if not body.get("revise"):
                            return self._json(409, {"error": "인도된 건 — 개정으로 열어야 한다", "need_revise": True,
                                                    "rev": rev, "next": rev + 1})
                        if (case.wd / DRAFT).is_file():   # 개정 착수 시점 — 인도본 대비 무엇이 바뀌었는지 남긴다(R087)
                            archive_revision.snapshot(case.wd, f"r{rev:02d}인도후-리뷰개정착수")
                    case.activate()
                    case.log.touch()
                    port = self.server.server_address[1]
                    info = {"url": f"http://127.0.0.1:{port}{case.prefix}/", "hub": f"http://127.0.0.1:{port}/", "port": port,
                            "log": str(case.log), "started": datetime.datetime.now().isoformat(timespec="seconds"),
                            "via": "browser"}             # CLI(wait·resolve·refresh)가 서버를 찾는 자리 — serve와 같다
                    (_drafts(case.wd) / STATE).write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
                return self._json(200, {"ok": True, "cli": case.cli()})
            if name == "notify":                        # CLI가 코멘트 상태만 바꿨을 때(wait의 '확인 중')
                case.send_items()
                return self._json(200, {"ok": True})
            if name in ("deactivate", "exit"):          # 이 건의 리뷰를 닫는다 — 리뷰 중인 건이 없으면 서버도 끈다
                case.active = False
                for lv in list(case.lives.values()):
                    lv.send("items", case.items())
                last = not any(c.active for c in hub.cases.values())
                self._json(200, {"ok": True, "server_stopped": last})
                if last:
                    hub.stop.set()
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                return None
            self._json(400, {"error": "bad request"})

    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)   # 포트가 사용 중이면 여기서 OSError — 기록 파일은 아직 안 만든다
    primary.log.touch()
    threading.Thread(target=watch_cli, daemon=True).start()
    srv.daemon_threads = True
    srv.hub = hub
    srv.log_path = primary.log
    srv.live = primary.live(DRAFT)
    srv.case_url = f"http://127.0.0.1:{srv.server_address[1]}{primary.prefix}/"
    return srv


# ---------------------------------------------------------------------------
# 직접 수정 — 리뷰 화면에서 문장·표 칸의 글자를 바로 고친다('26.9.24 사용자 선택: 문장 + 표 칸)
# ---------------------------------------------------------------------------
# 화면의 항목은 초안의 몇째 줄인지(data-line)를 이미 달고 있다. 고친 글자는 그 줄에만 되돌려 쓰고,
# 계층 기호·앞 공백·굵은 머리말 표기(**…**)는 서버가 다시 붙인다 — 사람은 글자만 고친다.
# 동시 수정은 '받아 간 원문 줄 == 지금 줄'일 때만 쓴다(CLI가 먼저 고쳤으면 409로 거절).

LEAD_LINE = re.compile(r"^(\s*(?:□|ㅇ|○|※|＊|☞|-)\s*)(?:\*\*(.+?)\*\*\s+)?(.*)$")
WRAPPED = (re.compile(r"^(\s*<\s*)(.*?)(\s*>\s*)$"), re.compile(r"^(\s*\[\s*)(.*?)(\s*\]\s*)$"))
TABLE_LINE = re.compile(r"^\s*\|")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}")


class EditConflict(Exception):
    """받아 간 뒤 그 줄이 바뀌었다 — 최신본으로 다시 열어야 한다."""


GENERIC_LEAD = re.compile(r"^(\s*(?:#{1,6}\s+|(?:[-*+]|\d+[.)])\s+|>\s?)?)(.*)$")   # 문서 보기 — 헤딩·목록·인용 기호


def _draft_lines(work_dir, doc=DRAFT):
    return (pathlib.Path(work_dir) / doc).read_text(encoding="utf-8").split("\n")


def _table_rows(lines, start):
    """표 시작 줄(1부터)부터 구분 행을 뺀 행들 — (줄 번호, 원문)."""
    rows, i = [], start - 1
    while i < len(lines) and TABLE_LINE.match(lines[i]):
        if not TABLE_SEP.match(lines[i].replace("|", "", 1)):
            rows.append((i + 1, lines[i]))
        i += 1
    return rows


def source_of(work_dir, line, row=None, col=None, doc=DRAFT):
    """고칠 자리의 원문 — 문장은 앞(기호)·머리말·본문·뒤로 나누고, 표 칸은 그 칸 글자."""
    lines = _draft_lines(work_dir, doc)
    if not 1 <= line <= len(lines):
        raise ValueError("줄 번호가 초안 범위를 벗어났다")
    if row is not None:
        rows = _table_rows(lines, line)
        if not 0 <= row < len(rows):
            raise ValueError("표 행이 없다")
        ln, raw = rows[row]
        cells = render_review_html.split_row(raw)
        if not 0 <= (col or 0) < len(cells):
            raise ValueError("표 칸이 없다")
        return {"kind": "cell", "line": ln, "raw": raw, "col": col or 0, "text": cells[col or 0]}
    raw = lines[line - 1]
    if doc != DRAFT:                                             # 문서 보기 — 기호만 떼고 한 줄 통째(여러 줄 문단은 코멘트로)
        blk = next((b for b in md_view.parse("\n".join(lines)) if b["line"] == line), None)
        if blk and blk.get("lines", 1) > 1:
            raise ValueError("여러 줄에 걸친 문단은 코멘트로 요청해 주세요")
        m = GENERIC_LEAD.match(raw)
        return {"kind": "para", "line": line, "raw": raw, "prefix": m.group(1), "lead": None, "body": m.group(2), "suffix": ""}
    first = next(i for i, x in enumerate(lines) if x.strip()) + 1
    if line == first:                                            # 제목 줄 — 통째
        return {"kind": "para", "line": line, "raw": raw, "prefix": "", "lead": None, "body": raw.strip(), "suffix": ""}
    for rx in WRAPPED:                                           # 발신 줄 < … > · 캡션 [ … ]
        m = rx.match(raw)
        if m:
            return {"kind": "para", "line": line, "raw": raw, "prefix": m.group(1), "lead": None, "body": m.group(2), "suffix": m.group(3)}
    m = LEAD_LINE.match(raw)
    if m:
        return {"kind": "para", "line": line, "raw": raw, "prefix": m.group(1), "lead": m.group(2), "body": m.group(3), "suffix": ""}
    return {"kind": "para", "line": line, "raw": raw, "prefix": "", "lead": None, "body": raw, "suffix": ""}


def _one_line(text):
    return re.sub(r"\s*\n\s*", " ", str(text or "")).strip()


def apply_edit(work_dir, req):
    """직접 수정을 초안에 쓴다 → (줄 번호, 옛 줄, 새 줄). 원문 줄이 바뀌었으면 EditConflict."""
    wd = pathlib.Path(work_dir)
    doc = req.get("doc") or DRAFT
    path = wd / doc
    lines = _draft_lines(wd, doc)
    line = int(req.get("line") or 0)
    if not 1 <= line <= len(lines):
        raise ValueError("줄 번호가 초안 범위를 벗어났다")
    old = lines[line - 1]
    if old != req.get("raw"):
        raise EditConflict("CLI가 이 줄을 먼저 고쳤다 — 최신본으로 다시 열어 주세요")
    if req.get("kind") == "cell":
        text = _one_line(req.get("text"))
        if "|" in text:
            raise ValueError("표 칸에는 '|'를 쓸 수 없다")
        cells = render_review_html.split_row(old)
        col = int(req.get("col") or 0)
        if not 0 <= col < len(cells):
            raise ValueError("표 칸이 없다")
        cells[col] = text
        indent = old[:len(old) - len(old.lstrip())]
        new = indent + "| " + " | ".join(cells) + " |"
    else:
        src = source_of(wd, line, doc=doc)
        body, lead = _one_line(req.get("body")), _one_line(req.get("lead")) if req.get("lead") is not None else None
        if not body and not lead:
            raise ValueError("내용을 모두 지우려면 '삭제' 코멘트로 요청해 주세요")
        new = src["prefix"] + (f"**{lead}** " if lead else "") + body + src["suffix"]
    if new == old:
        return line, old, new
    lines[line - 1] = new
    tmp = path.with_suffix(".md.tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(path)
    return line, old, new


def check_line(text, line):
    """고친 줄에 걸린 표기 검사(lint)·문체 감사 결과 — 그 줄 것만."""
    out = []
    for v in lint_md_profile.lint_text(text):
        if v.get("line") == line:
            out.append({"source": "lint", "rule": v.get("rule"), "message": v.get("message") or v.get("text") or ""})
    viol, warn = audit_style.audit_text(text)
    for v in viol + warn:
        if v.get("line") == line:
            out.append({"source": "audit", "rule": v.get("rule"), "message": v.get("message") or v.get("text") or ""})
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _join(port, work_dir):
    """이미 떠 있는 허브면 그 건을 등록한다 → 건 정보(dict) 또는 None(허브가 아님·응답 없음)."""
    base = f"http://127.0.0.1:{port}"
    try:
        json.loads(urllib.request.urlopen(base + "/api/hub", timeout=2).read())["hub"]
        req = urllib.request.Request(base + "/api/hub/activate", method="POST",
                                     data=json.dumps({"work_dir": str(pathlib.Path(work_dir).resolve())}).encode())
        r = json.loads(urllib.request.urlopen(req, timeout=5).read())
        return {"url": base + r["url"], "hub": base + "/", "port": port, "log": r["log"], "joined": True}
    except (OSError, ValueError, KeyError):
        return None


def serve(work_dir, port=DEFAULT_PORT, open_browser=True):
    fallback = None
    try:
        srv = make_server(work_dir, port)
    except OSError as e:                      # 3333을 다른 프로그램(또는 떠 있는 허브)이 쓰고 있다
        if not port:
            raise
        joined = _join(port, work_dir)        # 떠 있는 허브면 이 건을 합류시키고 끝낸다 — 서버를 새로 띄우지 않는다
        if joined:
            joined["started"] = datetime.datetime.now().isoformat(timespec="seconds")
            (_drafts(work_dir) / STATE).write_text(json.dumps(joined, ensure_ascii=False), encoding="utf-8")
            print(json.dumps(joined, ensure_ascii=False), flush=True)
            if open_browser:
                webbrowser.open(joined["url"])
            return 0
        fallback = {"wanted": port, "reason": f"사용 중({e.strerror or e})"}
        srv = make_server(work_dir, 0)
    url = srv.case_url
    info = {"url": url, "hub": f"http://127.0.0.1:{srv.server_address[1]}/", "port": srv.server_address[1],
            "log": str(srv.log_path), "started": datetime.datetime.now().isoformat(timespec="seconds")}
    if fallback:
        info["port_fallback"] = fallback
    (_drafts(work_dir) / STATE).write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(info, ensure_ascii=False), flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    finally:
        (_drafts(work_dir) / STATE).unlink(missing_ok=True)
    return 0


def _hub_active(port):
    """허브에서 리뷰 중인 건의 작업폴더 — wait --all의 대상."""
    hub = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/hub", timeout=3).read())
    return [pathlib.Path(c["wd"]) for c in hub["cases"] if c.get("active") and c.get("wd")]


def wait(work_dir=None, timeout=None, all_cases=False, port=DEFAULT_PORT, grace=GRACE_SEC):
    """새 코멘트·결정이 올 때까지 기다린다 → JSON 출력 후 종료.

    건마다 **처리 세션 임대**를 잡는다 — 다른 세션이 잡은 건은 넘기고(모두 남의 것이면 exit 3), 같은 코멘트를
    두 세션이 고치지 않게 한다. 기다리는 동안 신호를 남겨 화면에 'CLI 대기 중'이 보이고, 끝나면 '처리 중'으로
    바뀐다. `--all`은 허브에서 리뷰 중인 건 전부를 보고(도중에 열린 건도 5초마다 합류), 항목에 case·work_dir을 붙인다."""
    me = session_owner()
    owned, held = {}, {}

    def claim():
        try:
            wds = _hub_active(port) if all_cases else [pathlib.Path(work_dir)]
        except (OSError, ValueError, KeyError):
            wds = []
        for wd in wds:
            wd = wd.resolve()
            if str(wd) in owned:
                continue
            ok, cur = lease_claim(_owner_path(wd), me, waiting=True)
            if ok:
                owned[str(wd)] = wd
                held.pop(str(wd), None)
            else:
                held[str(wd)] = {"work_dir": str(wd), "state": cur["state"], "since": cur.get("since")}

    def rest():
        for wd in owned.values():
            lease_claim(_owner_path(wd), me, waiting=False)

    claim()
    if not owned:
        print(json.dumps({"error": "다른 세션이 처리 중인 건 — 그 세션에서 처리하거나 stop으로 닫은 뒤 다시",
                          "held": list(held.values())}, ensure_ascii=False, indent=1))
        return 3
    main_thread = threading.current_thread() is threading.main_thread()
    prev = signal.signal(signal.SIGTERM, lambda *a: sys.exit(143)) if main_thread else None   # 중지돼도 '대기 중'을 거둔다
    start = beat = scan = time.time()
    try:
        while True:
            got, hit = [], []
            for wd in owned.values():
                pending = collect_pending(_log_path(wd), grace)
                if pending:
                    hit.append(wd)
                    got += [dict(x, case=f"{wd.parent.name}/{wd.name}", work_dir=str(wd)) if all_cases else x
                            for x in pending]
            if got:
                rest()
                for wd in hit:
                    _ping(wd, "api/notify")        # 패널의 '보냄' → '확인 중'
                out = {"items": got}
                if held:
                    out["held"] = list(held.values())
                print(json.dumps(out, ensure_ascii=False, indent=1))
                return 0
            now = time.time()
            if timeout and now - start > timeout:
                print(json.dumps({"items": [], "timeout": True}))
                return 1
            if now - beat > BEAT_SEC:
                for wd in owned.values():
                    lease_claim(_owner_path(wd), me, waiting=True)
                beat = now
            if all_cases and now - scan > 5:
                claim()
                scan = now
            time.sleep(POLL_SEC)
    finally:
        rest()
        if main_thread:
            signal.signal(signal.SIGTERM, prev)


def _ping(work_dir, path):
    """실행 중인 서버에 POST 한 번 — 서버가 없거나 응답이 없으면 False."""
    st = _state(work_dir)
    if not st:
        return False
    try:
        urllib.request.urlopen(urllib.request.Request(st["url"] + path, data=b"{}", method="POST"), timeout=5)
        return True
    except OSError:
        return False


def resolve(work_dir, ids):
    """반영 완료 표시 + 열린 화면 갱신 — 수정이 끝났다는 신호이므로 화면이 바로 따라오게 한다."""
    log = _log_path(work_dir)
    known = {x["id"] for x in items(log)}
    for i in ids:
        if i in known:
            append_event(log, {"type": "status", "id": i, "status": "resolved"})
    print(json.dumps({"resolved": [i for i in ids if i in known], "refreshed": _ping(work_dir, "api/refresh")},
                     ensure_ascii=False))
    return 0


def refresh(work_dir):
    ok = _ping(work_dir, "api/refresh")
    print(json.dumps({"refreshed": ok} if ok else {"refreshed": False, "reason": "실행 중인 서버 없음"},
                     ensure_ascii=False))
    return 0 if ok else 1


def stop(work_dir):
    """이 건의 리뷰를 닫는다 — 허브에 리뷰 중인 건이 더 없으면 서버도 끝난다."""
    lease_release(_owner_path(work_dir))          # 이 건의 처리 세션 임대도 푼다(서버가 없어도)
    st = _state(work_dir)
    if not st:
        print(json.dumps({"stopped": False, "reason": "실행 중인 서버 없음"}, ensure_ascii=False))
        return 1
    _ping(work_dir, "api/deactivate")
    (_drafts(work_dir) / STATE).unlink(missing_ok=True)
    print(json.dumps({"stopped": True}, ensure_ascii=False))
    return 0


def harness_lock(action, why="", state_dir=None):
    """규칙 승격·하네스 코드 수정·변환은 한 번에 한 건 — state_dir 잠금(건 임대와 같은 방식).
    여러 건을 함께 정리하면 한 건의 규칙 코멘트가 코드를 바꿀 때 다른 건이 변환 중일 수 있다('26.9.25)."""
    sd = pathlib.Path(state_dir or load_config()["state_dir"])
    sd.mkdir(parents=True, exist_ok=True)
    path, me = sd / HARNESS_LOCK, session_owner()
    if action == "acquire":
        ok, cur = lease_claim(path, me, why=why)
        print(json.dumps({"locked": True} if ok else
                         {"locked": False, "held": {k: cur.get(k) for k in ("why", "since", "state")}}, ensure_ascii=False))
        return 0 if ok else 3
    if action == "release":
        print(json.dumps({"released": lease_release(path, me)}, ensure_ascii=False))
        return 0
    cur = lease_state(path)
    print(json.dumps({k: cur.get(k) for k in ("state", "why", "since")}, ensure_ascii=False))
    return 0


def harness_sum(state_dir=None):
    """하네스 지문 — 스킬 폴더(스크립트·참조·자산)와 운영 규칙(rules.md). 서브에이전트에 코멘트 처리를 넘기기
    전후로 대조해, 데이터만 고치라는 경계를 지켰는지 결정론으로 확인한다('26.9.25 분담: 데이터는 에이전트,
    하네스·규칙은 메인). 저장소 밖(플러그인 설치 환경)에서도 git 없이 쓸 수 있다."""
    skill = pathlib.Path(__file__).resolve().parent.parent
    rules = pathlib.Path(state_dir or load_config()["state_dir"]) / "rules.md"
    files = sorted(p for p in skill.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    h = hashlib.sha256()
    for p, name in [(p, str(p.relative_to(skill))) for p in files] + ([(rules, "rules.md")] if rules.is_file() else []):
        h.update(name.encode("utf-8") + b"\0" + p.read_bytes())
    return {"sum": h.hexdigest()[:16], "files": len(files) + rules.is_file()}


def main(argv=None):
    ap = argparse.ArgumentParser(description="게이트② 라이브 리뷰 서버")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve"); s.add_argument("work_dir")
    s.add_argument("--port", type=int, default=DEFAULT_PORT, help="기본 3333, 0이면 빈 포트 자동")
    s.add_argument("--no-open", action="store_true")
    w = sub.add_parser("wait"); w.add_argument("work_dir", nargs="?"); w.add_argument("--timeout", type=float)
    w.add_argument("--all", dest="all_cases", action="store_true", help="허브에서 리뷰 중인 건 전부")
    w.add_argument("--port", type=int, default=DEFAULT_PORT)
    r = sub.add_parser("resolve"); r.add_argument("work_dir"); r.add_argument("ids", nargs="+")
    f = sub.add_parser("refresh"); f.add_argument("work_dir")
    t = sub.add_parser("stop"); t.add_argument("work_dir")
    k = sub.add_parser("lock"); k.add_argument("action", choices=("acquire", "release", "status"))
    k.add_argument("--why", default="", help="잠그는 까닭(건·작업)")
    sub.add_parser("sum", help="하네스 지문 — 서브에이전트 처리 전후 대조")
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        return serve(a.work_dir, a.port, not a.no_open)
    if a.cmd == "wait":
        if not a.work_dir and not a.all_cases:
            ap.error("wait에는 work_dir 또는 --all이 필요하다")
        return wait(a.work_dir, a.timeout, a.all_cases, a.port)
    if a.cmd == "lock":
        return harness_lock(a.action, a.why)
    if a.cmd == "sum":
        print(json.dumps(harness_sum(), ensure_ascii=False))
        return 0
    if a.cmd == "resolve":
        return resolve(a.work_dir, a.ids)
    if a.cmd == "refresh":
        return refresh(a.work_dir)
    return stop(a.work_dir)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(2)
