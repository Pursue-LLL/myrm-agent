"""[INPUT]
- .cache (POS: 缓存配置)
- .callbacks (POS: 回调协议)
- .config (POS: 上下文配置)
- .offload (POS: offload 类型)
- ..schemas_pre_compact (POS: 预压缩三态决策契约)
- .summary (POS: 摘要模型)
- .tool_protection (POS: 工具保护)

[OUTPUT]
- 上下文管理的全部配置、模型与回调协议

[POS]
`myrm_agent_harness.agent.context_management.infra.schemas` 的唯一门面；实现按配置/保护/缓存/offload/摘要/回调分层。
"""

from myrm_agent_harness.agent.context_management.infra.schemas.cache import (
    DEFAULT_CACHE_TTL_PRUNE_CONFIG,
    CacheTtlPruneConfig,
    CacheUsageFeedback,
)
from myrm_agent_harness.agent.context_management.infra.schemas.callbacks import (
    ContextCompressEvictionCallback,
    ContextCompressOffloadCallback,
    ContextSnapshotCallback,
    SummaryPersistCallback,
)
from myrm_agent_harness.agent.context_management.infra.schemas.config import (
    COMPRESS_MIN_SAVE_DEFAULT,
    DEFAULT_CONTEXT_CONFIG,
    ContextConfig,
    get_compress_min_save_for_model,
)
from myrm_agent_harness.agent.context_management.infra.schemas.offload import (
    ContextOffloadFailureKind,
    ContextOffloadResult,
    EvictedToolCall,
    normalize_context_offload_result,
)
from myrm_agent_harness.agent.context_management.infra.schemas.summary import (
    CompactToolCall,
    CompressionIntent,
    StructuredSummary,
)
from myrm_agent_harness.agent.context_management.infra.schemas.tool_protection import (
    BUILTIN_ACTIVE_PRUNE_NEVER_TOOLS,
    BUILTIN_FILTER_PROTECTED_TOOLS,
    BUILTIN_PROTECTED_TOOLS,
    DEFAULT_BUSINESS_PROTECTED_TOOLS,
    DEFAULT_SOFT_ONLY_TOOLS,
    TOOL_PROTECTION_CONFIG,
    ToolProtectionConfig,
    ToolPruneMode,
)
from myrm_agent_harness.agent.context_management.infra.schemas_pre_compact import (
    CANCEL_COMPACTION_METADATA_KEY,
    PRE_COMPACT_DECISION_METADATA_KEY,
    PRE_COMPACT_INJECTION_METADATA_KEY,
    PRE_COMPACT_MESSAGE_METADATA_KEY,
    PRE_COMPACT_REPLACEMENT_SUMMARY_METADATA_KEY,
    ContextPreCompactCallback,
    PreCompactAction,
    PreCompactDecision,
    PreCompactInjection,
    normalize_pre_compact_decision,
)

__all__ = [
    "BUILTIN_ACTIVE_PRUNE_NEVER_TOOLS",
    "BUILTIN_FILTER_PROTECTED_TOOLS",
    "BUILTIN_PROTECTED_TOOLS",
    "CANCEL_COMPACTION_METADATA_KEY",
    "COMPRESS_MIN_SAVE_DEFAULT",
    "DEFAULT_BUSINESS_PROTECTED_TOOLS",
    "DEFAULT_CACHE_TTL_PRUNE_CONFIG",
    "DEFAULT_CONTEXT_CONFIG",
    "DEFAULT_SOFT_ONLY_TOOLS",
    "PRE_COMPACT_DECISION_METADATA_KEY",
    "PRE_COMPACT_INJECTION_METADATA_KEY",
    "PRE_COMPACT_MESSAGE_METADATA_KEY",
    "PRE_COMPACT_REPLACEMENT_SUMMARY_METADATA_KEY",
    "TOOL_PROTECTION_CONFIG",
    "CacheTtlPruneConfig",
    "CacheUsageFeedback",
    "CompactToolCall",
    "CompressionIntent",
    "ContextCompressEvictionCallback",
    "ContextCompressOffloadCallback",
    "ContextConfig",
    "ContextOffloadFailureKind",
    "ContextOffloadResult",
    "ContextPreCompactCallback",
    "ContextSnapshotCallback",
    "EvictedToolCall",
    "PreCompactAction",
    "PreCompactDecision",
    "PreCompactInjection",
    "StructuredSummary",
    "SummaryPersistCallback",
    "ToolProtectionConfig",
    "ToolPruneMode",
    "get_compress_min_save_for_model",
    "normalize_context_offload_result",
    "normalize_pre_compact_decision",
]
