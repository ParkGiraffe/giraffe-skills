#!/bin/zsh
# 새 맥에서 젤다무쌍 제작·업로드 환경을 점검하고 맞춘다 (2026-09-17).
#   _lib/bootstrap_mac.sh /Volumes/T7 [--check]
# --check 를 주면 설치·복사 없이 점검 결과만 출력한다.
# --check 에서도 6번은 /tmp/zelda_ep01_preview.html을 실제로 쓰고, 4번은 크롬을 띄울 수 있다.
set -u
T7="${1:?사용: bootstrap_mac.sh <T7 경로> [--check]}"; CHECK="${2:-}"
ENV_ROOT="$T7/블로그/_환경"; SERIES="$T7/블로그/닌텐도게임일지/젤다무쌍"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
ok() { echo "  [OK] $1"; }; bad() { echo "  [해야 함] $1"; FAIL=1; }
same_tree() {  # 백업($1)과 현재($2)가 같은지. 파일 이름은 NFC로 정규화하고 AppleDouble(._*)·.DS_Store는 뺀다. 단일 파일도 받는다
  python3 - "$1" "$2" <<'PY'
import sys, pathlib, unicodedata, filecmp
a, b = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
if a.is_file() or b.is_file():
    sys.exit(0 if a.is_file() and b.is_file() and filecmp.cmp(a, b, shallow=False) else 1)
def files(root):
    return {unicodedata.normalize("NFC", str(p.relative_to(root))): p
            for p in root.rglob("*") if p.is_file() and not p.name.startswith("._") and p.name != ".DS_Store"}
fa, fb = files(a), files(b)
sys.exit(0 if set(fa) == set(fb) and all(filecmp.cmp(fa[k], fb[k], shallow=False) for k in fa) else 1)
PY
}
FAIL=0
echo "== 1. Homebrew"
if command -v brew >/dev/null; then ok "brew $(brew --version | head -1)"; else bad "Homebrew 없음. https://brew.sh 안내대로 설치 후 다시 실행"; exit 1; fi
echo "== 2. ffmpeg, python3, Pillow, pyobjc"
for t in ffmpeg ffprobe python3; do
  if command -v $t >/dev/null; then ok "$t"; else
    if [ "$CHECK" = "--check" ]; then bad "$t 없음 (brew install ${t/ffprobe/ffmpeg})"; else brew install "${t/ffprobe/ffmpeg}" && ok "$t 설치" || bad "$t 설치 실패"; fi; fi
done
if python3 -c "import PIL" 2>/dev/null; then ok "Pillow"; else
  if [ "$CHECK" = "--check" ]; then bad "Pillow 없음 (python3 -m pip install --user pillow)"; else python3 -m pip install --user pillow && ok "Pillow 설치" || bad "Pillow 설치 실패"; fi; fi
if python3 -c "import AppKit, Quartz" 2>/dev/null; then ok "pyobjc"; else
  if [ "$CHECK" = "--check" ]; then bad "pyobjc 없음 (python3 -m pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz)"; else python3 -m pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz && ok "pyobjc 설치" || bad "pyobjc 설치 실패"; fi; fi
echo "== 3. 워터마크 폰트"
if [ -f "$HOME/Library/Fonts/BMDOHYEON_otf.otf" ]; then ok "도현체 있음"; else
  if [ -f "$ENV_ROOT/fonts/BMDOHYEON_otf.otf" ]; then
    if [ "$CHECK" = "--check" ]; then bad "도현체 없음 (_환경/fonts 에서 복사 예정)"; else cp "$ENV_ROOT/fonts/BMDOHYEON_otf.otf" "$HOME/Library/Fonts/" && ok "도현체 복사"; fi
  else bad "도현체가 맥에도 T7 _환경/fonts 에도 없음"; fi; fi
echo "== 4. 크롬 AppleScript JS, 손쉬운 사용"
if osascript -e 'tell application "Google Chrome" to execute front window'"'"'s active tab javascript "1+1"' >/dev/null 2>&1; then ok "크롬 JS 실행 허용"; else bad "크롬 실행 후 보기 > 개발자 > Apple Events의 JavaScript 허용 을 켤 것"; fi
if osascript -e 'tell application "System Events" to get name of first application process whose frontmost is true' >/dev/null 2>&1; then ok "System Events 접근 가능"; else bad "시스템 설정 > 개인정보 보호 및 보안 > 손쉬운 사용 에서 터미널(또는 실행 앱) 허용"; fi
echo "== 5. 클로드 메모리·전역 설정 복원"
LATEST=$( { ls -d "$ENV_ROOT"/claude/claude-backup-* ; } 2>/dev/null | sort | tail -1)
PROJ_KEY="$(echo "$REPO" | sed 's#/#-#g')"; MEM="$HOME/.claude/projects/$PROJ_KEY/memory"
if [ -z "$LATEST" ]; then bad "백업 없음 ($ENV_ROOT/claude)"; else
  ok "백업 $LATEST"
  for pair in "claude-home/CLAUDE.md:$HOME/.claude/CLAUDE.md" "claude-memory:$MEM"; do
    src="$LATEST/${pair%%:*}"; dst="${pair##*:}"
    if [ -e "$dst" ]; then
      if same_tree "$src" "$dst"; then ok "$dst 동일"; else bad "$dst 이미 있고 백업과 다름. 손으로 비교할 것: diff -r -x '._*' -x .DS_Store \"$src\" \"$dst\""; fi
    else
      if [ "$CHECK" = "--check" ]; then bad "$dst 없음 (복원 예정)"; else mkdir -p "$(dirname "$dst")" && cp -R "$src" "$dst" && ok "$dst 복원"; fi
    fi
  done
fi
echo "== 6. 1편 초안 미리보기 렌더"
D="$SERIES/10_편별/01 1-1 시작의 대지로/초안"
if [ -f "$D/script.md" ]; then
  if python3 "$REPO/blog/scripts/md_to_smarteditor.py" "$D/script.md" "/tmp/zelda_ep01_preview.html" --images "$D/images" >/dev/null 2>&1; then
    n=$(grep -c "se-component se-image" /tmp/zelda_ep01_preview.html || true)
    m=$(python3 -c "import json, sys; print(json.load(open(sys.argv[1]))['images']['count'])" "$D/meta.json")
    if [ "$n" = "$m" ]; then ok "사진 ${n}장 (meta와 일치)"; else bad "사진 수 불일치: 미리보기 $n, meta $m"; fi
  else
    bad "미리보기 렌더 실패 (md_to_smarteditor.py가 이모지 등으로 중단됐을 수 있음)"
  fi
  meta_ok=$(python3 -c "import json, sys
d = json.load(open(sys.argv[1]))
print(d['images']['source_folder'] == 'images' and d['videos_folder'] == '.')" "$D/meta.json")
  if [ "$meta_ok" = "True" ]; then ok "meta 상대 경로 계약 (source_folder=images, videos_folder=.)"; else bad "meta 상대 경로 계약 어긋남: $D/meta.json"; fi
else bad "1편 초안 없음: $D"; fi
echo; [ "$FAIL" = 0 ] && echo "모두 준비됨. 크롬에서 네이버에 로그인하면 업로드할 수 있습니다." || echo "위 [해야 함] 항목을 처리한 뒤 다시 실행하세요."
exit "$FAIL"
