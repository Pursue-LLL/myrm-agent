# eviction_marks/

## Overview
Message-level working-memory marks: metadata tags that keep selected messages immune to
context eviction. Pure in-memory primitives with zero LLM overhead.

## File Index

| File | Role | Description |
|------|------|-------------|
| `marks.py` | Marks Metadata Contract | `EvictionMark` enum, `IMMUNE_MARKS` set, and message-level mark manipulation (with/remove), inspection, and immunity primitives. |
| `__init__.py` | Package Exports | Public exports for context-management consumers. |

## Key Invariants
1. **Zero-LLM Overhead**: All operations execute in pure Python memory without invoking external models.
2. **Eviction contract**: `is_eviction_immune()` is the single predicate selective-eviction processors consult.
3. **Metadata-only**: Marks live on message `additional_kwargs`; they never mutate message content or the static prompt prefix.
