# Reply/Quote Context (Universal Structured Protocol)

## Overview

A reply or quote travels as structured data on `InboundMessage.reply_to`, so the model knows which earlier message a user is answering without the quote being flattened into the text.

- **Type**: `ReplyContext` in `messages.py` — frozen, slotted dataclass: `message_id`, `content`, `media: tuple[MediaAttachment, ...]`, `sender_id`, `sender_name`, `timestamp`.
- **Carried by**: `InboundMessage.reply_to: ReplyContext | None`, next to `reply_to_id`, the plain id a channel uses to address a native reply on the way out.
- **Persisted as**: `ReplyContextWire` (`inbound_wire.py`); the inbound log stores it and a replayed message keeps its quote.
- **Why structured**: attachments stay attached, the parser does not cut the quote, sender and time survive, and the model gets an unambiguous split between the quote and the user's own words.

Providers that fill `reply_to`: WeCom, Telegram, Feishu, Discord, Slack, WhatsApp and OneBot. iMessage (BlueBubbles) sets `reply_to_id` only.

## Providers

| Channel | Source | Fetch | Content | Media | Sender / time | Code |
|---------|--------|-------|---------|-------|---------------|------|
| WeCom | `body["quote"]`: text, image, file, voice, video, location, link, mixed | none (embedded) | text parts joined by newlines; the same `_parse_msg_item` reads the message itself | one per item | none | `wecom/aibot_inbound.py::_parse_quoted_message` |
| Telegram | `reply_to_message` | none | text, else caption, else the sticker emoji | photo, document, video, audio/voice, sticker | id, name (first and last name, else username), `date` | `telegram/inbound_message.py::_parse_reply_to_message` |
| Feishu | `parent_id` | `get_message` API | extracted message text | image, file, audio, media (video) | `open_id`, name through the contact API (fail-open), `create_time` | `feishu/inbound.py::_fetch_reply_context` |
| Discord | `message.reference.resolved` | none | message text plus embed description or title | attachments (`_extract_media`) | author id and name, `created_at` | `discord/inbound.py::_parse_reply_context` |
| Slack | `thread_ts` | `conversations.history`, cached per `channel:thread_ts` with a TTL and LRU eviction | original text, mention tokens kept for the auto-reply check | files by mimetype: image, video, audio, else document | user id, name through `users.info`, `ts` | `slack/context.py::_fetch_thread_parent` |
| WhatsApp | `quotedMessage` of the bridge event | none | quoted text | none | id (phone-number JID preferred over LID), name; no time | `whatsapp/inbound.py` |
| OneBot | `reply` segment | none | empty: only the id is read, the content would need an extra API call | none | none | `onebot/channel.py` |

Pattern: **embedded** quotes (WeCom, Telegram, Discord, WhatsApp, OneBot) are parsed from the event; **reference-only** quotes (Feishu, Slack) are fetched through the platform API.

## Edge cases

| Case | Handling |
|------|----------|
| No reply or quote field | `reply_to` is `None` |
| Quote with neither text nor media (WeCom, Telegram) | `None` |
| WhatsApp quote without text | `None` |
| Fetch fails or returns no message (Feishu, Slack) | `None`; a failure is logged at debug level |
| Discord `resolved` is not a `Message` (deleted or not cached) | id-only `ReplyContext` (empty content) and `reply_to_id` |
| OneBot `reply` segment | id-only `ReplyContext`; the content would need an extra API call that is not made |
| WeCom `mixed` quote with empty items | empty items are skipped, the rest accumulates |

## Discord details

- `reference.resolved` is a `Message`, a `DeletedReferencedMessage` or `None`; only a `Message` yields rich context.
- `_resolve_mentioned` treats a reply to the bot's own message as an implicit mention in groups, for human senders only. Another bot replying must @mention explicitly (see routing/_ARCH.md, "Bot-Authored Ingress Guard").
- Outbound, `reply_reference()` (`discord/helpers.py`) builds `MessageReference(message_id, channel_id, fail_if_not_exists=False)`; Discord rejects a reference without `channel_id`. An id that cannot be addressed sends a plain post.

## What the model sees

`build_channel_inbound_query` (`app/core/channel_bridge/agent_executor/helpers.py`) puts the quote in front of the user's words through `_decorate_user_text`:

```
[Replying to Alice]: "Tomorrow is sunny, 28°C" [1 attachment(s)]
---
What about the day after?
```

- The sender is `sender_name`, else `sender_id`, else "someone".
- The quote is cut at 500 characters (`_REPLY_CONTENT_MAX_LEN`) and ends in `...`.
- Sender and quote both pass `sanitize` (content boundary), so quoted text cannot inject instructions.
- The attachment hint states how many attachments the quoted message had.
- Group context and the delivery banner wrap the result.

## Adding reply support to a channel

1. Build a `ReplyContext` in the provider's inbound path, from the event or through a fetch; return `None` when there is nothing to quote.
2. Pass it as `reply_to=` to `_build_inbound` (`channels/core/inbound_pipeline.py` forwards keyword arguments to `InboundMessage`), and set `reply_to_id` when the platform can address a native reply.
3. Cover every media type the provider maps and the empty and failure cases in the provider's tests.

## Tests

- `tests/channels/providers/wecom/test_wecom_aibot_extra.py` — `_parse_quoted_message`
- `tests/channels/providers/telegram/test_telegram_parse_mentions_replies.py` — reply parsing
- `tests/channels/providers/feishu/test_feishu_channel.py::TestFetchReplyContext` — parent-message fetch
- `tests/channels/providers/discord/test_discord_reply_context.py` — `_parse_reply_context`, `_resolve_mentioned`
- `tests/channels/providers/slack/test_slack_thread_replies.py` — thread-parent fetch
- `tests/channels/providers/whatsapp/test_whatsapp_channel.py` — quoted messages
- `tests/channels/types/test_inbound_wire.py` — wire round trip
- `tests/core/channel_bridge/test_channel_inbound_user_text.py` — the prefix the model sees

## Related

- [wecom/_ARCH.md](../providers/wecom/_ARCH.md), [telegram/_ARCH.md](../providers/telegram/_ARCH.md), [feishu/_ARCH.md](../providers/feishu/_ARCH.md), [discord/_ARCH.md](../providers/discord/_ARCH.md), [slack/_ARCH.md](../providers/slack/_ARCH.md), [whatsapp/_ARCH.md](../providers/whatsapp/_ARCH.md), [onebot/_ARCH.md](../providers/onebot/_ARCH.md)
- Feishu parsing helpers: [feishu/parser.py](../providers/feishu/parser.py); Slack thread tracking: [slack/thread_tracker.py](../providers/slack/thread_tracker.py)
