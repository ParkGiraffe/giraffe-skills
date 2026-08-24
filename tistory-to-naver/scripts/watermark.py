#!/usr/bin/env python3
"""사진 우측 하단에 blog.naver.com/op5321 워터마크를 넣는다.

스타일 정본(2026-08-20, 네이버 수기 발행본 w966 픽셀 실측 + 사용자 피드백):
  - 반투명 검정 바(우측·하단 모서리에 딱 붙음) + 흰색 배달의민족 도현체
  - 실물: 바 높이 = 폭의 4.0%, 글자 높이 = 폭의 3.4%, 즉 글자가 바에 거의 꽉 참
    (상하 여백 3px@966). 여백을 크게 잡으면 안 된다 — 사용자가 바로 지적함.
  - 크기는 실물보다 작게(글자 높이 = 폭의 2.57%, 2026-08-20 확정), 불투명도 150.
    "뒤에 비쳐도 되니까 검게 하지 말 것"이 사용자 지시. 티스토리 옛 워터마크가
    비쳐 보이는 것은 감수한다.

GIF(애니메이션)는 건드리면 프레임이 깨지므로 건너뛴다.
"""
import os
from PIL import Image, ImageDraw, ImageFont

FONT = os.path.expanduser("~/Library/Fonts/BM_Dohyeon.otf")
TEXT = "blog.naver.com/op5321"
OPACITY = 150


def add_watermark(path, text=TEXT, opacity=OPACITY):
    """파일을 제자리에서 워터마크 처리. GIF/미지원 포맷은 그대로 둔다.
    성공 True, 건너뜀/실패 False."""
    try:
        im = Image.open(path)
        if (im.format == "GIF") or getattr(im, "is_animated", False):
            return False
        im = im.convert("RGB")
        W, H = im.size
        font_px = max(16, int(W * 0.0257))
        font = ImageFont.truetype(FONT, font_px)
        d0 = ImageDraw.Draw(im)
        x0, y0, x1, y1 = d0.textbbox((0, 0), text, font=font)
        tw, th = x1 - x0, y1 - y0
        pad_x = max(3, int(font_px * 0.14))
        pad_y = max(2, int(font_px * 0.09))
        bar_w, bar_h = tw + pad_x * 2, th + pad_y * 2

        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        bx0, by0 = W - bar_w, H - bar_h
        d.rectangle([bx0, by0, W, H], fill=(20, 20, 20, opacity))
        d.text((bx0 + pad_x - x0, by0 + pad_y - y0), text, font=font,
               fill=(255, 255, 255, 255))
        out = Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")
        out.save(path, quality=92)
        return True
    except Exception as e:
        print(f"[watermark] 실패({os.path.basename(path)}): {e}")
        return False
