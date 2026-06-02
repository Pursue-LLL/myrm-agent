# whatsapp/

## Overview
WhatsApp channel provider via Baileys multi-device bridge.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | WhatsApp channel provider via Baileys multi-device bridge. | — |
| bridge.py | Core | Bridge process management. WhatsAppChannel inherits spawn/read/write/kill via Mixin; | ✅ |
| channel.py | Core | WhatsApp integration: inbound bridge->_handle_inbound->_emit_inbound, outbound bridge stdin "send". | ✅ |
| format_converter.py | Core | WhatsApp format conversion. Protects code blocks/inline code, converts | ✅ |
| helpers.py | Core | WhatsApp JID normalization, mention detection, self-chat detection, and path constants. | ✅ |
