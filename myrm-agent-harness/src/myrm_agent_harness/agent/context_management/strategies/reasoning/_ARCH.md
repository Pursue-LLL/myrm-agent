# strategies/reasoning/

## Overview
Reasoning preservation strategy: Provider-agnostic thinking extraction, heuristic decision anchor mining, and immutable session ledger management.

## File Index

| File | Role | Description |
|------|------|-------------|
| `__init__.py` | Package | Export public data models and extraction APIs. |
| `anchor_extractor.py` | Extractor | Universal multi-provider reasoning extractor & heuristic decision anchor miner. Zero secondary LLM cost. The last-sentence fallback can be switched off (`tail_fallback=False`) for reasoning that leads into a tool call. |
| `anchor_ledger.py` | Ledger | Thread-safe, bounded session-scoped ledger for preserving core decision anchors across compaction. `render_for_turn(turn_key)` freezes the rendered block at the first sight of a turn key. |
| `_ARCH.md` | Doc | Architecture documentation. |

## Key Invariants
1. **Zero Secondary LLM Overhead**: All extraction operates in-memory via deterministic $O(N)$ linear scans.
2. **Multi-Provider Normalization**: Seamlessly normalizes Anthropic thinking blocks, DeepSeek/MiMo reasoning_content, Responses API items, and inline `<think>` tags.
3. **Prompt Cache Protection**: Extracted anchors are formatted into compact, immutable reference strings with stable prefixes.
