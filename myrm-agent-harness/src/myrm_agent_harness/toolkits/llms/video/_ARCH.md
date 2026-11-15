# video/

## Overview
Video generation module — multi-provider video generation with failover. Generation is the async task path: `async_video_engine.py` enqueues, a worker runs `generator.py`.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Video generation module — multi-provider video generation with failover. | ✅ |
| `_helpers.py` | Internal | Used by generator.py for retry logic, error formatting, content validation, and non-retryable classification (including ModerationBlockedError). | ✅ |
| `_overrides.py` | Internal | Pure `sanitize_overrides`: fits aspect ratio, resolution, duration, audio and reference inputs to what a provider declares, reporting ignored overrides and normalizations. | ✅ |
| `generator.py` | Core | Video generation orchestrator with ModerationBlockedError fast-fail dispatch; stores the winning result once through the primary media callback (fail-closed). | ✅ |
| `models.py` | Core | Pure data types with no business logic. Includes ModerationBlockedError and ProviderCapabilities. | ✅ |
| `async_video_engine.py` | Core | Async enqueue adapter: returns the task id of the created video task. | ✅ |
| `video_engine.py` | Core | Provider discovery (`list_providers`) for the server `media_tools/` adapter. | ✅ |

| Submodule | Description |
|-----------|-------------|
| providers/ | Video generation providers — pluggable backends for video generation. |

## Key Dependencies

- `core.security.http.secure_fetch` (secure_get/secure_request for result URL downloads in the providers, with `max_content_length` cap and `ContentTooLargeError` handling)
- `core`
