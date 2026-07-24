---
name: youtube-music-download
description: 유튜브 영상(들)을 오디오 mp3로 ~/Downloads(또는 --out)에 저장합니다. 재생목록·라디오 파라미터(&list=, start_radio)가 붙은 URL도 개별 영상만 받고, 최고 음질 mp3에 썸네일·메타데이터를 임베드합니다. 사용 시점 — 사용자가 유튜브 링크를 한 개 또는 여러 개 주면서 "노래 다운받아줘", "이 곡 mp3로", "음악 저장", "이거 다운로드해줘"라고 요청할 때. yt-dlp가 403 Forbidden으로 막힐 때 자동으로 최신화 후 재시도하는 경로까지 포함하므로, 유튜브 오디오/음악 다운로드 요청에는 손으로 yt-dlp 명령을 짜지 말고 이 스킬을 쓰세요.
---

# youtube-music-download — 유튜브 음악(오디오) 다운로드

박기린이 자주 쓰는 패턴: 유튜브 링크를 한 개 또는 여러 개 던지면 각각을 mp3로 `~/Downloads`에 받기.
`yt-dlp`를 얇게 감싸되, 손으로 매번 명령을 짤 때 빠지기 쉬운 방어(재생목록 무시, 403 자동 복구)를 스크립트에 박아둔 것이 핵심입니다.

## 언제 쓰나
- 사용자가 유튜브 영상 URL을 주면서 "노래 받아줘", "mp3로 다운로드", "이 곡 저장", "음악 다운" 등을 요청할 때
- 여러 곡 URL을 한꺼번에 받을 때 (한 줄에 하나씩)
- URL에 `&list=...`(재생목록)나 `start_radio=1`(라디오)이 붙어 있어도 그 영상 한 개만 원할 때

## 왜 손으로 yt-dlp를 치지 않는가 (스크립트가 대신 막는 함정)

1. **재생목록 폭주.** 유튜브 링크를 복사하면 보통 `&list=`나 `start_radio`가 딸려온다. 그냥 `yt-dlp <URL>` 하면 재생목록 전체(수십~수백 곡)를 받아버린다. 스크립트는 항상 `--no-playlist`로 그 URL이 가리키는 한 곡만 받는다.
2. **403 Forbidden.** 유튜브는 스트리밍 방식(SABR 등)을 주기적으로 바꾼다. 설치된 yt-dlp가 그보다 오래되면 **모든** 다운로드가 `HTTP Error 403: Forbidden`으로 실패한다. 이게 유튜브 다운로드가 깨지는 가장 흔한 이유다. 스크립트는 403을 감지하면 yt-dlp를 최신 pre-release로 한 번 자동 업데이트하고 같은 명령을 재시도한다.
3. **옵션 누락.** 최고 음질 추출(`--audio-quality 0`), 썸네일·메타데이터 임베드, 재실행 안전(`--no-overwrites`)을 매번 기억에서 재구성하면 하나씩 빠진다. 스크립트가 고정한다.

## 실행 절차

```bash
python3 ./youtube-music-download/scripts/download.py <URL> [<URL> ...] [--out DIR] [--format mp3]
```

옵션
- `<URL> ...` — 영상 URL을 공백으로 여러 개 나열
- `-a, --batch-file FILE` — URL을 한 줄에 하나씩 적은 파일 (곡이 많을 때)
- `--out DIR` (기본 `~/Downloads`) — 저장 폴더
- `--format` (기본 `mp3`) — 오디오 포맷. `m4a` 등 yt-dlp 지원 포맷

### 예시

```bash
# 한 곡
python3 scripts/download.py 'https://www.youtube.com/watch?v=-4vpdkEkup8'

# 여러 곡 한꺼번에 (리스트/라디오 파라미터가 붙어 있어도 개별 영상만 받음)
python3 scripts/download.py \
  'https://www.youtube.com/watch?v=-4vpdkEkup8&list=PLxxxx&index=4' \
  'https://www.youtube.com/watch?v=rXefFHRgyE0'

# 곡이 많으면 URL 파일로
printf '%s\n' 'https://youtu.be/aaa' 'https://youtu.be/bbb' > urls.txt
python3 scripts/download.py -a urls.txt

# 다른 폴더로
python3 scripts/download.py 'https://youtu.be/aaa' --out ~/Music
```

곡 수가 많거나 오래 걸릴 때는 백그라운드(`run_in_background`)로 돌리고, 끝나면 `ffprobe`로 재생시간·용량을 확인해 실제로 받아졌는지 검증한다.

## 검증

받은 뒤에는 개수와 무결성을 확인한다.

```bash
cd ~/Downloads && for f in *.mp3; do
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null)
  printf '%s  %s\n' "$dur" "$f"
done
```

재생시간이 0이거나 파일이 비정상적으로 작으면 그 URL만 다시 받는다.

## 한계

- 이 스크립트로는 오디오만 받는다. 영상(비디오)이 필요하면 yt-dlp를 직접 쓴다.
- 403이 최신화 후에도 반복되면 유튜브가 봇 차단을 강화한 경우다. 이때는 `--cookies-from-browser chrome`로 로그인 쿠키를 붙이거나 `--extractor-args "youtube:player_client=..."`로 다른 클라이언트를 시도해야 한다(스크립트는 여기까지 자동화하지 않고, 반복 403이면 그 안내를 출력한다).
- mp3는 원본(opus/webm)을 재인코딩하므로 미세한 손실이 있다. 무손실에 가깝게 원본 코덱을 유지하려면 `--format m4a`(원본이 aac일 때 유리)를 쓴다.
- 받은 음원의 재배포는 저작권 문제가 있으니 개인 감상 용도로만.

## 의존성

- `yt-dlp` (403 자동 복구를 위해 pip로 설치·업데이트 가능한 상태 권장: `python3 -m pip install -U --pre "yt-dlp[default]"`)
- `ffmpeg` (오디오 추출·변환·썸네일 임베드에 필요)

## 파일

- `scripts/download.py` — 실행 스크립트 본체
