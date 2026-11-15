# _media_shared/

## Overview
Provider mode-capability types, the normalization engine that video generation uses to fit requested parameters to the values a provider supports, and the single resolver that turns image and video references into validated bytes.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Provider mode-capability types and the normalization engine that video generation uses to fit requested parameters to the values a provider supports. | — |
| input_resolver.py | Core | The one entry that resolves image and video references (injected scheme loaders such as `media://`, paths inside allowed roots, `data:` images, http(s) through `secure_get`) to bytes: size checked before reading, magic bytes must be an image or video container, one image hook on the way out, any failing reference raises an error naming it. | ✅ |
| normalization.py | Core | Snaps a requested aspect ratio, size and duration to the closest values a provider mode declares as supported and reports each adjustment as a NormalizationRecord; video/generator.py applies it for providers that declare mode capabilities. | ✅ |
| types.py | Config | Defines the contract between provider capability declarations and the normalization engine. | — |

## Key Dependencies

- `core.security.http.secure_fetch` (SSRF-protected http(s) references), `utils.mime_types` (container sniffing); `types.py` and `normalization.py` use the standard library only.
