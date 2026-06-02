# rendering/

## Overview
Outbound message formatting: Markdown/plaintext rendering and message splitting.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Outbound message formatting: Markdown/plaintext rendering and message splitting. | — |
| converter_registry.py | Core | Pluggable format conversion registry. Channels register (source_format, | ✅ |
| renderer.py | Core | Outbound message formatting pipeline. Converts structured OutboundMessage to platform-sendable | ✅ |
| splitter.py | Core | Smart long-message splitter. Line-by-line processing with fence state machine, | ✅ |
| text_utils.py | Core | Universal text utilities. Provides code-block-aware text processing | ✅ |
