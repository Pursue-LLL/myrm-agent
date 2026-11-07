# summary/

## Overview
LLM-based structured summarization strategy with quality gate, circuit breaker, and message reconstruction.

## File Index

| File | Role | Description |
|------|------|-------------|
| `__init__.py` | Package | Re-exports public summary APIs. |
| `summarizer/` | Core | 结构化摘要子包（门面 + invocation/guard/summary/budget/audit）：LLM 调用与流式进度、辅助上下文裁剪、摘要生成、预算裁剪、全量/增量审计与指标；详见 [summarizer/_ARCH.md](summarizer/_ARCH.md) | ✅ |
| `summary_auditor.py` | Core | Quality gate that validates generated summaries for coverage, accuracy, and physical execution state consistency. |
| `execution_state_validator.py` | Core | Physical execution state consistency validator and auto-reconciler. Cross-checks summary against `ArtifactTracker` and tool outcomes (with secondary fallback extraction from `ToolMessage` artifacts, kwargs, and execution content) to prune hallucinated files and inject missing disk mutations. |
| `summary_builder.py` | Core | Message history reconstruction after summarisation (protected head extraction, compacted messages assembly, Split Turn aware recent tail extraction via `TailExtractionResult`). |
| `summary_parser.py` | Core | Summary format parsing and message-to-text formatting with credential redaction. Uses `parse_llm_json_object` (robust against fences, prose, bare control chars, trailing commas) for LLM responses and `require_key="user_goal"` for summary-message scans. Embedded `<!-- SUMMARY_JSON` block parsing tolerates literal `-->` inside JSON values (loop-until-parse), skips unparseable summary blocks, and locates the **last** parseable summary block (reverse scan) — compaction rebuilds always place the newest summary block at the latest position, so the last block is the freshest incremental-merge base and stale multi-block residuals never cause information loss. `extract_messages_after_summary` anchors on the same last-parseable block so incremental inputs stay aligned with the extracted summary. `_build_summary_from_dict` is the single source of truth for dict→`StructuredSummary` mapping (all 14 fields incl. `blocked_items`/`next_steps`); `parse_structured_summary_json` exposes the strict-JSON variant (None on failure) for business-layer persistence boundaries (server `compacted_summary`) so incremental-merge bases never drop fields. |
| `summary_prompts.py` | Core | Prompt templates for structured JSON summary and merge operations (including `SPLIT_TURN_PROMPT_SUFFIX` for ongoing active turns). |
| `summarize_circuit_guard.py` | Core | Circuit breaker shared by turn pipeline and server compact paths. |
| `progress_timeout.py` | Core | Progress-aware timeout primitives for detecting stalled summarization (InactivityTimeoutError, TotalCeilingTimeoutError). |
| `dropped_manifest.py` | Core | Dropped-constraint manifest builder for the compaction pipeline. Records redacted+truncated constraint snippets evicted by compaction so the GUI can distinguish "compaction dropped my constraint" from "the model ignored it" (fault-side attribution). Zero prompt cost — attached to StructuredSummary as audit metadata, excluded from `to_json()` so prompt-cache payloads never inflate. Exports `build_dropped_manifest` (pure) + `contains_constraint_marker` (shared matcher). |
| `exact_anchor.py` | Core | Deterministic machine symbol anchor extraction engine. Extracts Git commit SHAs, file paths, high severity error traces, code symbols, and API endpoints before compaction with quota safety limits and ReDoS protection. |

## Key Dependencies

- `...infra.schemas` (ContextConfig, StructuredSummary)
- `...tracking.artifact_tracker`
- `agent.config.llm_safety` (summary invocation re-pairs its prefix through `normalize_messages`)
- `security.detection.leak_detector`
