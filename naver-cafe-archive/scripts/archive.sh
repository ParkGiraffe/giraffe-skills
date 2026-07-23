#!/usr/bin/env bash
# 네이버 카페 옛 글 전수 아카이브 원샷 오케스트레이터.
# 로그인된 Chrome + "Apple 이벤트의 JavaScript 허용" 토글 ON 전제.
#
# 사용:
#   archive.sh [corpus_dir] [--refresh]
# 기본 corpus_dir = ./.claude/cafe-corpus
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CORPUS="${1:-./.claude/cafe-corpus}"
REFRESH=""
for a in "$@"; do [ "$a" = "--refresh" ] && REFRESH="--refresh"; done

echo "[1/4] 카페 전수 목록 (discover.py)"
caffeinate -dimsu python3 -u "$HERE/discover.py" "$CORPUS"
echo "[2/4] 카페별 글 목록 다중소스 수집 (collect.py)"
caffeinate -dimsu python3 -u "$HERE/collect.py" "$CORPUS"
echo "[3/4] 본문 아카이브 (content.py) $REFRESH"
caffeinate -dimsu python3 -u "$HERE/content.py" "$CORPUS" $REFRESH
echo "[4/4] 리포트 (generate_report.py)"
python3 "$HERE/generate_report.py" "$CORPUS"
echo "완료. $CORPUS/report.md 확인."
