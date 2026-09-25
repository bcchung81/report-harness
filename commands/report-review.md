---
description: "라이브 리뷰어 열기 — 작업폴더의 아웃라인·초안을 한글 양식에 가까운 화면으로 띄우고 코멘트를 받아 반영 (report-pipeline 게이트①·②)"
---

report-pipeline 스킬을 로드하고 **라이브 리뷰어**를 연다. 서버·코멘트 처리 규칙은 SKILL.md 게이트② 절 그대로 따른다 —
이 커맨드는 그 절차를 사용자가 원할 때 바로 시작하는 입구다(게이트①·② 밖에서 초안을 다시 보고 싶을 때도 쓴다).

1. **작업폴더를 정한다** — `$ARGUMENTS`로 고른다.
   - 비었으면 `reports_dir`(`harness_config.py`) 아래 날짜 폴더를 최신순으로 훑어 `20_draft.md` 또는 `10_outline.md`가
     있는 가장 최근 작업폴더를 쓴다.
   - 경로면 그 폴더, 건명·슬러그 일부면 부분일치 폴더(최신순). 여러 건이 맞으면 선택지로 고르게 한다.
   - `all`(또는 `전체`)이면 폴더를 고르지 않고 3번의 `wait --all`만 띄운다 — 허브에서 리뷰 중인 건 전부를 받는다.
   - `닫기`(또는 `stop`)면 그 건의 리뷰를 닫는다: `review_server.py stop {work_dir}`. 여기서 끝낸다.
   - 고른 폴더에 `20_draft.md`도 `10_outline.md`도 없으면 "리뷰할 아웃라인·초안이 없습니다"로 끝낸다.

2. **서버를 띄운다** — Bash 백그라운드로:

   ```
   python3 "$SKILL_DIR/scripts/review_server.py" serve {work_dir}
   ```

   출력의 `url`을 사용자에게 1줄로 알린다(기본 `http://127.0.0.1:3333/`). `joined: true`면 이미 떠 있는 허브에
   합류한 것이고, `port_fallback`이면 3333을 다른 프로그램이 쓰고 있어 출력 `url`이 주소다.

3. **코멘트를 기다린다** — Bash 백그라운드로:

   ```
   python3 "$SKILL_DIR/scripts/review_server.py" wait {work_dir}
   ```

   이 세션에서 같은 건의 `wait`가 이미 돌고 있으면 새로 띄우지 않는다. exit 3이면 다른 세션이 그 건을 잡고 있다 —
   출력의 `held`·`hint`를 그대로 알린다(같은 세션의 이전 wait가 남아 있으면 그 작업을 멈추고 다시 띄운다).

4. **코멘트가 오면** SKILL.md 게이트② 처리 그대로 한다 — 해당 항목의 데이터(`20_draft.md`·`figures/` 명세)만 고치고
   lint·감사를 다시 돌린 뒤 `review_server.py resolve {work_dir} f…`로 '반영됨'을 표시하고 다음 `wait`를 다시 띄운다.
   이 루프 안에서 스크립트·참조 문서는 고치지 않는다. '승인 · 변환'이 오면 게이트② 승인 절차로 넘어간다.

5. 사용자가 "리뷰 닫아줘"라고 하거나 승인으로 끝나면 `review_server.py stop {work_dir}`로 그 건의 리뷰를 닫는다.

진행 보고는 1줄 — "리뷰어 열림: {url} · 코멘트 대기 중".
