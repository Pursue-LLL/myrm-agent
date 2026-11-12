# _media_shared/

## Overview
Provider mode-capability types and the normalization engine that video generation uses to fit requested parameters to the values a provider supports.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Provider mode-capability types and the normalization engine that video generation uses to fit requested parameters to the values a provider supports. | — |
| normalization.py | Core | Snaps a requested aspect ratio, size and duration to the closest values a provider mode declares as supported and reports each adjustment as a NormalizationRecord; video/generator.py applies it for providers that declare mode capabilities. | ✅ |
| types.py | Config | Defines the contract between provider capability declarations and the normalization engine. | — |

## Key Dependencies

- Standard library and this package only.
