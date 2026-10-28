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
| `__init__.py` | Facade exporting `IMessageChannel` |
| `channel.py` | Core channel implementation: lifecycle, inbound webhook, send orchestration (render chunks, quote only the first, deliver attachments), Tapback bookkeeping; `_private_api_ready` is the one check Tapbacks, typing, read receipts and quoted replies share, and `_detect_private_api` refreshes it from `/server/info` at start and at every health check |
| `outbound.py` | The wire contract with BlueBubbles `/api/v1/message/*`: text (Private API quote), multipart attachment upload, Tapback; functions take `http, api_url, password` per call so a replaced client is honoured |
| `diagnostics.py` | `collect_imessage_issues`: pure diagnosis of configuration, status and Private API / helper state |
| `parser.py` | Inbound webhook payload parsing |
| `helpers.py` | Utility functions (media MIME, formatting) and constants (`CHANNEL_NAME`, send and media timeouts, `MAX_TEXT_LENGTH`); `TAPBACK_MAP` is the six Tapback names BlueBubbles accepts (a glyph outside it is not sent; removal posts the name behind `-`); `TAPBACK_CODE_TO_EMOJI` is the inbound `associatedMessageType` table |
| `webhook.py` | Registers the channel's webhook URL with the BlueBubbles server on start and removes it on stop |

## Design Notes

- Requires BlueBubbles server running on macOS with iMessage access
- Inbound webhooks are checked against the configured password (timing-safe comparison)
- Group chat wake-word regex matching and prefix cleaning for Prompt Caching efficiency
- Tapback reactions mapped to standard reaction enum
- Multipart attachment upload for media messages
- BlueBubbles refuses Tapbacks, typing, read receipts and quoted replies unless `private_api` is on and the helper is connected (`checkPrivateApiStatus` in bluebubbles-server), so the channel asks for none of them otherwise; the state follows `/server/info` at every health check (the helper may connect late or drop), and an unreadable body keeps the last state
- A skipped Tapback removal keeps its ledger entry, so a later removal still takes the Tapback off
- Private API helper connectivity diagnostics reported in channel health issues
