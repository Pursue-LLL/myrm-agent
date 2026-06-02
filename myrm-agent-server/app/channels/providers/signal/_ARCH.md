# signal/

## Overview
Signal channel provider via Signal CLI REST API.

Inbound messages are received via WebSocket (real-time, preferred) with
automatic fallback to HTTP polling for older signal-cli-rest-api versions.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Signal channel provider via Signal CLI REST API. | — |
| api.py | Core | Signal HTTP/WS layer. Called by channel.py via self._api. Provides REST messaging + WebSocket stream_events() for real-time inbound. | ✅ |
| channel.py | Core | Signal integration. WebSocket-first inbound with HTTP polling fallback. Outbound via /v2/send. | ✅ |
| helpers.py | Core | Signal envelope type definitions, constants (timeouts, WS settings), and pure functions. Referenced by channel.py and api.py. | ✅ |
