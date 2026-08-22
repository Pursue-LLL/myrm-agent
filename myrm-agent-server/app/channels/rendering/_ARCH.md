# rendering/

## Overview
Outbound message formatting: Markdown/plaintext rendering, message splitting, and cost metadata footer.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Outbound message formatting: Markdown/plaintext rendering and message splitting. | — |
| converter_registry.py | Core | Pluggable format conversion registry. Channels register (source_format, | ✅ |
| renderer.py | Core | Outbound message formatting pipeline (_prepare → _format → split_message). Full body content flows to split_message for multi-chunk IM delivery. | ✅ |
| splitter.py | Core | Smart long-message splitter. Fence state machine, CJK full-width punctuation boundaries (`BOUNDARY_CHARS`), join-preserving line iteration (last line no forced `\n`), multi-chunk delivery without prepare-layer truncation. | ✅ |
| text_utils.py | Core | Universal text utilities. Provides code-block-aware text processing | ✅ |
