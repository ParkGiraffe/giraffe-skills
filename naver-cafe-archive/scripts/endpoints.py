#!/usr/bin/env python3
"""네이버 카페 내부 API 엔드포인트 모음 (2026-06 런타임 디스커버리로 확인).

모든 호출은 chrome_bridge.ChromeBridge 를 통해 로그인된 Chrome 페이지
컨텍스트에서 실행한다(세션 쿠키 + 올바른 origin/referer 자동 첨부).

CORS 메모:
  - apis.naver.com/cafe-home-web/*, /cafe-web/*  → *.naver.com origin 허용
  - article.cafe.naver.com/gw/*                  → cafe.naver.com origin에서 호출 확인
  브리지는 cafe.naver.com / section.cafe.naver.com 탭을 origin으로 쓰므로 둘 다 통과.
"""

# --- 본인 식별 ---
MEMBER_IDENTIFIER = "https://apis.naver.com/cafe-home-web/cafe-home/v1/member/identifier"

# --- 카페 목록 (페이지네이션: ?page=N) ---
# 가입 카페: result.groups[].cafes[] = {memberKey, cafeName, cafeId, cafeUrl, memberNickname, favoriteCafe, managingCafe, ...}
JOIN_CAFES = "https://apis.naver.com/cafe-home-web/cafe-home/v1/config/join-cafes/groups/?page={page}"
# 탈퇴 카페: result.cafes[] = {cafeId, cafeName, cafeUrl, cafeOpenType(O/C), secedeDate}
SECEDE_CAFES = "https://apis.naver.com/cafe-home-web/cafe-home/v1/secede-cafes?page={page}"

# --- S1: 가입 카페에서 내가 쓴 글 (멤버 네트워크 글 목록) ---
# result.articleList[] = {clubid, articleid, menuid, subject, writernickname, writedt,
#                         writeDateTimestamp, commentcount, readcount, openyn, ...}
# result.totalCount = 전체 개수 (page * perPage > totalCount 이면 종료)
S1_MEMBER_ARTICLES = (
    "https://apis.naver.com/cafe-web/cafe-mobile/CafeMemberNetworkArticleListV3"
    "?search.cafeId={cafe_id}&search.memberKey={member_key}"
    "&search.perPage={per_page}&search.page={page}&requestFrom=A")

# --- S3: 탈퇴 카페에서 내가 쓴 글 (작성글 관리) ---
# result.articles[] = {articleId, subject, writerId, writeDate, deletable, ...}
# result.pageInfo = {page, perPage, totalCount, lastPage}
S3_SECEDE_ARTICLES = (
    "https://apis.naver.com/cafe-home-web/cafe-home/v1/secede-cafes/{cafe_id}/articles?page={page}")

# --- 본문 (article.cafe.naver.com) ---
# result.article = {subject, contentHtml, writeDate, writer{...}, readCount, commentCount, menu{name}}
#   → 멤버이고 읽기권한 있으면 contentHtml 채워짐.
# 탈퇴/비공개 글은 다른 축약 응답: result = {subject, summary, writeDate, open, searchOpen,
#   tobeReadable, cafeJoinApplyWait, customElements, ...} → contentHtml 없음(요약만). 재가입 필요.
ARTICLE_CONTENT = (
    "https://article.cafe.naver.com/gw/v4/cafes/{cafe_id}/articles/{article_id}"
    "?query=&menuId={menu_id}&useCafeId=true&requestFrom=A")

# --- 댓글 (필요 시) ---
ARTICLE_COMMENTS = (
    "https://article.cafe.naver.com/gw/v4/cafes/{cafe_id}/articles/{article_id}"
    "/comments/pages/{page}?requestFrom=A&orderBy=asc")

# 사람이 보는 글 URL
def article_web_url(cafe_url: str, article_id) -> str:
    return f"https://cafe.naver.com/{cafe_url}/{article_id}"
