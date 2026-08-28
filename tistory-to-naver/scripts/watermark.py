#!/usr/bin/env python3
"""워터마크는 리포 공용 _lib/watermark.py가 정본이다.

여기 따로 두면 두 대의 컴퓨터에서 상수가 갈라진다(실제로 그랬다). 호출부
(migrate_from_url.py)가 `from watermark import add_watermark`로 쓰고 있어
기존 이름만 그대로 넘겨준다.

sys.path에 _lib을 넣고 `import watermark` 하면 이 파일이 자기 자신을 집으므로
(모듈 이름이 같다) 파일 경로로 직접 불러온다.
"""
import importlib.util as _u, os as _os

_REPO = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
_PATH = _os.path.join(_REPO, "_lib", "watermark.py")
_spec = _u.spec_from_file_location("giraffe_lib_watermark", _PATH)
_mod = _u.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

add_watermark = _mod.add_watermark
stamp = _mod.stamp
TEXT = _mod.TEXT
OPACITY = _mod.OPACITY
