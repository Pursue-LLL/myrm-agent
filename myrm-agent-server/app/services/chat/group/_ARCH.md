# services/chat/group/

## Overview

Bot Mode multi-agent group chat and Hermes peer messaging orchestration service.
Supports Discord/Slack-style multi-agent rooms, Composer `@-mention` fan-out dispatching, deterministic SVG persona avatar color generation, and peer-to-peer consultation archiving into canonical Bot Chat histories.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Facade | Module exports for group chat models and orchestration service | ✅ |
| `group_chat_types.py` | Schema | Pydantic contracts for participants, rooms, messages, mentions, and peer archives | ✅ |
| `agent_peer_messaging_service.py` | Service | Singleton managing group room lifecycle, mention broadcasting, and peer consultation DM archiving | ✅ |

## Dependencies

- `group_chat_types.py` → `pydantic`, `enum`
- `agent_peer_messaging_service.py` → `group_chat_types.py`, `hashlib`, `time`, `uuid`
