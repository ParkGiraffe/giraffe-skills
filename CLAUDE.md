# CLAUDE.md — 스킬 작성 가이드

이 리포는 박기린(op5321)의 개인 Claude Code 스킬 모음입니다.
**새 스킬을 추가하거나 기존 스킬을 수정할 때는 아래 스킬 작성 도구를 거쳐서 작성**하세요.
스킬 도구 없이 임의로 짜지 말 것.

## 사용할 도구 (우선순위)

1. `/oh-my-claudecode:skillify` — 현재 세션의 반복 워크플로를 스킬 초안으로 추출
2. `/oh-my-claudecode:skill` — 로컬 스킬 추가·삭제·검색·수정 위저드
3. `skill-creator` (Anthropic 공식) — 처음부터 만들거나 description 최적화
4. `superpowers:writing-skills` — 작성·검증 일반 프로세스

이유: frontmatter 규칙·trigger description·디렉토리 구조를 도구가 강제하므로,
"trigger 약한 스킬", "scripts 없는 반쪽 스킬" 같은 실수를 방지.

## 하드룰

- 이모지 금지 — 모든 산출물에 한 글자도 쓰지 않음
- 고유명사 왜곡 금지 — 행사명·브랜드명 임의 변형 금지
- 한국어 톤 — SKILL.md 본문도 한국어 우선
- 코퍼스 의존 스킬은 부재 시 `/blog-learn` 친절 안내
