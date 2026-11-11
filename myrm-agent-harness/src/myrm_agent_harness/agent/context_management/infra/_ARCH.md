# infra/

## Overview
Context management infrastructure: shared types, budget management, session locks, and optional cache metrics persistence.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Context management infrastructure: shared types, budget management, session locks, and optional cache metrics persistence. | — |
| cache_break_detector.py | Core | Prompt cache break detection and attribution. Detects cache drops and attributes to system prompt change, tool schema change, model switch, an edited earlier message (``record_message_prefix`` + ``prefix_chain``), or TTL expiry. Works with ``toolkits/mcp/schema.normalize.canonicalize_schema_for_cache`` to form a prevention+detection closed loop. | ✅ |
| archive_reference.py | Core | Structured archive references and restore contracts for offloaded context payloads, including lightweight line/chunk, JSON, Markdown, code block, table, and list indexes plus chunk restore args for targeted recovery. | ✅ |
| cache_policy.py | Core | Framework-level prompt cache policy profile resolution for context pruning with provider TTL calibration metadata. The Claude profile does not start a prune because a cache looks cold (`cold_cache_prune_enabled=False`): the reasoning a Claude route signs binds every earlier message, and the prune lasts one request. Context pressure still prunes. | ✅ |
| cache_metrics_collector.py | Core | Request-scoped pairing via ContextVar (same asyncio task as token tracker). Each NDJSON record carries the call's ``cache_creation_tokens`` and, when the request edited an earlier message, its ``prefix_shift``. | ✅ |
| context_budget.py | Core | Context budget via estimate_context_tokens; resolve_budget_kwargs_from_metadata + estimate_processor_context_tokens for pipeline SSOT; DEFAULT_ESTIMATED_REMAINING_TURNS shared by runtime + preflight dynamic threshold. | ✅ |
| compactor_guard.py | Core | Compactor preflight safety evaluation fence protecting against ContextLengthExceeded crashes caused by compounding message history and skill overhead. | ✅ |
| prefix_chain.py | Core | ``message_digests`` (one digest per message, blind to ``cache_control`` breakpoints) and ``find_prefix_shift`` (the first message where a request stopped extending the previous one; ``PrefixShift.announced`` says whether the context pipeline had announced the rewrite). Provider caches match a byte-identical prefix, so this names the edit that made a request pay full price. | ✅ |
| message_priority.py | Core | Message priority classification for intelligent compression. | ✅ |
| schemas/ | Config | 上下文管理类型子包：`config.py`（窗口与压缩阈值）、`tool_protection.py`（不可压缩工具）、`cache.py`（TTL 裁剪与缓存反馈）、`offload.py`（offload/eviction）、`summary.py`（结构化摘要）、`callbacks.py`（依赖反转协议）；门面保持原导入面并继续重导出 pre-compact 名称。详见 [schemas/_ARCH.md](schemas/_ARCH.md) | ✅ |
| schemas_pre_compact.py | Config | PreCompactDecision (Cancel/Replace/Passthrough) + PreCompactInjection + ContextPreCompactCallback types | ✅ |
| session_lock.py | Core | Session-level lock manager. Provides reentrant per-session async locks for serialized context mutations while preserving cross-session parallelism. | ✅ |
| retention_helpers.py | Core | Shared retention helpers: compression_intent extraction (failed/focus/goal), group-aware focus matching via tool_call_id index, keep_recent prune cutoff, deterministic retain trim formatting (the "full output saved to" pointer is emitted only when a saved copy exists) | ✅ |
| tool_result_trimming.py | Core | Deterministic trimming for oversized tool outputs. Uses structure-aware JSON compaction under the fast-guard threshold and bounded head/tail text trim above it. | ✅ |
| evicted/ | Submodule | UECD subpackage — see [evicted/_ARCH.md](evicted/_ARCH.md) (`content` · `reader` · `persister` · `markers`) | ✅ |

## Key Dependencies

- `infra`
- `utils`
