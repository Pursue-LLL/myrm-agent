"""Feishu inbound message parsing — rich text, mentions, and media extraction.

Parses Feishu event payloads into structured data for the channel system.
Handles msg_type=post (rich text), msg_type=text, @mention detection,
and image/media key extraction.

[INPUT]

[OUTPUT]
- parse_post_content() → PostParseResult (markdown + image_keys + mentioned_ids)
- parse_inbound_event() → FeishuInboundEvent (sender, chat, content, mentions, media)

[POS]
Feishu inbound message parser. Converts Feishu event JSON to structured data.
Supports post rich-text -> Markdown, @mention detection, and image/media key extraction.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from .models import FeishuMessageEvent, FeishuWebhookPayload

logger = logging.getLogger(__name__)

_MARKDOWN_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-!|>~])")
_FALLBACK_POST_TEXT = "[富文本消息]"


@dataclass(frozen=True, slots=True)
class PostParseResult:
    """Result of parsing a Feishu post (rich text) message."""

    text: str
    image_keys: list[str] = field(default_factory=list)
    media_keys: list[tuple[str, str | None]] = field(default_factory=list)
    mentioned_open_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class FeishuInboundEvent:
    """Structured representation of a Feishu inbound message event."""

    sender_id: str
    chat_id: str
    content: str
    message_id: str
    msg_type: str
    is_group: bool
    bot_mentioned: bool
    sender_type: str = ""
    root_id: str | None = None
    parent_id: str | None = None
    image_keys: list[str] = field(default_factory=list)
    media_keys: list[tuple[str, str | None]] = field(default_factory=list)


def _escape_md(text: str) -> str:
    """Escape Markdown special characters in plain text."""
    return _MARKDOWN_SPECIAL.sub(r"\\\1", text)


def _wrap_inline_code(text: str) -> str:
    """Wrap text in inline code, handling nested backticks."""
    max_run = max((len(m) for m in re.findall(r"`+", text)), default=0)
    fence = "`" * (max_run + 1)
    needs_padding = text.startswith("`") or text.endswith("`")
    body = f" {text} " if needs_padding else text
    return f"{fence}{body}{fence}"


def _sanitize_fence_lang(lang: str) -> str:
    return re.sub(r"[^A-Za-z0-9_+#.\-]", "", lang.strip())


def _render_text_element(el: dict[str, object]) -> str:
    text = str(el.get("text", ""))
    style = el.get("style")
    if not isinstance(style, dict):
        style = {}

    if style.get("code"):
        return _wrap_inline_code(text)

    rendered = _escape_md(text)
    if not rendered:
        return ""

    if style.get("bold"):
        rendered = f"**{rendered}**"
    if style.get("italic"):
        rendered = f"*{rendered}*"
    if style.get("underline"):
        rendered = f"<u>{rendered}</u>"
    if style.get("strikethrough") or style.get("line_through") or style.get("lineThrough"):
        rendered = f"~~{rendered}~~"
    return rendered


def _render_link_element(el: dict[str, object]) -> str:
    href = str(el.get("href", "")).strip()
    raw_text = str(el.get("text", ""))
    text = raw_text or href
    if not text:
        return ""
    if not href:
        return _escape_md(text)
    return f"[{_escape_md(text)}](<{href}>)"


def _render_code_block(el: dict[str, object]) -> str:
    lang = _sanitize_fence_lang(str(el.get("language", "") or el.get("lang", "")))
    code = str(el.get("text", "") or el.get("content", "")).replace("\r\n", "\n")
    trailing = "" if code.endswith("\n") else "\n"
    return f"```{lang}\n{code}{trailing}```"


def _render_element(
    el: object,
    image_keys: list[str],
    media_keys: list[tuple[str, str | None]],
    mentioned_ids: list[str],
) -> str:
    """Render a single post element to Markdown."""
    if not isinstance(el, dict):
        return _escape_md(str(el)) if el else ""

    tag = str(el.get("tag", "")).lower()

    if tag == "text":
        return _render_text_element(el)
    if tag == "a":
        return _render_link_element(el)
    if tag == "at":
        open_id = str(el.get("open_id", "") or el.get("user_id", "")).strip()
        if open_id:
            mentioned_ids.append(open_id)
        name = str(el.get("user_name", "") or el.get("user_id", "") or el.get("open_id", ""))
        return f"@{_escape_md(name)}" if name else ""
    if tag == "img":
        key = str(el.get("image_key", "")).strip()
        if key:
            image_keys.append(key)
        return "![image]"
    if tag == "media":
        file_key = str(el.get("file_key", "")).strip()
        if file_key:
            file_name = str(el.get("file_name", "")) or None
            media_keys.append((file_key, file_name))
        return "[media]"
    if tag == "emotion":
        return str(el.get("emoji", "") or el.get("text", "") or el.get("emoji_type", ""))
    if tag == "br":
        return "\n"
    if tag == "hr":
        return "\n\n---\n\n"
    if tag == "code":
        code = str(el.get("text", "") or el.get("content", ""))
        return _wrap_inline_code(code) if code else ""
    if tag in ("code_block", "pre"):
        return _render_code_block(el)

    return _escape_md(str(el.get("text", "")))


def _resolve_post_payload(raw: object) -> tuple[str, list[object]] | None:
    """Extract (title, content_paragraphs) from a post payload.

    Handles three shapes:
    - Direct: {"title": "...", "content": [[...]]}
    - Localized: {"zh_cn": {"title": "...", "content": [...]}}
    - Wrapped: {"post": {"zh_cn": {"title": "...", "content": [...]}}}
    """
    if not isinstance(raw, dict):
        return None

    def _try_block(block: object) -> tuple[str, list[object]] | None:
        if not isinstance(block, dict) or not isinstance(block.get("content"), list):
            return None
        return str(block.get("title", "")), block["content"]

    direct = _try_block(raw)
    if direct:
        return direct

    root = raw.get("post", raw) if isinstance(raw.get("post"), dict) else raw

    for locale in ("zh_cn", "en_us", "ja_jp"):
        if locale in root and isinstance(root[locale], dict):
            result = _try_block(root[locale])
            if result:
                return result

    for val in root.values():
        if isinstance(val, dict):
            result = _try_block(val)
            if result:
                return result

    return None


def parse_post_content(content: str) -> PostParseResult:
    """Parse a Feishu post (rich text) message into Markdown.

    Converts post JSON content into Markdown text while collecting
    image keys, media keys, and mentioned user IDs.
    """
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return PostParseResult(text=_FALLBACK_POST_TEXT)

    payload = _resolve_post_payload(parsed)
    if not payload:
        return PostParseResult(text=_FALLBACK_POST_TEXT)

    title_raw, paragraphs = payload
    image_keys: list[str] = []
    media_keys: list[tuple[str, str | None]] = []
    mentioned_ids: list[str] = []
    rendered_paragraphs: list[str] = []

    for para in paragraphs:
        if not isinstance(para, list):
            continue
        line = "".join(_render_element(el, image_keys, media_keys, mentioned_ids) for el in para)
        rendered_paragraphs.append(line)

    title = _escape_md(title_raw.strip())
    body = "\n".join(rendered_paragraphs).strip()
    parts = [p for p in (title, body) if p]
    text = "\n\n".join(parts).strip() or _FALLBACK_POST_TEXT

    return PostParseResult(
        text=text,
        image_keys=image_keys,
        media_keys=media_keys,
        mentioned_open_ids=mentioned_ids,
    )


def _check_bot_mentioned(
    mentions: list[dict[str, object]],
    bot_open_id: str,
) -> bool:
    """Check if the bot is mentioned in the message's mention list."""
    if not bot_open_id:
        return False
    for m in mentions:
        mid = m.get("id", {})
        open_id = (mid.get("open_id") if isinstance(mid, dict) else None) or m.get("open_id")
        if open_id == bot_open_id:
            return True
    return False


def _strip_at_placeholders(text: str) -> str:
    """Remove @_user_N placeholder tokens injected by Feishu in group chats."""
    return re.sub(r"@_user_\d+\s?", "", text)


def parse_inbound_event(
    body: dict[str, object],
    bot_open_id: str = "",
) -> FeishuInboundEvent | None:
    """Parse a Feishu webhook event body into a structured inbound event.

    Uses Pydantic models for type-safe payload validation. Returns None
    if the event doesn't contain a valid message.
    """
    try:
        payload = FeishuWebhookPayload.model_validate(body)
    except ValidationError:
        logger.debug("Feishu webhook payload validation failed")
        return None

    if not isinstance(payload.event, dict):
        return None

    try:
        evt = FeishuMessageEvent.model_validate(payload.event)
    except ValidationError:
        logger.debug("Feishu message event validation failed")
        return None

    sender_id = evt.sender.sender_id.open_id
    if not sender_id:
        return None

    msg = evt.message
    msg_type = msg.message_type
    is_group = msg.chat_type == "group"

    mention_dicts = [m.model_dump() for m in msg.mentions]
    bot_mentioned = _check_bot_mentioned(mention_dicts, bot_open_id)

    content_raw = msg.content
    image_keys: list[str] = []
    media_keys: list[tuple[str, str | None]] = []
    content = ""

    try:
        content_json = json.loads(content_raw) if content_raw else {}
    except (json.JSONDecodeError, TypeError):
        content_json = {}

    if msg_type == "text":
        content = str(content_json.get("text", ""))
        if is_group:
            content = _strip_at_placeholders(content)

    elif msg_type == "post":
        result = parse_post_content(content_raw)
        content = result.text
        image_keys = result.image_keys
        media_keys = result.media_keys
        if not bot_mentioned and result.mentioned_open_ids:
            bot_mentioned = bot_open_id in result.mentioned_open_ids

    elif msg_type == "image":
        key = str(content_json.get("image_key", ""))
        if key:
            image_keys.append(key)
        content = "[image]"

    elif msg_type in ("audio", "file", "media"):
        file_key = str(content_json.get("file_key", ""))
        file_name = str(content_json.get("file_name", "")) or None
        if file_key:
            media_keys.append((file_key, file_name))
        content = f"[{msg_type}]"

    elif msg_type == "interactive":
        card_result = parse_interactive_card(content_raw)
        content = card_result.text
        image_keys = card_result.image_keys

    elif msg_type in ("share_chat", "share_user", "system", "merge_forward"):
        content = f"[{msg_type}]"

    else:
        content = f"[{msg_type}]"

    if not content.strip() and not image_keys and not media_keys:
        return None

    root_id = msg.root_id or None
    parent_id = msg.parent_id or None

    return FeishuInboundEvent(
        sender_id=sender_id,
        chat_id=msg.chat_id,
        content=content.strip(),
        message_id=msg.message_id,
        msg_type=msg_type,
        is_group=is_group,
        bot_mentioned=bot_mentioned,
        sender_type=evt.sender.sender_type,
        root_id=root_id,
        parent_id=parent_id,
        image_keys=image_keys,
        media_keys=media_keys,
    )


@dataclass(frozen=True, slots=True)
class CardParseResult:
    """Result of parsing a Feishu interactive card message."""

    text: str
    image_keys: list[str] = field(default_factory=list)


def _extract_card_text_and_images(
    node: object,
    texts: list[str],
    image_keys: list[str],
) -> None:
    """Recursively extract text and image keys from a Feishu card JSON tree."""
    if isinstance(node, str):
        stripped = node.strip()
        if stripped:
            texts.append(stripped)
        return
    if isinstance(node, list):
        for item in node:
            _extract_card_text_and_images(item, texts, image_keys)
        return
    if not isinstance(node, dict):
        return

    tag = str(node.get("tag", "")).lower()

    if tag == "img":
        key = str(node.get("img_key", "") or node.get("image_key", "")).strip()
        if key:
            image_keys.append(key)
        alt = str(node.get("alt", {}).get("content", "")) if isinstance(node.get("alt"), dict) else ""
        if alt.strip():
            texts.append(alt.strip())
        return

    for text_key in ("content", "text"):
        val = node.get(text_key)
        if isinstance(val, str) and val.strip():
            texts.append(val.strip())
        elif isinstance(val, dict):
            inner = val.get("content") or val.get("text")
            if isinstance(inner, str) and inner.strip():
                texts.append(inner.strip())

    for child_key in ("elements", "actions", "columns", "rows", "fields", "options"):
        child = node.get(child_key)
        if isinstance(child, list):
            for item in child:
                _extract_card_text_and_images(item, texts, image_keys)

    body = node.get("body")
    if isinstance(body, dict):
        _extract_card_text_and_images(body, texts, image_keys)


def parse_interactive_card(content: str) -> CardParseResult:
    """Parse a Feishu interactive card message, extracting text and images.

    Recursively walks the card JSON tree to collect readable text from
    markdown / plain_text / lark_md elements, and image keys from img tags.
    """
    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return CardParseResult(text="[interactive]")

    if not isinstance(parsed, dict):
        return CardParseResult(text="[interactive]")

    texts: list[str] = []
    image_keys: list[str] = []

    header = parsed.get("header")
    if isinstance(header, dict):
        title = header.get("title")
        if isinstance(title, dict):
            t = str(title.get("content", "")).strip()
            if t:
                texts.append(t)
        elif isinstance(title, str) and title.strip():
            texts.append(title.strip())

    _extract_card_text_and_images(parsed.get("elements", []), texts, image_keys)
    _extract_card_text_and_images(parsed.get("body", {}), texts, image_keys)

    seen: set[str] = set()
    unique_texts: list[str] = []
    for t in texts:
        if t not in seen:
            seen.add(t)
            unique_texts.append(t)

    text = "\n".join(unique_texts).strip() or "[interactive]"
    return CardParseResult(text=text, image_keys=image_keys)


def extract_message_text(msg_obj: dict[str, object]) -> str:
    """Extract plain text from a Feishu message object (from GET /im/v1/messages).

    Handles text and post message types. Returns a fallback tag for other types.
    """
    msg_type = str(msg_obj.get("msg_type", ""))
    body = msg_obj.get("body")
    body_str = str(body.get("content", "")) if isinstance(body, dict) else ""
    if not body_str:
        return ""
    try:
        parsed = json.loads(body_str)
    except (json.JSONDecodeError, TypeError):
        return ""
    if msg_type == "text":
        return str(parsed.get("text", ""))
    if msg_type == "post":
        return parse_post_content(body_str).text
    if msg_type == "interactive":
        return parse_interactive_card(body_str).text
    return f"[{msg_type}]"
