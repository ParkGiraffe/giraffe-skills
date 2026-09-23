---
name: pr-title
description: Use when writing Pull Request titles or commit messages to follow the Korean action word convention.
---

# PR Title and Commit Message Guide

PR 제목이나 커밋 메시지를 작성할 때 이 스킬을 사용한다.

## Basic Format

```
{대상} {액션}
```

- **대상**: 변경 대상 (파일, 모듈, 기능, 라이브러리 등)
- **액션**: 수행한 변경 유형

## Subject Naming Rules

변경 대상에 따라 적절한 이름을 선택한다:

| 대상 유형 | 예시 | 설명 |
|----------|------|------|
| 설정 파일 | TSConfig, ESLint, MikroORM | 도구의 공식/관용 이름 사용 |
| 모듈 | JwtModule, CacheModule, UsersController | 클래스/모듈 이름 사용 |
| 기능 | CI, E2E 테스트, Git Hooks | 기능 이름 사용 |
| 라이브러리 | Lodash, Vitest, Turborepo | 라이브러리 이름 사용 |
| 도메인 | 사용자, 인증, OTP | 한국어 도메인 용어 사용 |

### Examples
- `tsconfig.ts` → **TSConfig**
- `eslint.config.mjs` → **ESLint**
- `mikro-orm.config.ts` → **MikroORM**
- `users.service.ts` → **사용자** 또는 **UsersService**

## Action Types

| 액션 | 용도 | 예시 |
|------|------|------|
| 설정 | 초기 설정 또는 구성 | `JwtModule 설정` |
| 변경 | 기존 설정 수정 | `TSConfig 변경` |
| 수정 | 이슈 또는 에러 수정 | `ESLint 에러 수정` |
| 추가 | 새 기능 추가 | `UsersController 테스트 추가` |
| 적용 | 새 도구/패턴 적용 | `Turborepo 적용` |
| 구축 | 인프라 구축 | `CI 구축` |
| 교체 | 대안으로 교체 | `Lodash를 es-toolkit으로 교체` |
| 마이그레이션 | 새 도구로 전환 | `Jest에서 Vitest로 마이그레이션` |
| 표준화 | 패턴 표준화 | `응답 변환 방식 표준화` |
| 보강 | 기존 기능 강화 | `사용자 수정 테스트 보강` |
| 향상 | 품질 개선 | `pre-push 로그 가독성 향상` |
| 제외 | 규칙에서 제외 | `fixup 커밋 제목 길이 제한 제외` |
| 정의 | 규칙/스펙 정의 | `Cursor 규칙 정의` |

## Good Examples

```
✅ TSConfig 경로 별칭 설정
✅ mise 환경 변수 설정
✅ ESLint 설정 수정
✅ JWT 환경 변수 이름 오타 수정
✅ Jest에서 Vitest로 마이그레이션
✅ Lodash를 es-toolkit으로 교체
✅ 사용자 수정 테스트 보강
✅ pre-push 로그 가독성 향상
```

## Bad Examples

```
❌ 설정 파일 수정 (모호함 - 어떤 설정?)
❌ 버그 수정 (모호함 - 어떤 버그?)
❌ 테스트 추가 (모호함 - 어떤 테스트?)
❌ Web 앱 TSConfig 설정 (불필요한 컨텍스트 - Vite가 Web을 내포)
```

## Tips

1. **구체적으로**: 대상을 명확히 식별할 수 있어야 한다
2. **공식 이름 사용**: TSConfig (tsconfig가 아닌), ESLint (eslint가 아닌)
3. **중복 회피**: 추론 가능한 컨텍스트를 반복하지 않는다
4. **간결하게**: 한눈에 파악할 수 있어야 한다
5. **액션은 한국어로**: 설정, 수정, 추가 등

## Commit Message vs PR Title

- **커밋 메시지**: 더 세분화 가능, PR당 여러 개
- **PR 제목**: 전체 변경을 한 줄로 요약
