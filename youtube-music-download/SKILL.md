---
name: youtube-music-download
description: 유튜브 영상(들)을 오디오 mp3로 ~/Downloads(또는 --out)에 저장하고, 이어서 앨범커버를 정사각으로 잘라 다시 넣고 곡 정보(제목·아티스트·앨범·발매일·장르)를 태그에 채운 뒤 "아티스트 - 제목.mp3"로 파일명을 정리합니다. 재생목록·라디오 파라미터(&list=, start_radio)가 붙은 URL도 개별 영상만 받습니다. 사용 시점은 사용자가 유튜브 링크를 주면서 "노래 다운받아줘", "이 곡 mp3로", "음악 저장", "이거 다운로드해줘"라고 할 때, 그리고 "앨범커버도 편집해줘", "음악 정보까지", "태그 정리해줘", "저번처럼 해줘"라고 덧붙일 때 반드시 이 스킬을 씁니다. 이미 받아둔 mp3의 커버가 좌우에 검은 띠가 붙어 있거나 태그가 유튜브 영상 제목 그대로일 때 고치는 용도로도 씁니다. yt-dlp가 403 Forbidden으로 막힐 때 자동 최신화 후 재시도하는 경로까지 포함하므로, 유튜브 오디오/음악 다운로드와 태그 정리에는 손으로 yt-dlp나 ffmpeg 명령을 짜지 말고 이 스킬을 쓰세요.
---

# youtube-music-download: 유튜브 음악(오디오) 다운로드

박기린이 자주 쓰는 패턴: 유튜브 링크를 한 개 또는 여러 개 던지면 각각을 mp3로 `~/Downloads`에 받기.
`yt-dlp`를 얇게 감싸되, 손으로 매번 명령을 짤 때 빠지기 쉬운 방어(재생목록 무시, 403 자동 복구)를 스크립트에 박아둔 것이 핵심입니다.

## 언제 쓰나
- 사용자가 유튜브 영상 URL을 주면서 "노래 받아줘", "mp3로 다운로드", "이 곡 저장", "음악 다운" 등을 요청할 때
- 여러 곡 URL을 한꺼번에 받을 때 (한 줄에 하나씩)
- URL에 `&list=...`(재생목록)나 `start_radio=1`(라디오)이 붙어 있어도 그 영상 한 개만 원할 때
- "앨범커버 편집", "음악 정보까지", "태그 정리", "저번처럼"이 붙을 때. 이건 2단계(후처리)까지 하라는 뜻입니다
- 이미 받아둔 mp3의 커버에 검은 띠가 있거나 태그가 유튜브 영상 제목 그대로일 때. 이때는 2단계만 돌립니다

## 왜 손으로 yt-dlp를 치지 않는가 (스크립트가 대신 막는 함정)

1. **재생목록 폭주.** 유튜브 링크를 복사하면 보통 `&list=`나 `start_radio`가 딸려온다. 그냥 `yt-dlp <URL>` 하면 재생목록 전체(수십~수백 곡)를 받아버린다. 스크립트는 항상 `--no-playlist`로 그 URL이 가리키는 한 곡만 받는다.
2. **403 Forbidden.** 유튜브는 스트리밍 방식(SABR 등)을 주기적으로 바꾼다. 설치된 yt-dlp가 그보다 오래되면 **모든** 다운로드가 `HTTP Error 403: Forbidden`으로 실패한다. 이게 유튜브 다운로드가 깨지는 가장 흔한 이유다. 스크립트는 403을 감지하면 yt-dlp를 최신 pre-release로 한 번 자동 업데이트하고 같은 명령을 재시도한다.
3. **옵션 누락.** 최고 음질 추출(`--audio-quality 0`), 썸네일·메타데이터 임베드, 재실행 안전(`--no-overwrites`)을 매번 기억에서 재구성하면 하나씩 빠진다. 스크립트가 고정한다.

## 1단계: 다운로드

```bash
python3 ./youtube-music-download/scripts/download.py <URL> [<URL> ...] [--out DIR] [--format mp3]
```

옵션
- `<URL> ...`: 영상 URL을 공백으로 여러 개 나열
- `-a, --batch-file FILE`: URL을 한 줄에 하나씩 적은 파일 (곡이 많을 때)
- `--out DIR` (기본 `~/Downloads`): 저장 폴더
- `--format` (기본 `mp3`): 오디오 포맷. `m4a` 등 yt-dlp 지원 포맷

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

## 2단계: 앨범커버 편집과 음악 정보 정리

```bash
python3 ./youtube-music-download/scripts/tagfix.py "~/Downloads/Pokémon Movie10 BGM - Oración.mp3" \
  --title "오라시온" \
  --artist "미야자키 신지 (Shinji Miyazaki)" \
  --album-artist "미야자키 신지 (Shinji Miyazaki)" \
  --album "극장판 포켓몬스터 DP: 디아루가 VS 펄기아 VS 다크라이 뮤직 컬렉션" \
  --date "2007-07-25" --genre "OST" --track "20/24" --publisher "미디어팩토리" \
  --clear synopsis --rename
```

위 명령이 커버를 정사각으로 잘라 다시 넣고, 태그를 채우고, 파일명을 `미야자키 신지 - 오라시온.mp3`로 바꿉니다.

### 왜 필요한가

1단계가 넣어 주는 값은 곡 정보가 아니라 유튜브 영상 정보입니다.

- **태그.** 제목에 `Pokémon Movie10 BGM - Oración`, 아티스트에 `PocketMonstersMusic`(채널명)이 들어갑니다. 음악 앱에서 아티스트별·앨범별 정렬이 무너집니다.
- **커버.** 유튜브 썸네일이 그대로 박힙니다. 썸네일은 16:9나 4:3이라 정사각 앨범아트 좌우에 검은 띠가 붙어 있고, 음악 앱의 정사각 아트워크 자리에 그 띠까지 같이 보입니다.
- **오디오는 건드리지 않습니다.** 스크립트는 항상 `-c:a copy`입니다. 태그를 고치려고 mp3를 다시 인코딩하면 음질만 깎입니다.

### 곡 정보 조사 (스크립트가 대신 못 하는 부분)

태그 값은 사람이 조사해서 넘겨야 합니다. 순서는 이렇습니다.

1. 영상 설명란을 먼저 읽습니다. 작곡가·연주자·앨범 정보가 적혀 있는 경우가 많습니다.
   ```bash
   yt-dlp --no-playlist --skip-download --print "%(description)s" "<URL>"
   ```
2. **한국어 정식 표기를 검색으로 확인합니다. 기억으로 음차하면 틀립니다.** 오라시온 건에서 통용 표기인 "파르키아"를 그대로 쓸 뻔했는데 정식 명칭은 "펄기아"였습니다. 나무위키와 위키백과로 교차검증합니다.
3. 앨범명·발매일·레이블·트랙 번호는 앨범 문서에서 확인합니다.

### 태그 컨벤션

기존에 정리해 둔 파일들과 형태를 맞춥니다.

- `--artist`, `--album-artist`: `한글이름 (Romanization)` 형태입니다. `타루 (Taru)`, `윤하 (Younha)`, `미야자키 신지 (Shinji Miyazaki)`
- `--title`: 한국어 곡명만 씁니다
- `--genre`: `OST`, `K-Pop` 같은 짧은 분류
- 파일명은 `--rename`이 `아티스트 - 제목.mp3`로 만듭니다. 괄호 안 로마자는 태그에만 남고 파일명에서는 빠집니다
- `purl`과 `comment`의 유튜브 URL은 출처라서 그대로 둡니다

### 옵션

- `--cover IMG`: 쓸 커버 이미지를 직접 지정합니다. 생략하면 파일에 이미 붙어 있는 커버를 꺼내 씁니다
- `--no-crop`: 정사각 크롭을 생략합니다
- `--rename`: 파일명을 바꿉니다. `--artist`와 `--title`이 둘 다 있어야 동작합니다
- `--clear KEY`: 태그를 비웁니다. yt-dlp가 넣는 `synopsis`, `description`은 유튜브 설명란 첫 줄이라 지저분할 때가 많습니다
- `--dry-run`: 실행할 ffmpeg 명령만 출력하고 파일은 건드리지 않습니다
- 텍스트 태그: `--title --artist --album --album-artist --date --genre --track --disc --composer --publisher --comment --description`

넘긴 태그만 덮어쓰고 나머지는 그대로 둡니다. 나중에 한 항목만 고쳐서 다시 돌려도 됩니다.

### 커버 크롭이 판단하는 방식

정지 이미지 한 장에서는 ffmpeg `cropdetect`가 결과를 내지 않아서, 행·열 평균 밝기를 직접 재서 검은 띠를 찾습니다. 어두운 구간을 무조건 띠로 보면 검은 배경 앨범아트를 잘라먹기 때문에 두 가지를 확인합니다.

- **대칭성.** 레터박스는 양쪽 폭이 같으므로 좌우(상하) 중 좁은 쪽을 띠 폭으로 채택합니다. 한쪽만 어두운 것은 띠가 아니라 그냥 어두운 그림입니다
- **최소 폭.** 변 길이의 2% 미만은 JPEG 압축 흔적으로 보고 무시합니다. 이 방어가 없으면 이미 정사각인 커버가 1픽셀씩 깎이면서 의미 없이 재인코딩됩니다

이미 정사각이고 띠도 없으면 크롭과 재인코딩을 모두 건너뜁니다. 그래서 같은 파일에 여러 번 돌려도 화질이 나빠지지 않습니다.

## 검증

받은 뒤에는 개수와 무결성을 확인한다.

```bash
cd ~/Downloads && for f in *.mp3; do
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null)
  printf '%s  %s\n' "$dur" "$f"
done
```

재생시간이 0이거나 파일이 비정상적으로 작으면 그 URL만 다시 받는다.

2단계를 돌린 뒤에는 `tagfix.py`가 결과 태그와 커버 크기를 다시 읽어서 출력합니다. **그 출력에서 한글 고유명사와 조사가 깨지지 않았는지 눈으로 확인합니다.** 저장 후 다시 읽어 확인하는 절차는 생략하지 않습니다(리포 CLAUDE.md의 한글 입력 하드룰).

## 한계

- 이 스크립트로는 오디오만 받는다. 영상(비디오)이 필요하면 yt-dlp를 직접 쓴다.
- 403이 최신화 후에도 반복되면 유튜브가 봇 차단을 강화한 경우다. 이때는 `--cookies-from-browser chrome`로 로그인 쿠키를 붙이거나 `--extractor-args "youtube:player_client=..."`로 다른 클라이언트를 시도해야 한다(스크립트는 여기까지 자동화하지 않고, 반복 403이면 그 안내를 출력한다).
- mp3는 원본(opus/webm)을 재인코딩하므로 미세한 손실이 있다. 무손실에 가깝게 원본 코덱을 유지하려면 `--format m4a`(원본이 aac일 때 유리)를 쓴다.
- 받은 음원의 재배포는 저작권 문제가 있으니 개인 감상 용도로만.
- `tagfix.py`는 곡 정보를 스스로 찾지 못합니다. 제목·아티스트·앨범은 사람이 조사해서 넘겨야 하고, 스크립트는 그 값을 손실 없이 써 넣는 일만 합니다.
- 커버 화질은 유튜브 썸네일이 상한입니다. 오래된 영상은 `maxresdefault`가 없어 480px가 최대인 경우가 있고, 이때 억지로 업스케일하지 않습니다. 더 좋은 앨범아트가 따로 있으면 `--cover`로 넘깁니다.
- 흰색이나 밝은 배경으로 여백이 채워진 썸네일은 검은 띠 검출에 걸리지 않습니다. 이때는 `--cover`로 직접 자른 이미지를 주면 됩니다.

## 의존성

- `yt-dlp` (403 자동 복구를 위해 pip로 설치·업데이트 가능한 상태 권장: `python3 -m pip install -U --pre "yt-dlp[default]"`)
- `ffmpeg` (오디오 추출·변환·썸네일 임베드에 필요)

## 파일

- `scripts/download.py`: 1단계 다운로드 스크립트
- `scripts/tagfix.py`: 2단계 후처리 스크립트(앨범커버 정사각 크롭, 태그 정리, 파일명 변경)
