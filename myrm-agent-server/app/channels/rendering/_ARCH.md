# rendering/

## Overview
Outbound message formatting: Markdown/plaintext rendering, message splitting, and cost metadata footer.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Outbound message formatting: Markdown/plaintext rendering and message splitting. | — |
| converter_registry.py | Core | Pluggable format conversion registry. Channels register (source_format, | ✅ |
| renderer.py | Core | Outbound message formatting pipeline (_prepare → _format → split_message). Full body content flows to split_message for multi-chunk IM delivery. A reply is rendered once: `mark_rendered()` stamps a message that carries one rendered chunk (tool summary, sources and header already in its text), and `render()` returns such a message as `[content]`, so a channel that renders what it receives cannot decorate it a second time. | ✅ |
| splitter.py | Core | Smart long-message splitter + `cap_stream_preview` for streaming IM placeholders. Fence state machine, CJK boundaries, join-preserving line iteration; no chunk is longer than `max_len` (a code line too long for a chunk is cut and fenced piece by piece) and splitting never leaves a chunk holding only a fence marker. | ✅ |
| text_utils.py | Core | Universal text utilities. Provides code-block-aware text processing | ✅ |
