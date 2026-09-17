#!/bin/zsh
# 컴퓨터 반납 전에 git에 없는 작업 데이터를 외장 드라이브로 복사한다 (2026-09-17).
#   _lib/backup_claude_to_ssd.sh /Volumes/T7
# 복사 대상: 블로그 초안 폴더, docs/superpowers 설계·계획, 클로드 메모리와 전역 설정,
# 이 리포의 미추적 파일. 세션 기록(jsonl)은 용량이 커서 --sessions 를 줄 때만 복사한다.
set -e
DEST_ROOT="${1:?사용: backup_claude_to_ssd.sh <드라이브 경로> [--sessions]}"
STAMP=$(date +%Y%m%d)
DEST="$DEST_ROOT/claude-backup-$STAMP"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PROJ_KEY="$(echo "$REPO" | sed 's#/#-#g')"
CLAUDE_PROJ="$HOME/.claude/projects/$PROJ_KEY"
mkdir -p "$DEST"
echo "== 대상: $DEST"
rsync -a --exclude '.DS_Store' "$REPO/.claude/blog-corpus/" "$DEST/blog-corpus/"
rsync -a "$REPO/docs/" "$DEST/docs/"
mkdir -p "$DEST/claude-home"
rsync -a "$HOME/.claude/CLAUDE.md" "$DEST/claude-home/CLAUDE.md"
[ -f "$HOME/.claude/settings.json" ] && rsync -a "$HOME/.claude/settings.json" "$DEST/claude-home/settings.json"
[ -f "$HOME/.claude/keybindings.json" ] && rsync -a "$HOME/.claude/keybindings.json" "$DEST/claude-home/keybindings.json"
rsync -a "$CLAUDE_PROJ/memory/" "$DEST/claude-memory/"
git -C "$REPO" ls-files --others --exclude-standard | grep -v '^\.claude/' | while read -r f; do
  mkdir -p "$DEST/repo-untracked/$(dirname "$f")"; cp -R "$REPO/$f" "$DEST/repo-untracked/$f"; done
if [ "$2" = "--sessions" ]; then rsync -a "$CLAUDE_PROJ"/*.jsonl "$DEST/claude-sessions/"; fi
cat > "$DEST/README.md" <<TXT
# 클로드 작업 백업 ($STAMP)

새 컴퓨터에서 되돌리는 순서입니다.
1. 리포를 같은 경로에 받습니다: git clone https://github.com/ParkGiraffe/giraffe-skills.git $REPO
2. blog-corpus/ 를 $REPO/.claude/blog-corpus/ 로, docs/ 를 $REPO/docs/ 로 복사합니다.
3. claude-home/CLAUDE.md 를 ~/.claude/CLAUDE.md 로 복사합니다 (settings, keybindings도 있으면 같이).
4. claude-memory/ 를 ~/.claude/projects/$PROJ_KEY/memory/ 로 복사합니다. 경로 이름은 리포 경로에서 슬래시를 대시로 바꾼 것입니다.
5. repo-untracked/ 는 git에 없던 파일이니 필요한 것만 리포에 되돌립니다.
6. 사진·영상 원본과 편별 계획은 T7의 블로그/닌텐도게임일지/ 아래에 그대로 있습니다.
TXT
du -sh "$DEST"; echo "== 완료"
