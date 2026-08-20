"""Root-only filename whitelist for .myrmtheme archives.

[INPUT]
(none — 纯工具函数)

[OUTPUT]
is_allowed_package_entry(name) -> bool
is_image_entry / is_motion_entry / is_valid_mp4 / is_animated_image 等判断函数

[POS]
白名单校验 .myrmtheme ZIP 条目名：仅允许 recipe.json + README + LICENSE + 特定媒体文件名，
禁止子目录/路径遍历；附带 MP4/APNG/AWEBP 动画格式探测。
"""

from __future__ import annotations

import re

_PACKAGE_ENTRY_RE = re.compile(
    r"^(?:recipe\.json|README\.md|LICENSE|"
    r"(?:hero|poster|preview|background|wallpaper|motion-poster|motion)"
    r"\.(?:png|jpe?g|webp|mp4))$",
    re.IGNORECASE,
)

_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
_MOTION_SUFFIXES = (".mp4",)


def is_unsafe_entry_path(name: str) -> bool:
    normalized = name.replace("\\", "/").strip()
    if not normalized or normalized != name.strip():
        return True
    if "/" in normalized or ".." in normalized.split("/"):
        return True
    return normalized.startswith("~")


def is_allowed_package_entry(name: str) -> bool:
    if is_unsafe_entry_path(name):
        return False
    return _PACKAGE_ENTRY_RE.match(name) is not None


def is_image_entry(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(_IMAGE_SUFFIXES)


def is_motion_entry(name: str) -> bool:
    return name.lower().endswith(_MOTION_SUFFIXES)


def is_valid_mp4(content: bytes) -> bool:
    return len(content) >= 12 and content[4:8] == b"ftyp"


def is_animated_png(content: bytes) -> bool:
    signature = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
    if len(content) < 8 or content[:8] != signature:
        return False
    offset = 8
    while offset + 8 <= len(content):
        length = int.from_bytes(content[offset : offset + 4], "big")
        chunk_type = content[offset + 4 : offset + 8]
        if chunk_type == b"acTL":
            return True
        if chunk_type in (b"IDAT", b"IEND"):
            return False
        if length < 4:
            break
        offset += 12 + length
    return False


def is_animated_webp(content: bytes) -> bool:
    if len(content) < 21:
        return False
    if content[0:4] != b"RIFF" or content[8:12] != b"WEBP":
        return False
    if content[12:16] == b"VP8X" and (content[20] & 0x02) != 0:
        return True
    return b"ANIM" in content


def is_animated_image(filename: str, content: bytes) -> bool:
    lower = filename.lower()
    if lower.endswith(".png"):
        return is_animated_png(content)
    if lower.endswith(".webp"):
        return is_animated_webp(content)
    return False
