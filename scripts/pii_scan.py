"""패키징 PII 가드 (spec §12). 전화·이메일 잔존 시 배포 차단."""
import sys, re, pathlib

PHONE = re.compile(r"(?<!\d)0\d{1,2}[-. ]?\d{3,4}[-. ]?\d{4}(?!\d)")
# 도메인은 영문 최상위 도메인(TLD)으로 끝난다 — 숫자로 끝나는 `패키지@버전`(kordoc@4.15.3)을 이메일로 잡지 않는다('26.9.25)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b")
SCAN_SUFFIXES = {".md", ".json", ".txt", ".py", ".csv", ".jsonl", ".yml", ".yaml"}
# 배포물에 실리지 않는 의존성·캐시 트리는 스캔 대상이 아니다 — npm install 한 번에 패키지
# 메타의 관리자 이메일로 오탐이 수십 건 터지고, 그러면 배포 전 가드가 상시 빨간불이 되어
# 정작 진짜 PII를 막는 그 한 줄이 무시당한다(CI는 fresh checkout이라 뒤늦게 드러난다).
EXCLUDE_DIRS = {"node_modules", ".git", "__pycache__", ".pytest_cache",
                ".next", ".venv", "venv"}

def scan_dir(root, exclude_dirs=EXCLUDE_DIRS):
    hits = []
    root = pathlib.Path(root)
    for p in root.rglob("*"):
        if p.suffix.lower() not in SCAN_SUFFIXES or not p.is_file():
            continue
        if exclude_dirs.intersection(p.relative_to(root).parts[:-1]):
            continue
        t = p.read_text(encoding="utf-8", errors="ignore")
        for rx, kind in ((PHONE, "phone"), (EMAIL, "email")):
            for m in rx.findall(t):
                hits.append({"file": str(p), "kind": kind, "value": m})
    return hits

if __name__ == "__main__":
    hits = scan_dir(sys.argv[1])
    for h in hits:
        print(f"PII {h['kind']}: {h['file']}: {h['value']}")
    sys.exit(1 if hits else 0)
