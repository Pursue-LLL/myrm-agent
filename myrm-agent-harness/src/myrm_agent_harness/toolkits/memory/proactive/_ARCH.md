# memory/proactive/

## Overview

Proactive follow-up tracking — LLM extraction of implicit commitments from conversations.
Lives under `toolkits/memory/` as a separate persistence track (records persisted by the host, e.g. in SQLite), gated by `enable_memory`.
Harness supplies types and extraction; hosts persist the records and implement session hooks and heartbeat delivery.

Detailed design: [COMMITMENT_SYSTEM.md](COMMITMENT_SYSTEM.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Commitment tracking public API. | — |
| config.py | Config | Extraction thresholds and batch limits. | ✅ |
| extraction.py | Core | LLM-based commitment extraction from conversation messages. | ✅ |
| types.py | Core | `CommitmentRecord`, kinds, status lifecycle, due windows. | ✅ |

## Boundaries

- **Core IP (release wheels)**: compiled via `harness_packaging/core_manifest.yaml` → `toolkits/memory/proactive`
- **Reuses**: injected async LLM callback only (no harness LLM factory coupling)
- **Does not import**: `agent/`, `runtime/`, `backends/`
- **Host implements**: record persistence, session hook timing, REST/GUI, heartbeat delivery

## Key Dependencies

- `pydantic` (structured extraction and records)
- `utils.json_parsing` (`parse_llm_json_object` — 容错 LLM 回复 JSON 解析)
- stdlib: `datetime`, `logging`
