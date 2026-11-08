# _media_shared/

## Overview
Shared across video/ and image/ modules. Keeps media-specific logic

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Shared across video/ and image/ modules. Keeps media-specific logic | — |
| normalization.py | Core | Used by video/generator.py and future image/generator.py to normalize | ✅ |
| types.py | Config | These types are imported by video/models.py and normalization.py. | — |

## Key Dependencies

- Standard library only.
