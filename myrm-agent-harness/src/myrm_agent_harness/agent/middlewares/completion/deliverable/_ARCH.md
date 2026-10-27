# deliverable/

## Overview

What an answer hands over, and whether the run backs it: the check for a save the run claimed or implied but never
made, the staging of unwritten drafts into the workspace when the completion guard lets the run finish, and the
evidence tier a delivery earns. Consulted by `completion_guard/` and by the per-turn disclosure.

Parent: [completion/_ARCH.md](../_ARCH.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public surface: the staging, tier and write-check names. | — |
| `auto_staging.py` | Internal | Automatic staging and LRU preservation for unwritten deliverables in `.myrm/staged_artifacts/`. | ✅ |
| `confidence_tier.py` | Core | DeliverableConfidenceTier SSOT (VERIFIED, ARTIFACT, RESEARCH, PLAN), deterministic physical evidence resolver (measured 0.018 ms over a 66-record turn), and the disclosure policy (`should_disclose_tier`): evidence tiers are always shown, PLAN only when the answer itself makes a completion claim. | ✅ |
| `write_verifier.py` | Internal | Zero-call deliverable write claim detection and unwritten deliverable heuristic sniffer. | ✅ |

## Key Dependencies

- `agent.security.guards.loop_guard` — CallRecord, SuccessLevel, ToolGroup, get_tool_group
