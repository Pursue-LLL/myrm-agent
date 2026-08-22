# rendering/

## Overview
Outbound message formatting: Markdown/plaintext rendering, message splitting, and cost metadata footer.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Outbound message formatting: Markdown/plaintext rendering and message splitting. | — |
| converter_registry.py | Core | Pluggable format conversion registry. Channels register (source_format, | ✅ |
| renderer.py | Core | Outbound message formatting pipeline. Converts structured OutboundMessage to platform-sendable plain text/Markdown. Includes cost metadata footer rendering via `_build_cost_footer()` when `cost_metadata` is present in message metadata, and supports per-message override `metadata.reasoning_display_mode` to统一控制 reasoning 显示策略。 | ✅ |
| splitter.py | Core | Smart long-message splitter. Fence state machine, CJK full-width punctuation boundaries (`BOUNDARY_CHARS`), multi-chunk delivery without prepare-layer truncation. | ✅ |
| text_utils.py | Core | Universal text utilities. Provides code-block-aware text processing | ✅ |
