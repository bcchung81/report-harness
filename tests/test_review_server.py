"""라이브 리뷰 서버 — 창을 닫지 않고 코멘트를 여러 번 보내고, 초안 변경이 바로 보인다 (review_server.py)."""
import sys, json, pathlib, threading, urllib.request, urllib.error, re
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import review_server as rs

DRAFT = "시험 보고\n\n< '26. 9. 24.(목), 경영기획본부 AI디지털심화팀 >\n\n□ 개 요\n\nㅇ **(측정 기준)** 과제 18건을 4개 유형으로 나눔\n"


def _start(tmp_path):
    (tmp_path / "20_draft.md").write_text(DRAFT, encoding="utf-8")
    srv = rs.make_server(tmp_path)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def _get(url):
    return urllib.request.urlopen(url, timeout=5).read().decode("utf-8")


def _post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=5).read())


def test_page_is_live_and_static_copy_has_no_script(tmp_path):
    srv, base = _start(tmp_path)
    try:
        html = _get(srv.case_url + "d/20_draft.md")
        assert "라이브 리뷰" in html and "(측정 기준)" in html and "<script>" in html
        assert not re.search(r"(?:src|href)=\"https?://", html)          # 외부 URL 없음
        static = (tmp_path / "history/drafts/25_review.html").read_text(encoding="utf-8")
        assert "<script" not in static                                   # 정적 사본은 스크립트 없음
    finally:
        srv.shutdown()


def test_feedback_roundtrip_without_closing(tmp_path):
    """코멘트 두 번 → wait가 둘 다 넘기고 '확인 중' → resolve로 '반영됨' — 서버는 계속 살아 있다."""
    srv, base = _start(tmp_path)
    try:
        a = _post(base + "/api/feedback", {"addr": "□1-ㅇ1", "line": 7, "quote": "과제 18건", "comment": "수치 근거 추가"})
        b = _post(base + "/api/feedback", {"addr": "전체", "line": 0, "quote": "", "comment": "표 제목 확인"})
        assert (a["id"], b["id"]) == ("f1", "f2")
        pending = rs.collect_pending(srv.log_path)
        assert [x["id"] for x in pending] == ["f1", "f2"] and pending[0]["quote"] == "과제 18건"
        assert rs.collect_pending(srv.log_path) == []                   # 같은 코멘트를 두 번 넘기지 않는다
        rs.resolve(tmp_path, ["f1"])
        st = json.loads(_get(base + "/api/state"))
        assert {x["id"]: x["status"] for x in st["items"]} == {"f1": "resolved", "f2": "delivered"}
        _post(base + "/api/feedback", {"addr": "□1", "comment": "세 번째"})   # 여전히 받는다
        assert [x["id"] for x in rs.collect_pending(srv.log_path)] == ["f3"]
    finally:
        srv.shutdown()


def test_screen_changes_only_on_cli_signal(tmp_path):
    """화면은 CLI '반영 완료'(refresh) 때만 바뀐다 — 고치는 도중의 초안은 새로 연 탭에도 나오지 않는다('26.9.24)."""
    srv, base = _start(tmp_path)
    try:
        v1 = json.loads(_get(base + "/api/state"))["version"]
        (tmp_path / "20_draft.md").write_text(DRAFT.replace("과제 18건을", "과제 20건을"), encoding="utf-8")
        assert json.loads(_get(base + "/api/state"))["version"] == v1          # 신호 전 — 그대로
        assert "과제 20건을" not in _get(srv.case_url + "d/20_draft.md")
        r = _post(base + "/api/refresh", {})
        assert r["changed"] == ["□1-ㅇ1"]                                    # 바뀐 항목만
        assert json.loads(_get(base + "/api/state"))["version"] != v1 and "과제 20건을" in _get(srv.case_url + "d/20_draft.md")
        assert "과제 20건을" in (tmp_path / "history/drafts/25_review.html").read_text(encoding="utf-8")
    finally:
        srv.shutdown()


def test_diff_sends_only_changed_blocks_and_line_shifts():
    """항목 단위 비교 — 글이 바뀐 항목은 조각, 위에 빈 줄이 늘어 번호만 밀린 항목은 번호만, 항목이 늘면 그 쪽 통째."""
    old, _ = rs.snapshot_text(DRAFT)
    new, _ = rs.snapshot_text(DRAFT.replace("과제 18건을", "과제 20건을"))
    d = rs.diff_parts(old, new)
    assert [x["i"] for x in d["blocks"]] == [3] and d["changed"] == ["□1-ㅇ1"] and "pages" not in d
    shifted, _ = rs.snapshot_text(DRAFT.replace("□ 개 요", "\n□ 개 요"))
    d = rs.diff_parts(old, shifted)
    assert "blocks" not in d and d["lines"] and d["changed"] == []
    grown, _ = rs.snapshot_text(DRAFT + "\nㅇ **(추가)** 새 항목\n")
    d = rs.diff_parts(old, grown)
    assert list(d["pages"]) == [0] and "blocks" not in d


def test_events_stream_pushes_patch_without_polling(tmp_path):
    """열어 둔 연결(SSE)로 hello → 신호가 올 때만 items·patch — 브라우저는 주기 요청을 하지 않는다."""
    srv, base = _start(tmp_path)
    resp = urllib.request.urlopen(base + "/api/events", timeout=10)
    try:
        def event():
            name = data = None
            while True:
                line = resp.readline().decode("utf-8").rstrip("\n")
                if line.startswith("event: "):
                    name = line[7:]
                elif line.startswith("data: "):
                    data = json.loads(line[6:])
                elif line == "" and name:
                    return name, data
        name, hello = event()
        assert name == "hello" and hello["version"] and hello["boot"] and hello["items"] == []
        (tmp_path / "20_draft.md").write_text(DRAFT.replace("과제 18건을", "과제 20건을"), encoding="utf-8")
        _post(base + "/api/refresh", {})
        name, patch = event()
        assert name == "patch" and patch["from"] == hello["version"] and patch["changed"] == ["□1-ㅇ1"]
        assert "과제 20건을" in patch["blocks"][0]["html"]
        assert event()[0] == "items"
    finally:
        srv.live.stop.set()
        resp.close()
        srv.shutdown()


def test_approve_is_delivered_as_decision(tmp_path):
    srv, base = _start(tmp_path)
    try:
        _post(base + "/api/decision", {"decision": "approved", "note": "팩트체크 경량"})
        pending = rs.collect_pending(srv.log_path)
        assert pending[0]["type"] == "decision" and pending[0]["decision"] == "approved"
        req = urllib.request.Request(base + "/api/decision", data=b'{"decision":"rm -rf"}', method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "허용되지 않은 결정값이 통과했다"
        except urllib.error.HTTPError as e:
            assert e.code == 400
    finally:
        srv.shutdown()


def test_handler_overrides_http_callbacks(tmp_path):
    """http.server가 이름으로 부르는 콜백(do_GET·do_POST·log_message)을 재정의한다 — 요청 로그는 콘솔에 찍지 않는다."""
    (tmp_path / "20_draft.md").write_text(DRAFT, encoding="utf-8")
    srv = rs.make_server(tmp_path)
    try:
        h = srv.RequestHandlerClass
        assert all(name in vars(h) for name in ("do_GET", "do_POST", "log_message"))
    finally:
        srv.server_close()


def test_overlay_offers_hover_and_click_selection():
    """선택 가능 표시(마우스 올림 테두리)와 클릭 선택이 있다 — 드래그만 되던 '26.9.24 결함의 회귀 방지."""
    ov = rs.overlay()
    assert ".dg .box:hover" in ov and ".blk[data-addr]" in ov
    assert "addEventListener('click'" in ov and "rv-sel" in ov
    assert "http" not in ov.replace("http.server", "")                   # 외부 URL 없음


def test_kinds_withdraw_and_factcheck(tmp_path):
    """주석 유형(수정·삭제·질문·좋음), 전달 전 취소, 승인 팩트체크 — plannotator 기능 대응('26.9.24)."""
    srv, base = _start(tmp_path)
    try:
        _post(base + "/api/feedback", {"addr": "□1", "kind": "삭제", "comment": ""})
        _post(base + "/api/feedback", {"addr": "□1-ㅇ1", "kind": "질문", "comment": "근거는?"})
        assert _post(base + "/api/withdraw", {"id": "f2"}) == {"ok": True}
        pending = rs.collect_pending(srv.log_path)
        assert [(x["id"], x["kind"], x["comment"]) for x in pending] == [("f1", "삭제", "삭제 요청")]
        try:
            _post(base + "/api/withdraw", {"id": "f1"})                  # 이미 전달됨 — 취소 불가
            assert False
        except urllib.error.HTTPError as e:
            assert e.code == 409
        _post(base + "/api/decision", {"decision": "approved", "factcheck": "전수", "note": ""})
        assert rs.collect_pending(srv.log_path)[0]["factcheck"] == "전수"
        try:
            _post(base + "/api/feedback", {"kind": "몰라", "comment": "x"})
            assert False
        except urllib.error.HTTPError as e:
            assert e.code == 400
    finally:
        srv.shutdown()


def test_boot_and_hot_reload(tmp_path):
    """서버를 다시 띄우면 부팅 ID가 바뀌어 열린 탭이 기준본을 다시 받고, 렌더러 코드는 파일이 바뀌면 다시 읽는다."""
    srv, base = _start(tmp_path)
    try:
        st = json.loads(_get(base + "/api/state"))
        assert st["boot"] and st["ui"] == rs.ui_version()
    finally:
        srv.shutdown()
    srv2, base2 = _start(tmp_path)
    try:
        assert json.loads(_get(base2 + "/api/state"))["boot"] != st["boot"]
    finally:
        srv2.shutdown()
    rs._MOD_SIG["sig"] = ("낡은 서명",)                                 # 모듈 파일이 바뀐 것처럼
    assert rs.reload_renderers() is True and rs.reload_renderers() is False
    assert "<html" in rs.render_review_html.render(DRAFT)[0]


def test_review_page_has_no_top_banner():
    doc, _ = rs.render_review_html.render(DRAFT)
    assert "리뷰용 미리보기" not in doc and 'class="bar"' not in doc and '<meta name="generated"' in doc


def test_diff_keeps_duplicate_addresses_apart():
    """붙임 배너와 그 뒤 '끝.'은 같은 주소를 쓴다 — 바뀌지 않은 배너를 바뀐 것으로 보고하지 않는다."""
    text = DRAFT + "\n| 붙임 1 | | 대장 |\n| --- | --- | --- |\n\n끝.\n"
    old, _ = rs.snapshot_text(text)
    new, _ = rs.snapshot_text(text.replace("과제 18건을", "과제 20건을"))
    assert rs.diff_parts(old, new)["changed"] == ["□1-ㅇ1"]


def test_serve_prefers_port_3333_and_falls_back_when_busy(tmp_path, monkeypatch):
    """기본 주소는 http://127.0.0.1:3333/ — 사용 중이면 빈 포트로 띄우고 그 사실을 알린다."""
    import socket
    assert rs.DEFAULT_PORT == 3333
    (tmp_path / "20_draft.md").write_text(DRAFT, encoding="utf-8")
    busy = socket.socket(); busy.bind(("127.0.0.1", 0)); busy.listen(1)
    port = busy.getsockname()[1]
    started = {}
    monkeypatch.setattr(rs.ThreadingHTTPServer, "serve_forever", lambda self, *a: started.setdefault("port", self.server_address[1]))
    try:
        rs.serve(tmp_path, port, open_browser=False)
    finally:
        busy.close()
    assert started["port"] != port
    assert len(list((tmp_path / "history/drafts").glob("26_review.*.jsonl"))) == 1   # 실패한 시도는 기록 파일을 안 남긴다


def test_feedback_scope_doc_or_rule(tmp_path):
    """적용 범위 — 기본은 이 보고서만(doc), '앞으로도 적용'은 rule(규칙 후보)로 wait에 전달된다."""
    srv, base = _start(tmp_path)
    try:
        _post(base + "/api/feedback", {"addr": "□1", "comment": "문구 수정"})
        _post(base + "/api/feedback", {"addr": "□1", "comment": "표 제목은 늘 대괄호", "scope": "rule"})
        _post(base + "/api/feedback", {"addr": "□1", "comment": "이상한 값", "scope": "all"})
        got = [(x["comment"], x["scope"]) for x in rs.collect_pending(srv.log_path)]
        assert got == [("문구 수정", "doc"), ("표 제목은 늘 대괄호", "rule"), ("이상한 값", "doc")]
        assert 'data-s="rule"' in rs.overlay()
    finally:
        srv.shutdown()


EDIT_DRAFT = """시험 보고

< '26. 9. 24.(목), 경영기획본부 AI디지털심화팀 >

□ 개 요

ㅇ **(측정 기준)** 과제 18건을 4개 유형으로 나눔

  - 검수 시간을 넣어 착시를 차단

[ 표 제목 ]

| 구 분 | 내 용 |
| --- | --- |
| 식 별 | 처리 번호 |
"""


def test_direct_edit_paragraph_keeps_marks_and_lead(tmp_path):
    """직접 수정 — 기호·앞 공백·굵은 머리말 표기는 서버가 다시 붙이고, 사람은 글자만 고친다('26.9.24)."""
    (tmp_path / "20_draft.md").write_text(EDIT_DRAFT, encoding="utf-8")
    src = rs.source_of(tmp_path, 7)
    assert (src["prefix"], src["lead"], src["body"]) == ("ㅇ ", "(측정 기준)", "과제 18건을 4개 유형으로 나눔")
    line, old, new = rs.apply_edit(tmp_path, {"kind": "para", "line": 7, "raw": src["raw"], "lead": "(측정 원칙)", "body": "과제 18건을\n4개 유형으로 나눔"})
    assert new == "ㅇ **(측정 원칙)** 과제 18건을 4개 유형으로 나눔"
    dash = rs.source_of(tmp_path, 9)
    rs.apply_edit(tmp_path, {"kind": "para", "line": 9, "raw": dash["raw"], "lead": None, "body": "검수 시간을 넣어 착시 차단"})
    assert (tmp_path / "20_draft.md").read_text(encoding="utf-8").split("\n")[8] == "  - 검수 시간을 넣어 착시 차단"
    sending = rs.source_of(tmp_path, 3)
    assert sending["body"] == "'26. 9. 24.(목), 경영기획본부 AI디지털심화팀" and sending["suffix"].strip() == ">"


def test_direct_edit_table_cell_and_conflict(tmp_path):
    (tmp_path / "20_draft.md").write_text(EDIT_DRAFT, encoding="utf-8")
    cell = rs.source_of(tmp_path, 13, row=1, col=1)
    assert (cell["line"], cell["text"]) == (15, "처리 번호")
    rs.apply_edit(tmp_path, {"kind": "cell", "line": 15, "raw": cell["raw"], "col": 1, "text": "처리 번호(자동)"})
    assert (tmp_path / "20_draft.md").read_text(encoding="utf-8").split("\n")[14] == "| 식 별 | 처리 번호(자동) |"
    with pytest.raises(rs.EditConflict):                      # 받아 간 뒤 줄이 바뀌었다
        rs.apply_edit(tmp_path, {"kind": "cell", "line": 15, "raw": cell["raw"], "col": 1, "text": "다른 값"})
    with pytest.raises(ValueError):
        rs.apply_edit(tmp_path, {"kind": "cell", "line": 15, "raw": "| 식 별 | 처리 번호(자동) |", "col": 1, "text": "a | b"})


def test_edit_endpoint_logs_snapshots_and_pushes(tmp_path):
    """POST /api/edit — 초안 사본(첫 수정 전)·이력 이벤트(type edit, wait로 CLI에 전달)·검사 결과·화면 갱신."""
    (tmp_path / "20_draft.md").write_text(EDIT_DRAFT, encoding="utf-8")
    srv = rs.make_server(tmp_path)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        v1 = json.loads(_get(base + "/api/state"))["version"]
        src = json.loads(_get(base + "/api/source?line=7"))
        r = _post(base + "/api/edit", {"kind": "para", "line": 7, "raw": src["raw"], "lead": src["lead"], "body": "과제 20건을 4개 유형으로 나눔", "addr": "□1-ㅇ1"})
        assert r["ok"] and r["changed"] and isinstance(r["issues"], list)
        assert "과제 20건을" in _get(srv.case_url + "d/20_draft.md") and json.loads(_get(base + "/api/state"))["version"] != v1
        assert len(list((tmp_path / "history/drafts").glob("20_draft.*.리뷰직접수정전.md"))) == 1
        pending = rs.collect_pending(srv.log_path)
        assert pending[0]["type"] == "edit" and pending[0]["addr"] == "□1-ㅇ1" and "과제 20건을" in pending[0]["after"]
        req = urllib.request.Request(base + "/api/edit", data=json.dumps({"kind": "para", "line": 7, "raw": src["raw"], "body": "x"}).encode(), method="POST")
        try:
            urllib.request.urlopen(req, timeout=5)
            assert False, "충돌이 거절되지 않았다"
        except urllib.error.HTTPError as e:
            assert e.code == 409
    finally:
        srv.live.stop.set()
        srv.shutdown()


def test_restart_continues_open_review_log(tmp_path):
    """서버를 다시 띄워도 승인 전 리뷰는 같은 기록을 이어 쓴다 — 이력·반영 표시가 끊기지 않는다."""
    srv, base = _start(tmp_path)
    try:
        _post(base + "/api/feedback", {"addr": "□1", "comment": "첫 코멘트"})
    finally:
        srv.shutdown(); srv.server_close()
    srv2, base2 = _start(tmp_path)
    try:
        assert srv2.log_path == srv.log_path
        assert _post(base2 + "/api/feedback", {"addr": "□1", "comment": "둘째"})["id"] == "f2"
        _post(base2 + "/api/decision", {"decision": "approved"})
    finally:
        srv2.shutdown(); srv2.server_close()
    import time; time.sleep(1.1)                                  # 기록 파일 이름이 초 단위
    srv3, _ = _start(tmp_path)
    try:
        assert srv3.log_path != srv.log_path                      # 승인 뒤에는 새 회차
    finally:
        srv3.server_close()


# ---------------------------------------------------------------- 허브·모든 md 리뷰 ('26.9.25)
def _case(root, name, draft=DRAFT, extra=None):
    wd = root / "20260101" / name
    wd.mkdir(parents=True)
    (wd / "20_draft.md").write_text(draft, encoding="utf-8")
    for k, v in (extra or {}).items():
        (wd / k).parent.mkdir(parents=True, exist_ok=True)
        (wd / k).write_text(v, encoding="utf-8")
    return wd


def _post_code(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(req, timeout=5).status, None
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_hub_lists_cases_and_docs_have_views_and_permissions(tmp_path):
    a = _case(tmp_path, "0900_가", extra={"10_outline.md": "# 아웃라인\n\n## 1. 절\n\n- 논지 하나\n\n두 줄\n문단\n",
                                          "30_부속.md": "# 부속\n\n## 1. 절\n\n- 논지 하나\n\n두 줄\n문단\n",
                                          "00_context.md": "- 결정 하나\n", "research/20260101-0900_자료.md": "---\ntitle: t\n---\n\n본문\n"})
    _case(tmp_path, "0910_나")
    srv = rs.make_server(a)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        cases = json.loads(_get(host + "/api/hub"))["cases"]
        assert [c["name"] for c in cases][:1] == ["0900_가"] and {c["name"] for c in cases} >= {"0900_가", "0910_나"}
        assert cases[0]["active"] and not [c for c in cases if c["name"] == "0910_나"][0]["active"]
        assert "window.__RV" in _get(host + "/")                                    # 목록 화면 없이 리뷰 중인 건으로
        outline = _get(srv.case_url + "d/10_outline.md")
        assert 'class="page doc"' in outline and "v-heading" in outline and "window.__RV" in outline
        rv = json.loads(re.search(r"window\.__RV=(\{.*?\});</script>", outline).group(1))
        groups = {d["doc"]: d["group"] for d in rv["docs"]}
        assert groups["10_outline.md"] == "stage" and groups["research/20260101-0900_자료.md"] == "research"
        docs = {d["doc"]: d for d in rv["docs"]}
        assert rv["case"]["active"] and not docs["00_context.md"]["perm"]["edit"]
        # 초안이 있으면 아웃라인은 앞 게이트의 기록 — 코멘트만, 초안과 어긋난 수를 단다('26.9.25)
        assert rv["perm"] == {"comment": True, "edit": False, "approve": False} and docs["10_outline.md"]["record"]
        assert docs["10_outline.md"]["drift"] == 1 and "앞 게이트의 기록" in outline      # 초안의 □ 개 요가 아웃라인에 없다
        assert docs["30_부속.md"]["perm"]["edit"] and not docs["30_부속.md"]["record"]
        # 아웃라인 코멘트 — doc이 붙어 기록된다
        _post(srv.case_url + "api/feedback", {"doc": "10_outline.md", "addr": "§1.1-•1", "comment": "논지 보강"})
        got = rs.collect_pending(srv.log_path)
        assert got[0]["doc"] == "10_outline.md" and got[0]["addr"] == "§1.1-•1"
        assert _post_code(srv.case_url + "api/edit", {"doc": "10_outline.md", "kind": "para", "line": 5,
                                                      "raw": "- 논지 하나", "body": "x"})[0] == 403
        # 문서 보기 한 줄 직접 수정은 되고(부속 문서), 여러 줄 문단은 코멘트로
        src = json.loads(_get(srv.case_url + "api/source?doc=" + urllib.parse.quote("30_부속.md") + "&line=5"))
        assert src["prefix"] == "- " and src["body"] == "논지 하나"
        r = _post(srv.case_url + "api/edit", {"doc": "30_부속.md", "kind": "para", "line": 5, "raw": src["raw"], "body": "논지 둘"})
        assert r["changed"] and "- 논지 둘" in (a / "30_부속.md").read_text(encoding="utf-8")
        code, err = _post_code(srv.case_url + "api/edit", {"doc": "30_부속.md", "kind": "para", "line": 7, "raw": "두 줄", "body": "x"})
        assert code == 400
        # 맥락은 코멘트만, research는 고칠 수 없다
        assert _post_code(srv.case_url + "api/edit", {"doc": "00_context.md", "kind": "para", "line": 1, "raw": "- 결정 하나", "body": "x"})[0] == 403
        assert _post_code(srv.case_url + "api/edit", {"doc": "research/20260101-0900_자료.md", "kind": "para", "line": 5, "raw": "본문", "body": "x"})[0] == 403
        assert _post(srv.case_url + "api/feedback", {"doc": "00_context.md", "addr": "§0-•1", "comment": "결정 정정"})["id"]
        # 등록하지 않은 건은 보기 전용 — 화면은 열리고 코멘트는 거절
        other = host + "/r/20260101/" + urllib.parse.quote("0910_나") + "/"
        assert "보기 전용" in _get(other + "d/20_draft.md")
        assert _post_code(other + "api/feedback", {"addr": "□1", "comment": "x"})[0] == 403
    finally:
        srv.shutdown()


def test_second_serve_joins_hub_and_keeps_logs_apart(tmp_path):
    a, b = _case(tmp_path, "0900_가"), _case(tmp_path, "0910_나")
    srv = rs.make_server(a)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        joined = rs._join(port, b)
        assert joined and joined["joined"] and joined["url"].endswith("/")
        _post(joined["url"] + "api/feedback", {"addr": "□1", "comment": "나 건 코멘트"})
        assert rs.collect_pending(srv.log_path) == []                         # 가 건 기록에는 없다
        assert [x["comment"] for x in rs.collect_pending(pathlib.Path(joined["log"]))] == ["나 건 코멘트"]
        r = _post(joined["url"] + "api/deactivate", {})
        assert r["server_stopped"] is False                                   # 가 건이 아직 리뷰 중
        r = _post(srv.case_url + "api/deactivate", {})
        assert r["server_stopped"] is True
    finally:
        srv.shutdown()


def test_left_rail_holds_navigation_not_top_bar():
    """탐색(문서·보고서)은 왼쪽 서랍에 — 위 막대의 콤보·목록 링크 없음, 아이콘은 탐색·이력·전체 의견만('26.9.25)."""
    ov = rs.overlay()
    assert 'data-t="nav"' in ov and 'id="rv-tree"' in ov and 'id="rv-cases"' in ov and 'id="rv-find"' in ov
    assert 'id="rv-docsel"' not in ov and 'id="rv-home"' not in ov
    rail = re.search(r'<nav id="rv-rail".*?</nav>', ov, re.S).group(0)
    assert re.findall(r'data-t="(\w+)"', rail) == ["nav", "hist"] and 'id="rv-general"' in rail
    assert re.findall(r'<span class="lb">(\w+)</span>', rail) == ["탐색", "이력", "의견", "단축키"]   # 아이콘만으로는 뜻이 안 읽힌다
    # 보고서 바꾸기는 서랍 안에 펼치지 않고 버튼 아래 떠 있는 목록(이중 스크롤·트리 밀림 방지)
    assert 'id="rv-cases" class="rv-cases" role="listbox"' in ov and ".rv-cases{position:absolute" in ov
    # 서랍은 창 폭과 관계없이 쪽을 밀어 본문을 덮지 않는다 — 모자라면 메모 폭 → 쪽 배율 순으로 줄인다('26.9.25 사용자 지적:
    # 종전 1640px 이상에서만 밀어 노트북 폭에서 서랍이 본문을 가렸다)
    assert "classList.toggle('rv-dopen'" in ov and "(min-width:1640px)" not in ov
    assert "zoom:var(--rv-z,1)" in ov and "/ var(--rv-z,1))" in ov              # zoom이 여백에도 걸리므로 나눠 준다
    fit = re.search(r"function fitPage\(\)\{.*?setProperty\('--rv-note-w'.*?\}", ov, re.S).group(0)
    assert "drawer?DRAWER_W:RAIL_W" in fit and "--rv-note-w" in fit
    assert "fitPage();" in re.search(r"function openDrawer\(t\)\{.*?\n.*?\n", ov, re.S).group(0)
    assert "addEventListener('resize',()=>{fitPage(); layoutNotes()})" in ov
    # 쪽수 탐침은 쪽 안에서 재야 쪽이 축소돼도 문단과 같은 좌표계다
    pag = re.search(r"function paginate\(\)\{.*?layoutNotes\(\) \}", ov, re.S).group(0)
    assert "sec.appendChild(probe)" in pag and "document.body.appendChild(probe)" not in pag and "mm)'" in pag


def test_doc_and_case_names_are_readable(tmp_path):
    """탐색 서랍은 파일명 대신 사람이 읽는 이름 — research는 프론트매터 title, 없으면 파일명 정리('26.9.25)."""
    res = tmp_path / "research"
    res.mkdir()
    (res / "20260925-0312_METR-무작위실험.md").write_text(
        "---\ntitle: METR, Measuring AI Productivity (2025.7) — 부연\nsource_url: x\n---\n본문\n", encoding="utf-8")
    (res / "20260805-0856_제공-최종본_1_과제관리카드.md").write_text("목차\n", encoding="utf-8")
    (res / "20260915-1620_따옴표.md").write_text(
        "---\ntitle: \"2025년 매뉴얼 (행안부, '25.11 배포 — PDF 243쪽) 발췌\"\n---\n", encoding="utf-8")
    m = rs.doc_meta(tmp_path, "research/20260925-0312_METR-무작위실험.md")
    assert (m["label"], m["sub"]) == ("METR, Measuring AI Productivity", "2025.7") and m["title"].endswith("— 부연")
    m = rs.doc_meta(tmp_path, "research/20260805-0856_제공-최종본_1_과제관리카드.md")
    assert (m["label"], m["sub"]) == ("최종본 1 과제관리카드", "제공 자료")
    m = rs.doc_meta(tmp_path, "research/20260915-1620_따옴표.md")
    assert (m["label"], m["sub"]) == ("2025년 매뉴얼", "행안부, '25.11 배포")
    assert rs.doc_meta(tmp_path, "10_outline.md") == {"num": "10", "label": "아웃라인", "sub": "", "title": "10 아웃라인"}
    assert rs.doc_meta(tmp_path, "30_발표_대본.md")["label"] == "발표 대본"
    assert rs.case_title("1127_AI성과측정-요약본-부서장") == ("AI성과측정 요약본 부서장", "11:27")
    assert rs.case_title("기타") == ("기타", "")



# ---------------------------------------------------------------- 여러 보고서 동시 정리의 안전장치('26.9.25)
def _as(monkeypatch, sid, pid=None):
    """처리 세션 흉내 — Claude Code 세션 ID·프로세스."""
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", sid)
    monkeypatch.setenv("CLAUDE_PID", str(pid or rs.os.getpid()))


def _dead_pid():
    import subprocess
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_wait_refuses_a_case_held_by_another_session(tmp_path, monkeypatch, capsys):
    """한 건은 한 세션만 — 다른 세션이 잡은 건은 wait가 exit 3(같은 코멘트를 두 세션이 고치지 않는다)."""
    srv, base = _start(tmp_path)
    try:
        _as(monkeypatch, "A")
        assert rs.lease_claim(rs._owner_path(tmp_path), rs.session_owner())[0]
        _post(base + "/api/feedback", {"addr": "□1", "comment": "하나"})
        _as(monkeypatch, "B")
        assert rs.wait(tmp_path, timeout=0.3, grace=0) == 3
        assert "다른 세션" in capsys.readouterr().out
        assert [x["status"] for x in rs.items(srv.log_path)] == ["sent"]           # B는 가져가지 않았다
        _as(monkeypatch, "A")
        assert rs.wait(tmp_path, timeout=2, grace=0) == 0
        assert json.loads(capsys.readouterr().out)["items"][0]["comment"] == "하나"
        rs.lease_release(rs._owner_path(tmp_path))
        _as(monkeypatch, "B", _dead_pid())                                          # 세션 프로세스가 끝난 임대는 빈 것
        assert rs.lease_claim(rs._owner_path(tmp_path), rs.session_owner())[0]
        _as(monkeypatch, "C")
        assert rs.lease_claim(rs._owner_path(tmp_path), rs.session_owner())[0] is (rs.os.name != "nt")
    finally:
        srv.shutdown()


def test_cli_state_is_shown_and_stale_lock_is_cleared(tmp_path, monkeypatch):
    """화면의 CLI 상태 — 대기 중·처리 중·없음. 남은 잠금 파일(30초 넘음)은 치우고 넘긴다."""
    srv, base = _start(tmp_path)
    try:
        assert json.loads(_get(base + "/api/state"))["cli"]["state"] == "none"
        _as(monkeypatch, "A")
        me = rs.session_owner()
        rs.lease_claim(rs._owner_path(tmp_path), me, waiting=True)
        assert json.loads(_get(base + "/api/state"))["cli"]["state"] == "waiting"
        rs.lease_claim(rs._owner_path(tmp_path), me, waiting=False)
        assert json.loads(_get(base + "/api/state"))["cli"]["state"] == "working"
        assert json.loads(_get(base + "/api/hub"))["cases"][0]["cli"] == "working"
        lock = pathlib.Path(str(srv.log_path) + ".lock")
        lock.write_text("")
        rs.os.utime(lock, (1, 1))
        _post(base + "/api/feedback", {"addr": "□1", "comment": "둘"})
        assert len(rs.collect_pending(srv.log_path)) == 1 and not lock.exists()
        rs.stop(tmp_path)                                                           # stop은 임대도 푼다
        assert rs.lease_state(rs._owner_path(tmp_path))["state"] == "none"
    finally:
        srv.shutdown()


def test_open_review_from_drawer_and_delivered_case_opens_as_revision(tmp_path):
    """서랍의 '리뷰 열기' — 보기 전용 건을 연다. 인도된 건은 개정으로만(초안 스냅샷, 다음 인도 r02)."""
    a = _case(tmp_path, "0900_가")
    b = _case(tmp_path, "0910_나", extra={"final/r01_20260101_나.hwpx": "x"})
    c = _case(tmp_path, "0920_다")
    srv = rs.make_server(a)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        url_b = host + "/r/20260101/" + urllib.parse.quote("0910_나")
        url_c = host + "/r/20260101/" + urllib.parse.quote("0920_다")
        assert _post_code(url_c + "/api/feedback", {"addr": "□1", "comment": "x"})[0] == 403
        code, err = _post_code(url_b + "/api/activate", {})
        assert code == 409 and err["need_revise"] and err["next"] == 2               # 인도된 건은 확인 없이 안 열린다
        assert _post_code(url_b + "/api/activate", {"revise": True})[0] == 200
        assert any("r01인도후-리뷰개정착수" in p.name for p in (b / "history/drafts").iterdir())
        st = json.loads((b / "history/drafts" / rs.STATE).read_text(encoding="utf-8"))
        assert st["url"].endswith("/r/20260101/" + urllib.parse.quote("0910_나") + "/") and st["via"] == "browser"
        assert _post_code(url_c + "/api/activate", {})[0] == 200
        assert _post_code(url_c + "/api/feedback", {"addr": "□1", "comment": "이제 된다"})[0] == 200
        assert not list((c / "history/drafts").glob("*리뷰개정착수*"))                  # 인도 전 건은 스냅샷 없이 연다
        assert len([x for x in json.loads(_get(host + "/api/hub"))["cases"] if x["active"]]) == 3
    finally:
        srv.shutdown()


def test_wait_all_takes_every_open_case(tmp_path, monkeypatch, capsys):
    """wait --all — 허브에서 리뷰 중인 건 전부의 코멘트를 받고, 항목에 case·work_dir을 붙인다."""
    a = _case(tmp_path, "0900_가")
    b = _case(tmp_path, "0910_나")
    srv = rs.make_server(a)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        url_b = host + "/r/20260101/" + urllib.parse.quote("0910_나")
        _post(url_b + "/api/activate", {})
        _post(srv.case_url + "api/feedback", {"addr": "□1", "comment": "가 코멘트"})
        _post(url_b + "/api/feedback", {"addr": "□1", "comment": "나 코멘트"})
        _as(monkeypatch, "A")
        assert rs.wait(all_cases=True, port=srv.server_address[1], timeout=3, grace=0) == 0
        got = json.loads(capsys.readouterr().out)["items"]
        assert {(x["case"], x["comment"]) for x in got} == {("20260101/0900_가", "가 코멘트"), ("20260101/0910_나", "나 코멘트")}
        assert all(pathlib.Path(x["work_dir"]).is_dir() for x in got)
        assert rs.lease_state(rs._owner_path(b))["state"] == "working"            # 받은 뒤엔 '처리 중'
    finally:
        srv.shutdown()


def test_harness_lock_is_one_case_at_a_time(tmp_path, monkeypatch, capsys):
    """규칙 승격·하네스 코드 수정·변환은 한 번에 한 건 — 다른 세션은 exit 3, 푼 뒤에는 잡힌다."""
    _as(monkeypatch, "A")
    assert rs.harness_lock("acquire", "1127 규칙 코멘트 f10", tmp_path) == 0
    _as(monkeypatch, "B")
    assert rs.harness_lock("acquire", "1523 변환", tmp_path) == 3
    assert "1127 규칙 코멘트 f10" in capsys.readouterr().out
    assert rs.harness_lock("release", state_dir=tmp_path) == 0 and rs.lease_state(tmp_path / rs.HARNESS_LOCK)["state"] != "none"
    _as(monkeypatch, "A")
    rs.harness_lock("release", state_dir=tmp_path)
    _as(monkeypatch, "B")
    assert rs.harness_lock("acquire", "1523 변환", tmp_path) == 0


def test_view_only_case_leaves_no_files(tmp_path):
    """보기 전용으로 연 건에는 아무것도 쓰지 않는다 — 리뷰 사본(25_review.html)은 리뷰를 연 건만('26.9.25)."""
    a = _case(tmp_path, "0900_가")
    b = _case(tmp_path, "0910_나")
    srv = rs.make_server(a)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        url_b = host + "/r/20260101/" + urllib.parse.quote("0910_나")
        assert "window.__RV" in _get(url_b + "/d/20_draft.md")
        _get(url_b + "/api/state")
        assert not (b / "history").exists()
        _get(srv.case_url + "d/20_draft.md")
        assert (a / "history/drafts/25_review.html").is_file()                      # 리뷰를 연 건은 사본을 남긴다
    finally:
        srv.shutdown()


def test_harness_sum_changes_only_when_harness_or_rules_change(tmp_path):
    """서브에이전트 전후 대조용 지문 — 같은 상태면 같고, 운영 규칙이 바뀌면 달라진다."""
    (tmp_path / "rules.md").write_text("- R001 [draft] 규칙\n", encoding="utf-8")
    a, b = rs.harness_sum(tmp_path), rs.harness_sum(tmp_path)
    assert a == b and a["files"] > 10
    (tmp_path / "rules.md").write_text("- R001 [draft] 규칙 바뀜\n", encoding="utf-8")
    assert rs.harness_sum(tmp_path)["sum"] != a["sum"]


def test_sent_comment_is_held_for_grace_so_it_can_be_undone(tmp_path):
    """보낸 코멘트는 5초 뒤에 넘긴다 — 그 사이 '되돌리기'(withdraw)가 통한다. 승인 같은 결정은 바로 넘긴다."""
    srv, base = _start(tmp_path)
    try:
        f = _post(base + "/api/feedback", {"addr": "□1", "comment": "잠깐"})
        assert rs.collect_pending(srv.log_path, grace=5) == []                      # 아직 5초 전
        assert _post(base + "/api/withdraw", {"id": f["id"]}) == {"ok": True}         # 되돌리기 통함
        _post(base + "/api/decision", {"decision": "approved"})
        assert [x["type"] for x in rs.collect_pending(srv.log_path, grace=5)] == ["decision"]
        _post(base + "/api/feedback", {"addr": "□1", "comment": "남는다"})
        lines = srv.log_path.read_text(encoding="utf-8").splitlines()
        e = json.loads(lines[-1]); e["at"] = "2000-01-01T00:00:00"; lines[-1] = json.dumps(e, ensure_ascii=False)
        srv.log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        assert [x["comment"] for x in rs.collect_pending(srv.log_path, grace=5)] == ["남는다"]
    finally:
        srv.shutdown()


def test_overlay_interactive_components():
    """보고서 밖 화면의 인터랙티브 요소('26.9.25) — 빠른 이동·단축키 도움말·되돌리기 알림·진행 단계·
    가장자리 코멘트 위치, 그리고 운영체제 '동작 줄이기' 설정 존중."""
    ov = rs.overlay()
    for need in ('id="rv-cmd"', 'id="rv-cmd-q"', 'id="rv-cmd-open"', 'id="rv-help"', 'id="rv-help-btn"', 'id="rv-mini"',
                 "function undoable(", "function drawMini(", "function showCmd(", "class=\"rv-track\"",
                 "prefers-reduced-motion: reduce", "#rv-drawer.on{visibility:visible"):
        assert need in ov, need
    assert "#rv-cmd,#rv-help" in re.search(r"const inUI=.*", ov).group(0)       # 새 창의 클릭은 문서 클릭이 아니다

