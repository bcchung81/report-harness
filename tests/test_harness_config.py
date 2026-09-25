import json, sys, pathlib, datetime
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import harness_config as hc

def test_defaults_without_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = hc.load_config(path=tmp_path / "nope.json")
    assert cfg["reports_dir"] == pathlib.Path.cwd() / "reports"
    assert cfg["state_dir"] == pathlib.Path.cwd() / ".report-harness"
    assert cfg["knowledge_vault"] is None and cfg["template_hwpx"] is None
    assert cfg["assets_dir"].name == "assets"

def test_config_file_overrides(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"reports_dir": str(tmp_path / "R"), "knowledge_vault": str(tmp_path / "V")}))
    cfg = hc.load_config(path=p)
    assert cfg["reports_dir"] == tmp_path / "R"
    assert cfg["knowledge_vault"] == tmp_path / "V"

def test_work_dir_convention(tmp_path):
    cfg = {"reports_dir": tmp_path}
    now = datetime.datetime(2026, 7, 22, 14, 5)
    d = hc.work_dir(cfg, "예시-건명", now=now)
    assert d == tmp_path / "20260722" / "1405_예시-건명"
    assert d.is_dir()

def test_state_paths_created(tmp_path):
    cfg = {"state_dir": tmp_path / "st"}
    sp = hc.state_paths(cfg)
    assert sp["rules"] == tmp_path / "st" / "rules.md"
    assert sp["lessons"] == tmp_path / "st" / "lessons.jsonl"
    assert (tmp_path / "st").is_dir()

def test_explicit_null_falls_back_to_default(tmp_path):
    p = tmp_path / "c.json"
    p.write_text('{"knowledge_vault": null, "reports_dir": null}')
    cfg = hc.load_config(path=p)
    assert cfg["knowledge_vault"] is None
    assert cfg["reports_dir"] == pathlib.Path.cwd() / "reports"


def test_config_path_env_isolates_trial_runs(tmp_path, monkeypatch):
    """REPORT_HARNESS_CONFIG로 설정 파일을 바꾼다 — 시험 실행·평가가 운영 산출 폴더를 건드리지 않게('26.9.25).
    없는 경로면 설정 없이 cwd 기준 기본값으로 돈다."""
    import json
    cfg = tmp_path / "trial.json"
    cfg.write_text(json.dumps({"reports_dir": str(tmp_path / "trial-reports")}), encoding="utf-8")
    monkeypatch.setenv("REPORT_HARNESS_CONFIG", str(cfg))
    assert hc.load_config()["reports_dir"] == tmp_path / "trial-reports"
    monkeypatch.setenv("REPORT_HARNESS_CONFIG", str(tmp_path / "없음.json"))
    monkeypatch.chdir(tmp_path)
    assert hc.load_config()["reports_dir"] == tmp_path / "reports"
