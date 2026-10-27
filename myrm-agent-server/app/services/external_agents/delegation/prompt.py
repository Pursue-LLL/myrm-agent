"""The prompt of a turn delegated straight to an external CLI agent.

[INPUT]
- 无（纯函数；入参是 Agent 收到的用户回合：文本或多模态内容块，以及用户引用的片段）

[OUTPUT]
- delegation_prompt: 用户回合 → 外部 CLI 只收文本的那一条提示词
- image_url, is_video: 图片内容块指向的 URL，以及该块装的是不是视频（暂存模块与提示词共用的唯一判法）

[POS]
直连委托把用户回合交给只收文本的外部 CLI。多模态内容块拼成文本：文本块按原样连接；图片在 CLI 能读到的
位置（本地路径或 http(s) 地址）时给出一行指向，内联数据（data URL）CLI 读不到，明说没有转交，不把 base64
灌进提示词；划词引用的片段用主 Agent 同款的 `<quoted_context>` 标签放在最前。不写任何路由横幅：那是给主 Agent 的
模型看的，外部 CLI 的提示词里只该有用户自己的内容。
"""

from __future__ import annotations

from urllib.parse import urlparse
from urllib.request import url2pathname

_INLINE_IMAGE_NOTE = "[Image attached inline: its data was not forwarded to this agent]"
_PART_SEPARATOR = "\n\n"


def image_url(part: dict[str, object]) -> str | None:
    """The URL an ``image_url`` content block points at, or None when it names nothing."""
    image = part.get("image_url")
    url = image.get("url") if isinstance(image, dict) else image
    return url if isinstance(url, str) and url else None


def is_video(part: dict[str, object]) -> bool:
    """Whether an ``image_url`` content block carries a video (the frontend sends both through that block type)."""
    return str(part.get("_mime_type", "")).startswith("video/")


def _image_reference(part: dict[str, object]) -> str | None:
    """One line pointing the CLI at an attached image (or video), or None when the part names nothing."""
    url = image_url(part)
    if url is None:
        return None
    if url.startswith("data:"):
        return _INLINE_IMAGE_NOTE
    kind = "Video" if is_video(part) else "Image"
    location = url2pathname(urlparse(url).path) if url.startswith("file:") else url
    return f"[{kind}: {location}]"


def _part_text(part: object) -> str | None:
    if not isinstance(part, dict):
        return None
    match part.get("type"):
        case "text":
            text = part.get("text")
            return text if isinstance(text, str) and text else None
        case "image_url":
            return _image_reference(part)
        case _:
            return None


def delegation_prompt(query: object, quote: str | None = None) -> str:
    """The text prompt an external CLI gets for ``query``, with the passage the user quoted (if any) in front."""
    if isinstance(query, str):
        body = query
    elif isinstance(query, list):
        body = _PART_SEPARATOR.join(text for text in map(_part_text, query) if text)
    else:
        body = str(query)
    if quote and quote.strip():
        return f"<quoted_context>\n{quote}\n</quoted_context>{_PART_SEPARATOR}{body}"
    return body
