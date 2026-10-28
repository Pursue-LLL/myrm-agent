# media/

## Overview
Media download system with streaming, validation, retry, cache, sticker visual understanding, image enrichment for multimodal LLM vision input, and structured contact/vCard parsing.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Media download system with streaming, validation, retry, cache, and sticker vision. | — |
| cache.py | Core | Media download cache with LRU eviction. | ✅ |
| config.py | Config | Media download configuration; exposes shared `MAX_FORWARD_DOWNLOAD_BYTES` cap for cross-channel forwarding flows. | ✅ |
| contact_enrichment.py | Core | vCard contact attachment parsing (2.1/3.0/4.0) and enrichment; stores `metadata["contact_cards"]` for LLM context injection. | ✅ |
| downloader.py | Core | Core media downloader with streaming, SSRF-pinned fetch (`secure_fetch`), retry, cache, and metrics. | ✅ |
| exceptions.py | Core | Media download exceptions. | ✅ |
| image_enrichment.py | Core | Image attachment download via SSRF-safe `secure_get`, compression, and local file caching for multimodal LLM vision input. Owns the cache lifetime: receiving a cached image again restarts its age, and `sweep_channel_image_cache` removes files not received for `CHANNEL_IMAGE_RETENTION_DAYS` (30). It runs in the daily context cleanup job and once at server startup (`sweep_channel_image_cache_at_startup`, a maintenance-daemon task in a worker thread), because a machine that is off at 03:00 would never reach the daily job. | ✅ |
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
