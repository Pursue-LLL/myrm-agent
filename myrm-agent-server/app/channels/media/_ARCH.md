# media/

## Overview
Media download system with streaming, validation, retry, cache, sticker visual understanding, image enrichment for multimodal LLM vision input, and structured contact/vCard parsing.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Media download system with streaming, validation, retry, cache, and sticker vision. | — |
| cache.py | Core | Media download cache with LRU eviction. | ✅ |
| config.py | Config | Media download configuration. | ✅ |
| contact_enrichment.py | Core | vCard contact attachment parsing (2.1/3.0/4.0) and enrichment; stores `metadata["contact_cards"]` for LLM context injection. | ✅ |
| downloader.py | Core | Core media downloader with streaming, SSRF-pinned fetch (`secure_fetch`), retry, cache, and metrics. | ✅ |
| exceptions.py | Core | Media download exceptions. | ✅ |
| image_enrichment.py | Core | Image attachment download via SSRF-safe `secure_get`, compression, and local file caching for multimodal LLM vision input. | ✅ |
| document_enrichment.py | Core | PDF/Office download and text extraction for IM; stores `metadata["document_text_blocks"]` (honors `extractDocumentText`). | ✅ |
| progress.py | Core | Progress callback protocol for media downloads. | ✅ |
| retry.py | Core | Retry policy for media downloads. | ✅ |
| sticker_vision.py | Core | Sticker visual understanding via Vision model with LRU cache. | ✅ |
| video_enrichment.py | Core | Video attachment detection and metadata enrichment for channel router. | ✅ |
| validators.py | Core | Media download validators. | ✅ |

## Key Dependencies

- `utils`
- `vision.fallback_engine` (for sticker image-to-text conversion)
- `channels.types` (for InboundMessage, MediaType)
