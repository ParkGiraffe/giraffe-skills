---
name: rebase-on-main
description: 현재 브랜치를 origin/main 최신 위로 리베이스합니다. 사용자가 "메인 리베이스", "rebase main", "origin main에 맞춰", "/rebase-on-main" 등을 말할 때 사용. main 코드를 진실로 간주해 충돌 시 자동으로 main 쪽을 채택하고(-X ours), 백업 브랜치를 자동 생성하며 force-with-lease만 허용합니다. main/master 브랜치에선 실행을 거부합니다.
user-invocable: true
---

현재 작업 브랜치를 최신 `origin/main` 위로 리베이스합니다.

## 핵심 정책: main 우선

이 스킬의 가장 중요한 원칙입니다.

- **main 코드는 진실(source of truth)** — main이 가진 것을 그대로 따른다.
- **main 코드는 웬만하면 손대지 않는다** — main 자체를 수정해야 하는 상황이면 우선 사용자에게 알리고 승인 받는다.
- **충돌 나면 main 쪽으로 자동 해결** — 매번 사용자에게 물어보지 않는다.
- 그 결과 현재 브랜치 코드가 main에 맞춰 변형되더라도 그것이 정상이다.

이 정책 때문에 기본 명령에 항상 `-X ours` 옵션을 붙입니다.

> **주의(헷갈리는 부분)**: rebase 컨텍스트에서 "ours"는 base(=origin/main)를 의미하고 "theirs"가 우리의 commit입니다. 일반 머지의 ours/theirs와 의미가 정반대입니다. 따라서 main 우선 = `-X ours`.

## 1단계: 사전 점검

다음을 병렬로 실행해 상태를 파악하세요.

```bash
git branch --show-current
git status --porcelain
git fetch origin main
```

판정 규칙:

- 현재 브랜치가 `main` / `master` / `develop` → **즉시 중단**하고 사용자에게 알림.
- 워킹 트리에 변경 있음(`status --porcelain` 출력 비어있지 않음) → 사용자에게 어떻게 처리할지 확인.
  - 옵션 A: `git stash push -m "rebase-on-main"` 후 진행, 끝나고 `git stash pop`
  - 옵션 B: 먼저 커밋하고 진행
  - 옵션 C: 중단
- `git rev-list --count HEAD..origin/main` → 0 이면 리베이스 필요 없음을 알리고 종료.

## 2단계: 백업 브랜치 생성

리베이스는 히스토리를 다시 쓰므로 안전망이 반드시 필요합니다.

```bash
git branch backup/rebase-$(git branch --show-current)-$(date +%Y%m%d-%H%M)
```

백업 브랜치 이름을 사용자에게 알려주세요. 작업 후 본인이 직접 `git branch -d <backup>`으로 정리합니다.

## 3단계: 리베이스 실행 (main 우선 자동 해결)

기본 명령:

```bash
git rebase origin/main -X ours
```

`-X ours` 가 자동으로 처리하는 것:
- 같은 라인을 양쪽에서 변경한 경우 → main 쪽 채택
- 한쪽에서만 변경된 영역 → 정상 머지
- 의미적 모순(예: main에서 함수 시그니처 변경 + 우리 브랜치에서 호출부 추가) → 자동 해결되지만 컴파일 에러를 만들 수 있음

### 성공한 경우

- `git log --oneline origin/main..HEAD` 로 리베이스된 커밋 목록 표시
- `git diff <백업브랜치>..HEAD` 로 main 흡수로 인해 자동 변형된 영역 요약
- 빌드/타입체크가 가능하면 `pnpm build` 또는 `pnpm typecheck` 등을 돌려 main 흡수 결과가 깨지지 않았는지 확인 (불가능하면 사용자에게 검증 요청)

### 정말로 멈춘 경우 (드물지만 가능)

`-X ours` 가 적용되어도 binary/rename/delete 충돌은 자동 해결이 안 될 수 있습니다.

1. `git status` 로 충돌 종류 표시.
2. **사용자에게 보고하고 지시 대기**. 임의로 `--theirs` / `--ours` 강제 적용 금지.
3. 사용자가 해결하면 `git add <files>` → `git rebase --continue`.
4. 포기: `git rebase --abort` (백업 브랜치는 그대로 남음).

### 자동 해결 결과 보고 (필수)

리베이스 후에는 어떤 파일이 main 쪽으로 자동 흡수됐는지 사용자에게 요약해서 보고합니다.

```
main 우선으로 자동 해결된 파일:
- path/to/file.ts (라인 X-Y)
- path/to/other.tsx (라인 Z)
```

사용자가 결과를 검토할 수 있게 합니다.

## 4단계: 푸시 (사용자 승인 필요)

업스트림이 이미 존재하면 force push 가 필요합니다. **반드시 `--force-with-lease`만 사용**합니다.

```bash
git rev-parse --abbrev-ref @{upstream} 2>&1
```

- 업스트림 있음 → `git push --force-with-lease` 제안. 사용자 명시 승인 후 실행.
- 업스트림 없음 → `git push -u origin <current-branch>` 제안.

**금지:**
- `git push --force` (lease 없는 강제 푸시)
- main/master 로의 force push (어떤 옵션이든)
- 사용자 승인 없는 자동 push

## 주의사항

- `git rebase -i`(인터랙티브)는 CLI 환경에서 동작하지 않으므로 사용 금지.
- 다른 사람이 같이 작업 중인 공유 브랜치는 리베이스 대상에서 제외. 사용자에게 확인 후 진행.
- 백업 브랜치는 사용자가 정리하기 전까지 자동 삭제하지 않음.
- 리베이스 도중 헷갈리면 즉시 `git rebase --abort` 후 사용자에게 상황 보고.
- main 자체 파일을 수정해야 하는 상황이 생기면 우선 사용자에게 알리고 승인 받기.

## 출력 형식

작업이 끝나면 다음 정보를 요약해 보고합니다.

```
브랜치: <current-branch>
백업: <backup-branch-name>
리베이스: <성공 | 충돌 해결 후 성공 | 중단>
적용된 커밋: <개수>
main 우선으로 흡수된 파일: <목록 또는 "없음">
다음 단계: <push 제안 또는 작업 완료 안내>
```
