# Reply/Quote Context Design (Universal Structured Protocol)

## Overview

Framework-level structured reply/quote mechanism enabling LLMs to understand reply relationships without text flattening.

**Supported channels**: WeCom, Telegram, Feishu, Discord, Slack  
**Core type**: `ReplyContext` dataclass (immutable, frozen, slotted)  
**Advantage**: Structured data > flat string concat (competitor approach)

---

## Design Philosophy

### Problem: Competitor's Flat String Approach

```python
# Competitor (CoPaw, etc.): Flat string concatenation
content = f"> {quoted_text[:200]}\n{user_reply}"
# Result: LLM must parse ambiguous text to understand quote vs reply
```

**Issues**:
- Media attachments lost in flattening
- Quote content truncated (200 chars limit)
- Ambiguity: LLM cannot reliably distinguish quote from reply
- No sender/timestamp metadata preserved

### Solution: Structured ReplyContext

```python
@dataclass(frozen=True, slots=True)
class ReplyContext:
    message_id: str
    content: str
    media: tuple[MediaAttachment, ...] = ()
    sender_id: str | None = None
    sender_name: str | None = None
    timestamp: float | None = None
```

**Benefits**:
- Native `MediaAttachment` tuple (no data loss)
- Full content preserved (no truncation)
- Unambiguous structure (LLM direct access)
- Rich metadata (sender, timestamp) for context

---

## InboundMessage Integration

```python
@dataclass(frozen=True, slots=True)
class InboundMessage:
    # ... existing fields ...
    reply_to: ReplyContext | None = None  # ← New field
```

**LLM receives**:
```python
InboundMessage(
    content="用户回复内容",
    reply_to=ReplyContext(
        message_id="quoted_msg_123",
        content="被引用的原始消息",
        media=(MediaAttachment(...), ...),
        sender_id="sender_456",
        sender_name="Alice",
        timestamp=1712345678.9,
    )
)
```

---

## Channel Implementations

### 1. WeCom (`wecom_aibot.py`)

**Mapping**: `body["quote"]` → `ReplyContext`

```python
def _parse_quoted_message(body: dict) -> ReplyContext | None:
    """Parse WeCom quote field into ReplyContext.
    
    Supports: text, image, file, voice, video, location, link, mixed.
    """
    quote = body.get("quote")
    if not quote:
        return None
    
    # Handle mixed vs single quote
    if quote_type == "mixed":
        quoted_items = quote["mixed"]["msg_item"]
    else:
        quoted_items = [quote]
    
    # Parse each item using unified _parse_msg_item
    for item in quoted_items:
        content, media = self._parse_msg_item(item)
        # Accumulate text_parts and media_list
    
    return ReplyContext(message_id=quoted_msg_id, content=..., media=...)
```

**Highlights**:
- Unified `_parse_msg_item` (eliminates code duplication with primary message parsing)
- 7 msgtype support + mixed (competitor: 4 types)
- 32 lines (down from 76 via refactor)

---

### 2. Telegram (`telegram/inbound.py`)

**Mapping**: `msg.reply_to_message` → `ReplyContext`

```python
def _parse_reply_to_message(reply_msg: TgMessage) -> ReplyContext | None:
    """Parse Telegram replied-to message into ReplyContext.
    
    Supports: text, caption, photo, document, video, audio/voice, sticker.
    """
    content = reply_msg.text or reply_msg.caption or reply_msg.sticker.emoji
    
    media_list = []
    if reply_msg.photo:
        media_list.append(MediaAttachment(media_type=MediaType.IMAGE))
    # ... (document/video/audio/sticker)
    
    return ReplyContext(
        message_id=str(reply_msg.message_id),
        content=content.strip(),
        media=tuple(media_list),
        sender_id=str(reply_msg.from_user.id),
        sender_name=reply_msg.from_user.display_name,
        timestamp=float(reply_msg.date),
    )
```

**Highlights**:
- Complete Message object available (recursive `TgMessage` field)
- Rich metadata: sender_id/name + timestamp preserved
- 64 lines

---

### 3. Feishu (`feishu/channel.py`)

**Mapping**: `parent_id` → API fetch → `ReplyContext`

```python
async def _fetch_reply_context(parent_id: str) -> ReplyContext | None:
    """Fetch parent message via Feishu API and parse into ReplyContext.
    
    Retrieves: text content + media (image/file/audio/media) + sender/timestamp.
    """
    msg_obj = await self._client.get_message(parent_id)
    
    text = extract_message_text(msg_obj)
    
    # Parse media by msg_type
    media_list = []
    if msg_obj["msg_type"] == "image":
        media_list.append(MediaAttachment(media_type=MediaType.IMAGE))
    # ... (file/audio/media)
    
    return ReplyContext(
        message_id=parent_id,
        content=text,
        media=tuple(media_list),
        sender_id=msg_obj["sender"]["sender_id"]["open_id"],
        timestamp=float(msg_obj["create_time"]) / 1000.0,
    )
```

**Highlights**:
- API fetch required (parent_id is just a reference, not full message)
- Replaces previous flat string `"> {text[:200]}"` with structured data
- 47 lines (refactor from previous implementation)

---

### 4. Discord (`discord/channel.py`)

**Mapping**: `message.reference` + `message.referenced_message` → `ReplyContext`

```python
def _parse_referenced_message(message: discord.Message) -> ReplyContext | None:
    """Parse Discord reference into ReplyContext.
    
    Uses referenced_message (full Message object) if available,
    fallback to reference (ID-only metadata).
    
    Supports: text, embeds, attachments (image/document/video/audio).
    """
    if not message.reference:
        return None
    
    ref_msg = message.referenced_message
    if not ref_msg:
        # Fallback: only message ID available
        return ReplyContext(
            message_id=str(message.reference.message_id),
            content="",
            media=(),
        )
    
    content = strip_mention(ref_msg.content or "", self._client.user)
    
    # Include embed content
    if ref_msg.embeds:
        embed_texts = [e.description or e.title for e in ref_msg.embeds]
        content += "\n" + "\n".join(filter(None, embed_texts))
    
    # Parse attachments by content_type
    media_list = []
    for att in ref_msg.attachments:
        if att.content_type.startswith("image/"):
            media_list.append(MediaAttachment(media_type=MediaType.IMAGE, url=att.url))
        # ... (video/audio/document)
    
    return ReplyContext(
        message_id=str(ref_msg.id),
        content=content.strip(),
        media=tuple(media_list),
        sender_id=str(ref_msg.author.id),
        sender_name=ref_msg.author.display_name,
        timestamp=ref_msg.created_at.timestamp(),
    )
```

**Highlights**:
- Elegant fallback: `referenced_message` (full object) → `reference` (ID-only)
- Embed content included in text (Discord-specific rich formatting)
- 60 lines

---

### 5. Slack (`slack/channel.py`)

**Mapping**: `thread_ts` → API fetch → `ReplyContext`

```python
async def _fetch_thread_parent(channel_id: str, thread_ts: str) -> ReplyContext | None:
    """Fetch Slack thread parent message and parse into ReplyContext.
    
    Uses conversations.history API with latest=thread_ts&limit=1.
    Supports: text, file attachments (image/document/video/audio).
    """
    resp = await self._api.request(
        "POST",
        "conversations.history",
        {
            "channel": channel_id,
            "latest": thread_ts,
            "inclusive": True,
            "limit": 1,
        },
    )
    
    parent_msg = resp["messages"][0]
    content = strip_mention(parent_msg["text"], self._bot_user_id)
    
    # Parse files by mimetype
    media_list = []
    for f in parent_msg.get("files", []):
        mimetype = f["mimetype"]
        if mimetype.startswith("image/"):
            media_list.append(MediaAttachment(media_type=MediaType.IMAGE, url=f["url_private"]))
        # ... (video/audio/document)
    
    # Resolve sender name via users.info API
    sender_id = parent_msg.get("user")
    sender_name = await self._user_resolver.resolve_user(sender_id) if sender_id else None
    
    return ReplyContext(
        message_id=thread_ts,
        content=content,
        media=tuple(media_list),
        sender_id=sender_id,
        sender_name=sender_name,  # ✅ Resolved via UserResolver
        timestamp=float(parent_msg["ts"]),
    )
```

**Highlights**:
- API fetch required (thread_ts is timestamp, not full message)
- Async refactor: `_parse_message_event` → `async def` (enables await)
- 73 lines

---

## Cross-Channel Comparison

| Channel | Reply Field | API Fetch? | Media Support | Sender/Timestamp |
|---------|-------------|-----------|---------------|------------------|
| WeCom | `quote` dict | ❌ | 7 types + mixed | ❌ (not in payload) |
| Telegram | `reply_to_message` | ❌ | 6 types | ✅ Full user object + date |
| Feishu | `parent_id` | ✅ | 4 types | ⚠️ sender_id only (name=None) |
| Discord | `referenced_message` | ❌ | Attachments + embeds | ✅ author + created_at |
| Slack | `thread_ts` | ✅ | Files (all types) | ✅ user + ts + **name (via users.info)** |

**Pattern**:
- **Embedded reply data** (WeCom/Telegram/Discord): Parse directly from event payload
- **Reference-only** (Feishu/Slack): Fetch parent message via API

---

## LLM Context Injection (Implemented)

Reply context is injected into the LLM query via `build_channel_inbound_query()` in
`app/core/channel_bridge/agent_executor/helpers.py`:

```python
# _format_reply_context() produces:
# [Replying to Alice]: "Tomorrow is sunny, 28°C" [1 attachment(s)]
# ---
# What about the day after?

# Full flow: InboundMessage.reply_to → _format_reply_context() → prepend to body → LLM sees it
```

**Key properties**:
- `sender_name` included → LLM knows who sent the original
- `media` hint included → LLM knows attachments existed
- Content truncated to 500 chars → prevents context window bloat
- `sanitize()` applied → prevents prompt injection from quoted content

**vs Competitor (Hermes)**:
```python
# Hermes approach [gateway/run.py:8044-8052]:
reply_snippet = event.reply_to_text[:500]
message_text = f'[Replying to: "{reply_snippet}"]\n\n{message_text}'
# Missing: sender_name, media hint, security sanitization
```

---

## Edge Cases

| Case | Handling |
|------|----------|
| No reply/quote field | `ReplyContext` = `None` (normal message) |
| Empty content + no media | Return `None` (invalid reply) |
| API fetch failure | Return `None` + debug log |
| Referenced message deleted | Discord: ID-only fallback; Others: `None` |
| Mixed quote with empty items | WeCom: Skip empty items, accumulate non-empty |

---

## Code Quality Metrics

| Channel | Lines | Lints | Refactor Benefit |
|---------|-------|-------|------------------|
| Framework | 18 | 0 | Unified protocol |
| WeCom | 净减44行 | 0 | DRY: `_parse_msg_item` |
| Telegram | 64 | 0 | - |
| Feishu | 47 | 0 | flat string → structured |
| Discord | 60 | 0 | - |
| Slack | 73 | 0 | async refactor |
| **Total** | **~280净增** | **0** | **Cross-channel consistency** |

**Architecture principles**:
- Single responsibility: Each method parses one aspect
- Type safety: `isinstance` checks + optional chaining
- Defensive programming: Multiple layers of None guards
- Maintainability: Future msgtype additions require single-point edit

---

## Testing Strategy

**Unit tests** (planned):
- `tests/unit/test_wecom_quote_parsing.py`
- `tests/unit/test_telegram_reply_parsing.py`
- `tests/unit/test_feishu_reply_fetch.py`
- `tests/unit/test_discord_reference_parsing.py`
- `tests/unit/test_slack_thread_fetch.py`

**Coverage**:
- All msgtype/attachment types per channel
- Edge cases (empty content, missing fields, API failures)
- Integration with `_build_inbound` → `InboundMessage`

**Integration tests** (planned):
- Mock external API calls (Feishu/Slack)
- Verify `reply_to` field propagates to agent context

---

## Migration Guide (for developers extending channels)

When adding reply/quote support to a new channel:

1. **Import `ReplyContext`**:
   ```python
   from app.channels.types import ReplyContext
   ```

2. **Create parsing method**:
   ```python
   async def _parse_reply(self, ...) -> ReplyContext | None:
       # Extract replied-to message (from event or API)
       # Parse content, media, sender, timestamp
       return ReplyContext(...) if valid else None
   ```

3. **Integrate with `_build_inbound`**:
   ```python
   reply_to = await self._parse_reply(...)
   msg = self._build_inbound(
       ...,
       reply_to=reply_to,  # ← Pass structured context
   )
   ```

4. **Handle edge cases**:
   - No reply field → `None`
   - Empty content + no media → `None`
   - API failure → `None` + log

5. **Add tests**: Unit test covering all supported media types and edge cases.

---

## Related Documentation

- [WeCom Quote Parsing](../providers/wecom/QUOTE_PARSING.md)
- [Telegram Reply Parsing](../providers/telegram/REPLY_PARSING.md) (planned)
- [Feishu Reply Fetch](../providers/feishu/REPLY_FETCH.md) (planned)
- [Discord Reference Parsing](../providers/discord/REFERENCE_PARSING.md) (planned)
- [Slack Thread Fetch](../providers/slack/THREAD_FETCH.md) (planned)
- [Competitor Comparison Roadmap](../../../../../../temp-docs/COMPETITOR_BORROWABLE_HIGHLIGHTS_ROADMAP.md)
