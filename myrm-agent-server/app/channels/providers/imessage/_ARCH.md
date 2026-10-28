# iMessage Channel — Architecture

## Position

iMessage bidirectional channel via BlueBubbles macOS HTTP API bridge.

## Inputs

- `channels.core.base::BaseChannel` — Channel abstract base
- BlueBubbles HTTP API (localhost macOS server)

## Outputs

- `IMessageChannel` — text/media send, Tapback reactions, webhook auth

## Key Files

| File | Responsibility |
|------|----------------|
| `channel.py` | Core channel implementation: lifecycle, inbound webhook, send orchestration (render chunks, quote only the first, deliver attachments), Tapback bookkeeping |
| `outbound.py` | The wire contract with BlueBubbles `/api/v1/message/*`: text (Private API quote), multipart attachment upload, Tapback; functions take `http, api_url, password` per call so a replaced client is honoured |
| `diagnostics.py` | `collect_imessage_issues`: pure diagnosis of configuration, status and Private API / helper state |
| `parser.py` | Inbound webhook payload parsing |
| `helpers.py` | Utility functions (media MIME, formatting); `TAPBACK_MAP` is the six Tapback names BlueBubbles accepts (a glyph outside it is not sent; removal posts the name behind `-`); `TAPBACK_CODE_TO_EMOJI` is the inbound `associatedMessageType` table |
| `webhook.py` | Webhook signature verification |

## Design Notes

- Requires BlueBubbles server running on macOS with iMessage access
- Webhook HMAC authentication for inbound messages
- Group chat wake-word regex matching and prefix cleaning for Prompt Caching efficiency
- Tapback reactions mapped to standard reaction enum
- Multipart attachment upload for media messages
- Private API helper connectivity diagnostics reported in channel health issues
