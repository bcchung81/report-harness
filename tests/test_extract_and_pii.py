import sys, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/report-pipeline/scripts"))
sys.path.insert(0, str(ROOT / "scripts"))
from extract_format_profile import render_profile
from pii_scan import scan_dir

def test_render_profile_table():
    spec = {"elements": {"문서 제목": {"font": "HY헤드라인M", "pt": 20}},
            "page": {"여백": "좌20 우20 위10 아래15", "줄간격": "160%"}}
    md = render_profile(spec, source="test.hwp")
    assert "| 문서 제목 | HY헤드라인M | 20pt |" in md and "160%" in md

def test_pii_scan_detects(tmp_path):
    (tmp_path / "a.md").write_text("문의: 061-350-1565 mail@kca.kr")
    hits = scan_dir(tmp_path)
    assert len(hits) == 2

def test_pii_scan_clean(tmp_path):
    (tmp_path / "a.md").write_text("연락처는 마스킹됨 061-***-****")
    assert scan_dir(tmp_path) == []

def test_pii_scan_no_hyphen_phone(tmp_path):
    (tmp_path / "a.md").write_text("연락처 01012345678 / 010 1234 5678 / 010.1234.5678")
    kinds = [h["kind"] for h in scan_dir(tmp_path)]
    assert kinds.count("phone") >= 3

def test_pii_scan_extra_extensions(tmp_path):
    (tmp_path / "a.csv").write_text("name,phone\n김,061-350-1565")
    (tmp_path / "b.jsonl").write_text('{"mail":"x@kca.kr"}')
    (tmp_path / "c.yaml").write_text("tel: 010-1234-5678")
    kinds = {h["kind"] for h in scan_dir(tmp_path)}
    assert kinds == {"phone", "email"}

def test_pii_scan_skips_dependency_trees(tmp_path):
    """gitignore된 의존성·캐시 트리는 배포물이 아니다.

    실사고: docs/survey에 npm install이 들어오자 node_modules의 패키지 메타에서 오탐 40여 건이
    터져 `package_check.sh`가 로컬 상시 exit 1이 됐다(CI는 fresh checkout이라 통과해 더 늦게
    드러난다). 배포 전 가드가 항상 빨간불이면 진짜 PII를 막는 그 한 줄이 무시당한다."""
    dep = tmp_path / "node_modules" / "zod"
    dep.mkdir(parents=True)
    (dep / "package.json").write_text('{"author":"sindresorhus@gmail.com"}')
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "x.py").write_text("tel = '061-350-1565'")
    assert scan_dir(tmp_path) == []
    # 제외 트리 밖의 진짜 유출은 여전히 잡아야 한다
    (tmp_path / "leak.md").write_text("문의: mail@kca.kr")
    assert [h["kind"] for h in scan_dir(tmp_path)] == ["email"]


def test_pii_scan_no_false_positive_on_dates(tmp_path):
    (tmp_path / "a.md").write_text("사업기간 2026.01.13 ~ 2026.12.31, 예산 349,850,000원")
    assert scan_dir(tmp_path) == []


def test_pii_scan_ignores_package_version_pins(tmp_path):
    """`kordoc@4.15.3` 같은 패키지 버전 지정은 이메일이 아니다 — 도메인은 영문 TLD로 끝나야 한다('26.9.25)."""
    (tmp_path / "a.md").write_text("npx -y kordoc@4.15.3 mcp\n", encoding="utf-8")
    assert scan_dir(tmp_path) == []
    (tmp_path / "b.md").write_text("문의: someone@example.co.kr\n", encoding="utf-8")
    assert [h["kind"] for h in scan_dir(tmp_path)] == ["email"]
