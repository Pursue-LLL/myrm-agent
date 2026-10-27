# completion/

## Overview

Completion guard subsystem — finish gate, code verification, external evidence,
deliverable write claims, execution-claim grounding, per-turn evidence
disclosure, and mixed-message early termination. A held-back answer is routed
back to the model with the instruction delivered in the next model request
only (`completion_guard/directive_middleware.py`); no tool call stands in for it and
nothing is stored in the conversation.

The guard lives in `completion_guard/`, the deliverable checks in `deliverable/`, the claim grounding in `execution_claim/`;
the query-grounding verifier is a single file kept here.

Detailed design: [MIDDLEWARE_SYSTEM.md](../MIDDLEWARE_SYSTEM.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public exports for CompletionGuard and helpers. | — |
| `completion_guard/` | Package | The finish gate and everything only it uses: `CompletionGuard` (decision), `hold_back` (what a held-back draft becomes), `mixed_message` (Mixed Message Guard), `directive` + `directive_middleware` (the instruction the model reads, appended to the next request only), `checklist`, `record_rules`, `verification`, `external_evidence`, `freshness`, `capabilities`, `rerun`, `state`, `events`, `safety`. See [completion_guard/_ARCH.md](completion_guard/_ARCH.md). | ✅ |
| `deliverable/` | Package | What an answer hands over and whether the run backs it: the write-claim and unwritten-deliverable checks, the staging of unwritten drafts, and the evidence tier with its disclosure policy. See [deliverable/_ARCH.md](deliverable/_ARCH.md). | ✅ |
| `execution_claim/` | Package | Grounding of completion claims (verification results, outbound actions, code changes) in this run's tool records, with the claim lexicon. See [execution_claim/_ARCH.md](execution_claim/_ARCH.md). | ✅ |
| `query_grounding_verifier.py` | Internal | Entity state/data query intent grounding and physical evidence verification (detects business entity queries e.g. orders/tickets/logistics, supports per-entity grounding map matching against tool arguments and outputs, blocks ungrounded hallucination when query tools were omitted or unsearched entities were fabricated, and halts fake success claims when query tools failed). | ✅ |

## Key Dependencies

- `agent.middlewares.tooling.tool_interceptor_middleware` — LoopGuard CallRecord window (merged into the turn's call ledger on every model turn)
- `agent.security.guards.loop_guard` — CallRecord, ToolGroup, VerificationCategory
- `toolkits.code_execution` — independent verification re-run sandbox
- `agent._internals.run_lifecycle.post_run_events` — attaches the per-turn disclosure payload via `attach_disclosure_to_event()` to the `message_end` event (the server persists it as message metadata)
