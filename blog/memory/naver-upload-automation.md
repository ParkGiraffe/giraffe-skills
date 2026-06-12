---
name: naver-upload-automation
description: "네이버 블로그 자동 업로드 osascript 함정 — 탭은 고정 id 문자열 비교로 참조, input_buffer iframe 포커스는 정상 신호"
metadata: 
  node_type: memory
  type: project
  originSessionId: f3342fce-1690-4976-9d02-df034c4a4289
---

데브로그 블로그 업로드(giraffe-skills blog 스킬 + paste_to_naver.py + inject_code_blocks.py) 시 검증된 사실 (2026-06-12, 1편 업로드로 실증):

- **AppleScript 탭 인덱스는 신뢰 불가.** 창을 앞으로 올릴 때마다 창/탭 번호가 밀린다. 반드시 탭 id로 참조하되, id가 AppleScript 정수 한계(2^29)를 넘으므로 `((id of t) as string) is "..."` 문자열 비교로.
- **postwrite 탭이 2개면 좌표 계산과 클릭이 서로 다른 창에 떨어진다.** 시작 전 중복 postwrite 탭을 닫아 1개로 만들 것.
- **activeElement가 IFRAME(id=input_buffer...)이면 에디터 포커스 성공 신호다.** SmartEditor의 숨은 입력 버퍼라 실패로 오판하지 말 것.
- 절차: 중복 탭 정리 → 탭 id로 활성화+전면 → 본문 좌표 JS 계산 → CGEvent 클릭 → 포커스 검증(inBody 또는 input_buffer) → paste_to_naver.py → inject_code_blocks.py(사이드카 /tmp/naver_code_blocks.json) → 제목 pbcopy+클릭+Cmd+V → JS로 최종 검증(코드 컴포넌트 수·placeholder 잔존 0·제목).
- 드래프트의 펜스 코드블록은 paste_to_naver.py가 못 다루므로, 업로드 직전 [[CODE-n]] placeholder로 치환한 paste/ 파생본과 사이드카 JSON을 생성하는 전처리가 필요 (드래프트 폴더에 code_blocks_NN.json으로 보관, 업로드 시 /tmp로 복사).

관련: [[blog-conversion-register]]
