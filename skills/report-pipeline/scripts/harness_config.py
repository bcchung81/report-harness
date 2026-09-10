"""설정 로드·작업폴더 규약 (spec §2·§3). stdlib-only.

기본값은 전부 실행위치(cwd) 기준 — 설정 파일(~/.claude/report-harness.json)이 없는
배포 환경(웹앱 등 홈 디렉토리가 휘발성인 곳)에서도 산출물·복리 state가 프로젝트
폴더와 함께 남도록 한다. 로컬 사용자는 설정 파일로 절대경로를 주입해 오버라이드한다.
"""
import json, pathlib, datetime

DEFAULT_CONFIG_PATH = pathlib.Path.home() / ".claude" / "report-harness.json"
ASSETS_DIR = pathlib.Path(__file__).resolve().parent.parent / "assets"

def load_config(path=None):
    path = pathlib.Path(path) if path else DEFAULT_CONFIG_PATH
    raw = {}
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
    def p(key, default):
        val = raw.get(key)
        return pathlib.Path(val).expanduser() if val is not None else default
    return {
        "reports_dir": p("reports_dir", pathlib.Path.cwd() / "reports"),
        # 홈이 아니라 실행위치 폴백 — 웹앱 등 휘발성 홈 환경에서 rules/lessons 복리 보존
        "state_dir": p("state_dir", pathlib.Path.cwd() / ".report-harness"),
        "knowledge_vault": p("knowledge_vault", None),
        "template_hwpx": p("template_hwpx", None),
        # 번들 자산(양식 원본·도식 Pool 경량 사본) — 설정 무관, 스킬 상대 경로 고정
        "assets_dir": ASSETS_DIR,
    }

def work_dir(config, slug, now=None):
    now = now or datetime.datetime.now()
    d = pathlib.Path(config["reports_dir"]) / now.strftime("%Y%m%d") / f"{now.strftime('%H%M')}_{slug}"
    d.mkdir(parents=True, exist_ok=True)
    return d

def history_paths(work_dir):
    """건별 이력 폴더 규약 (R086) — 현행 산출물과 절대 겹치지 않는 자리.

    `history/drafts/`는 아직 변환되지 않은 초안 스냅샷, `history/rNN_{시각}/`은 그 판본
    인도본을 만든 변환 세트다. 인도본 hwpx는 `final/`에 `rNN_YYYYMMDD_` 접두어로 쌓이므로
    이력 폴더로 복사하지 않는다(중복). 조작은 `archive_revision.py`가 맡는다.
    """
    wd = pathlib.Path(work_dir)
    h = wd / "history"
    return {"history": h, "drafts": h / "drafts", "index": h / "index.jsonl",
            "final": wd / "final"}


def state_paths(config):
    sd = pathlib.Path(config["state_dir"])
    sd.mkdir(parents=True, exist_ok=True)
    return {"rules": sd / "rules.md", "lessons": sd / "lessons.jsonl", "state_dir": sd}

if __name__ == "__main__":
    cfg = load_config()
    print(json.dumps({k: str(v) if v else None for k, v in cfg.items()}, ensure_ascii=False, indent=2))
