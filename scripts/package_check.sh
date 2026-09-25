#!/bin/bash
# 패키징 가드: 배포 제외 확인 + PII 스캔 (spec §12)
set -e
# report/는 기관 내부 산출물이라 가장 민감하다 — gitignore 한 줄이 지워져도 여기서 잡는다
# 기관 양식 원본(경영관리 프레임워크)·디자인 시안(prototype)도 같은 취급 — 런타임은 원본을 읽지 않고 파생 패턴만 쓴다
for banned in "form" "docs/analysis" "report" "skills/report-pipeline/assets/경영관리프레임워크" "prototype"; do
  # core.quotepath=false: 한글 경로가 8진 이스케이프로 출력되어 grep이 놓치는 것 방지
  if git -c core.quotepath=false ls-files | grep -q "^$banned/"; then echo "FATAL: $banned 이 추적됨 — 배포 금지 대상"; exit 1; fi
done
# tests/는 PII 탐지 픽스처(가짜 연락처)가 있어 제외 — 배포·공개 문서 계층 전부를 훑는다
for dir in skills commands webapp hooks scripts docs; do
  python3 scripts/pii_scan.py "$dir/"
done
# 버전 가드(경고) — 설치본은 버전으로 갱신을 판단한다. 배포 저장소와 내용이 다른데 버전이 같으면 설치자의
# `claude plugin update`가 'already at the latest version'으로 새 커밋을 받지 않는다('26.9.25 격리 설치 재현).
# 배포 원격 참조(deploy/main)가 있는 개발 노트북에서만 본다 — CI(새 클론)에는 없어 건너뛴다.
if git rev-parse -q --verify refs/remotes/deploy/main >/dev/null; then
  ver() { git show "$1:.claude-plugin/plugin.json" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['version'])"; }
  if ! git diff --quiet refs/remotes/deploy/main HEAD -- skills commands hooks .mcp.json .claude-plugin \
     && [ "$(ver refs/remotes/deploy/main)" = "$(ver HEAD)" ]; then
    echo "WARN: 배포 저장소와 플러그인 내용이 다른데 버전이 같다($(ver HEAD)) — 올리지 않으면 설치자가 갱신을 받지 못한다"
  fi
fi
echo "package check OK"
