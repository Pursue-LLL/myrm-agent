# completion/

## Overview

Completion guard subsystem — finish gate, code verification, external evidence,
deliverable write claims, execution-claim grounding, per-turn evidence
disclosure, and mixed-message early termination. A held-back answer is routed
back to the model with the instruction delivered in the next model request
only (`completion_guard/directive_middleware.py`); no tool call stands in for it and
nothing is stored in the conversation.

The guard itself lives in `completion_guard/`. The deliverable (`deliverable_*`), execution-claim (`execution_claim_*`), query-grounding
and PPT verifiers below are consulted by it but have not been moved into that package (known residue).

Detailed design: [MIDDLEWARE_SYSTEM.md](../MIDDLEWARE_SYSTEM.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public exports for CompletionGuard and helpers. | — |
| `completion_guard/` | Package | The finish gate and everything only it uses: `CompletionGuard` (decision), `hold_back` (what a held-back draft becomes), `mixed_message` (Mixed Message Guard), `directive` + `directive_middleware` (the instruction the model reads, appended to the next request only), `checklist`, `verification`, `external_evidence`, `freshness`, `capabilities`, `rerun`, `state`, `events`, `safety`. See [completion_guard/_ARCH.md](completion_guard/_ARCH.md). | ✅ |
| `deliverable_auto_staging.py` | Internal | Automatic staging and LRU preservation for unwritten deliverables in `.myrm/staged_artifacts/`. | ✅ |
| `deliverable_confidence_tier.py` | Core | DeliverableConfidenceTier SSOT (VERIFIED, ARTIFACT, RESEARCH, PLAN), deterministic physical evidence resolver (measured 0.018 ms over a 66-record turn), and the disclosure policy (`should_disclose_tier`): evidence tiers are always shown, PLAN only when the answer itself makes a completion claim. | ✅ |
| `deliverable_write_verifier.py` | Internal | Zero-call deliverable write claim detection and unwritten deliverable heuristic sniffer. | ✅ |
| `execution_claim_verifier.py` | Internal | Completion-claim grounding against this run's tool records: verification claims (real test runners only; dry runs and zero-test outputs never ground a pass), outbound/irreversible action claims (MCP with outbound semantics, outbound commands, outbound tool names), and code-change claims (successful writes or shell mutations). Sentence-level scan with attribution/conditional/negation/explanation exclusions and request-intent gating for bare result forms; `has_completion_claim()` exposes the claim detection for the disclosure policy. | ✅ |
| `execution_claim_lexicon.py` | Internal | Declarative lexicons for the claim verifier: claim patterns, request-side intents, strict test-runner list, outbound command and tool-name vocabulary, and evidence-shape vetoes (dry runs, zero-test output, PATH rewrites, read-only MCP calls). | ✅ |
| `query_grounding_verifier.py` | Internal | Entity state/data query intent grounding and physical evidence verification (detects business entity queries e.g. orders/tickets/logistics, supports per-entity grounding map matching against tool arguments and outputs, blocks ungrounded hallucination when query tools were omitted or unsearched entities were fabricated, and halts fake success claims when query tools failed). | ✅ |
| `ppt_outline_verifier.py` | Internal | PPT reporting plan outline quality gate — detects PPT/slide-deck delivery and enforces the 4-dimensional rubric (concise titles, explicit takeaway per slide, concrete visual/data anchor, balanced density). | ✅ |

## Key Dependencies

- `agent.middlewares.tooling.tool_interceptor_middleware` — LoopGuard CallRecord window
- `agent.security.guards.loop_guard` — CallRecord, ToolGroup, VerificationCategory
- `toolkits.code_execution` — independent verification re-run sandbox
- `agent._internals.run_lifecycle.post_run_events` — attaches the per-turn disclosure payload via `attach_disclosure_to_event()` to the `message_end` event (the server persists it as message metadata)
