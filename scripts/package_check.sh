#!/bin/bash
# 패키징 가드: 배포 제외 확인 + PII 스캔 (spec §12)
set -e
# report/는 기관 내부 산출물이라 가장 민감하다 — gitignore 한 줄이 지워져도 여기서 잡는다
for banned in "form" "docs/analysis" "report"; do
  # core.quotepath=false: 한글 경로가 8진 이스케이프로 출력되어 grep이 놓치는 것 방지
  if git -c core.quotepath=false ls-files | grep -q "^$banned/"; then echo "FATAL: $banned 이 추적됨 — 배포 금지 대상"; exit 1; fi
done
# tests/는 PII 탐지 픽스처(가짜 연락처)가 있어 제외 — 배포·공개 문서 계층 전부를 훑는다
for dir in skills commands webapp hooks scripts docs; do
  python3 scripts/pii_scan.py "$dir/"
done
echo "package check OK"
