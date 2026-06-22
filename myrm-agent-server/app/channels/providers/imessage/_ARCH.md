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
| `channel.py` | Core channel implementation (send/receive/webhook) |
| `parser.py` | Inbound webhook payload parsing |
| `helpers.py` | Utility functions (media MIME, formatting) |
| `webhook.py` | Webhook signature verification |

## Design Notes

- Requires BlueBubbles server running on macOS with iMessage access
- Webhook HMAC authentication for inbound messages
- Tapback reactions mapped to standard reaction enum
- Multipart attachment upload for media messages
