#!/bin/bash
# usage: verify.sh <tistory_id> <logNo> <img_count>
N=$1; L=$2; IMG=$3
H=$(curl -sSL "https://arnopark.tistory.com/$N")
T=$(echo "$H" | grep -oE '<meta property="og:title" content="[^"]*"' | head -1 | sed 's/.*content="//;s/"$//')
echo "id=$N | $T"
printf "  blockquote=%s h2=%s  " "$(echo "$H" | grep -c '<blockquote')" "$(echo "$H" | grep -o '<h2' | wc -l | tr -d ' ')"
for pat in "m.blog.naver.com/op5321/$L" "blog.naver.com/op5321/$L" "PostView.naver?blogId=op5321&amp;logNo=$L" "이미지 ${IMG}장"; do
  echo "$H" | grep -q "$pat" && printf "OK " || printf "MISSING[%s] " "$pat"
done
echo "$H" | grep -q "정리본" && printf "정리본OK " || printf "정리본MISSING "
echo "$H" | grep -qE "안녕하세요|마이그레이션한 글입니다|원본 작성일" && printf "!!금지문구있음 " || printf "금지문구없음 "
echo "$H" | grep -q "�" && printf "!!손상 " || printf "손상없음"
echo
