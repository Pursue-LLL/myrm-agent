# services/channels/pairing/

## Overview

Model-agnostic external channel token binding and visual pairing handshake engine.
Decouples channel authentication from LLM capabilities, providing deterministic dynamic QR codes, webhook callbacks, and one-click ping connectivity verification.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Facade | Module exports for pairing types and handshake service | ✅ |
| `pairing_types.py` | Schema | Pydantic data contracts for pairing sessions, QR codes, and ping tests | ✅ |
| `channel_handshake_service.py` | Service | State machine managing dynamic sessions, SVG QR generation, token persistence, and ping verification | ✅ |

## Dependencies

- `pairing_types.py` → `pydantic`
- `channel_handshake_service.py` → `app.channels.storage.credentials_store`, `pairing_types.py`
