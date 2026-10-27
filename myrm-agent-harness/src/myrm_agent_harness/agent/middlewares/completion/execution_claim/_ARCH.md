# execution_claim/

## Overview

A finished answer that says what the run did must be backed by what the run did. The verifier grounds three families
of claims (verification results, outbound or irreversible actions, code changes) in this run's own tool records, and
the lexicon holds the patterns it reads. Consulted by `completion_guard/` and by the disclosure policy.

Parent: [completion/_ARCH.md](../_ARCH.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public surface: `check_execution_claim`, `has_completion_claim`. | — |
| `verifier.py` | Internal | Completion-claim grounding against this run's tool records: verification claims (real test runners only; dry runs and zero-test outputs never ground a pass), outbound/irreversible action claims (MCP with outbound semantics, outbound commands, outbound tool names), and code-change claims (successful writes or shell mutations). Sentence-level scan with attribution/conditional/negation/explanation exclusions and request-intent gating for bare result forms; `has_completion_claim()` exposes the claim detection for the disclosure policy. | ✅ |
| `lexicon.py` | Internal | Declarative lexicons for the claim verifier: claim patterns, request-side intents, strict test-runner list, outbound command and tool-name vocabulary, and evidence-shape vetoes (dry runs, zero-test output, PATH rewrites, read-only MCP calls). | ✅ |

## Key Dependencies

- `agent.security.guards.loop_guard` — CallRecord, SuccessLevel, ToolGroup, VerificationCategory, get_tool_group
- `toolkits.mcp.config` — `is_mcp_tool_name`
