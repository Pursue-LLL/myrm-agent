"""Context management module.

提供上下文过滤、压缩、摘要等功能，用于管理 Agent 的上下文窗口。

核心组件：
1. infra: 共享 schema、预算与保留策略、会话锁、归档引用、缓存策略
2. strategies: 三层降载策略与辅助策略
   - filter / filters: 大型工具结果过滤（结构化数据用 StructuralFilter，非结构化数据用 SemanticFilter + LLM）
   - compactor / compression: 去重、按优先级紧凑化旧工具结果、智能回退与防抖保护
   - summary: 结构化摘要（最后手段）
   - session_notes / reasoning: 会话笔记与推理锚点
3. pipeline: 有序处理器链
   - ContextPipeline: 管道引擎
   - 统一 builder: build_default_processors / create_default_pipeline（处理器清单见 pipeline/processors/_ARCH.md）
4. tracking: 工件追踪与任务指标
5. archive_checkpoint / pre_compact_service / preheat: 归档摘要、压缩前召回、前缀缓存预热

设计理念：
- 过滤 (Filtering) 是立即的：大结果截断 + 智能预览
- 压缩 (Compression)：确定性规则，不调用 LLM；原文经 ContextCompressOffloadCallback 落盘后，旧工具结果再紧凑化为标识符 + 元信息存根（有损但可追溯）
  - 工具特定模板（保留标识符和元信息）
  - 最小清理保护（避免小清理破坏 Prompt Cache）
- 摘要 (Summarization) 是不可逆的：原始消息结构被替换，无法恢复
- 保留最近 N 次工具调用的完整格式，作为 few-shot 示例
"""

from .context import AgentContext
from .eviction_marks import (
    IMMUNE_MARKS,
    EvictionMark,
    get_message_marks,
    has_message_marks,
    is_eviction_immune,
    with_message_marks,
)
from .infra.archive_reference import ContextArchiveReference
from .infra.cache_policy import CacheTtlPrunePolicy, resolve_cache_ttl_prune_policy
from .infra.schemas import (
    BUILTIN_PROTECTED_TOOLS,
    DEFAULT_BUSINESS_PROTECTED_TOOLS,
    DEFAULT_CONTEXT_CONFIG,
    DEFAULT_SOFT_ONLY_TOOLS,
    TOOL_PROTECTION_CONFIG,
    CacheUsageFeedback,
    CompactToolCall,
    CompressionIntent,
    ContextCompressOffloadCallback,
    ContextConfig,
    ContextOffloadResult,
    ContextSnapshotCallback,
    StructuredSummary,
    ToolProtectionConfig,
    ToolPruneMode,
)
from .infra.session_lock import (
    acquire_context_lock,
    clear_all_locks,
    get_active_session_count,
    get_current_chat_id,
    get_locked_session_count,
    get_session_lock,
    reset_current_chat_id,
    set_current_chat_id,
)

# Pipeline 架构
from .pipeline import (
    BaseProcessor,
    CompressProcessor,
    ContextPipeline,
    ExplicitCacheProcessor,
    FilterProcessor,
    ProcessorContext,
    ReasoningAnchorProcessor,
    SessionNotesProcessor,
    SummarizeProcessor,
    ThinkingBlockCleaner,
    build_default_processors,
    create_default_pipeline,
)
from .strategies.compactor import (
    COMPACT_RULES,
    compress_messages_async,
    compress_tool_message_async,
)
from .strategies.filter import (
    FILTER_TOKEN_THRESHOLD,
    FilteredResult,
    create_filtered_result,
    format_filtered_message,
    should_filter,
)
from .strategies.filters import BaseFilter, FilterContext, FilterResult, SemanticFilter, StructuralFilter
from .strategies.filters.base import SEMANTIC_CONTENT_TYPES, STRUCTURAL_CONTENT_TYPES, detect_content_type
from .strategies.summary.summarizer import generate_structured_summary, should_summarize
from .title_recovery import (
    InvalidGeneratedTitleRecoverySuite,
    InvalidTitleReason,
    InvalidTitleTaxonomy,
    ProvisionalTitleRetryGate,
    TitleRecoveryConfig,
    TitleRecoveryState,
    TitleRecoveryVerdict,
    TitleValidationResult,
)
from .tracking.artifact_tracker import (
    ArtifactAction,
    ArtifactRecord,
    ArtifactTracker,
    clear_artifact_tracker,
    create_artifact_tracker,
    get_all_active_trackers,
    get_artifact_tracker,
    get_or_create_artifact_tracker,
)
from .tracking.task_metrics import (
    ArchiveRestoreBlockEvent,
    CompressionEvent,
    RefetchEvent,
    TaskMetrics,
    clear_task_metrics,
    create_task_metrics,
    get_all_active_metrics,
    get_or_create_task_metrics,
    get_task_metrics,
    record_archive_refetch_for_path,
)

__all__ = [
    # schemas
    "BUILTIN_PROTECTED_TOOLS",
    "COMPACT_RULES",
    "DEFAULT_BUSINESS_PROTECTED_TOOLS",
    "DEFAULT_CONTEXT_CONFIG",
    "DEFAULT_SOFT_ONLY_TOOLS",
    # filter
    "FILTER_TOKEN_THRESHOLD",
    "SEMANTIC_CONTENT_TYPES",
    "STRUCTURAL_CONTENT_TYPES",
    "TOOL_PROTECTION_CONFIG",
    # context
    "AgentContext",
    "ArchiveRestoreBlockEvent",
    # artifact_tracker
    "ArtifactAction",
    "ArtifactRecord",
    "ArtifactTracker",
    # filters
    "BaseFilter",
    "BaseProcessor",
    "CacheTtlPrunePolicy",
    "CacheUsageFeedback",
    "CompactToolCall",
    "CompressProcessor",
    "CompressionEvent",
    "CompressionIntent",
    "ContextArchiveReference",
    "ContextCompressOffloadCallback",
    "ContextConfig",
    "ContextOffloadResult",
    # pipeline
    "ContextPipeline",
    "ContextSnapshotCallback",
    "ExplicitCacheProcessor",
    "FilterContext",
    "FilterProcessor",
    "FilterResult",
    "FilteredResult",
    "IMMUNE_MARKS",
    "ProcessorContext",
    "ReasoningAnchorProcessor",
    "RefetchEvent",
    "SemanticFilter",
    "SessionNotesProcessor",
    "StructuralFilter",
    "StructuredSummary",
    "SummarizeProcessor",
    # task_metrics
    "TaskMetrics",
    "ThinkingBlockCleaner",
    "ToolProtectionConfig",
    "ToolPruneMode",
    "EvictionMark",
    "acquire_context_lock",
    "build_default_processors",
    "clear_all_locks",
    "clear_artifact_tracker",
    "clear_task_metrics",
    "compress_messages_async",
    "compress_tool_message_async",
    "create_artifact_tracker",
    "create_default_pipeline",
    "create_filtered_result",
    "create_task_metrics",
    "detect_content_type",
    "format_filtered_message",
    "generate_structured_summary",
    "get_active_session_count",
    "get_all_active_metrics",
    "get_all_active_trackers",
    "get_artifact_tracker",
    "get_current_chat_id",
    "get_locked_session_count",
    "get_message_marks",
    "get_or_create_artifact_tracker",
    "get_or_create_task_metrics",
    # session_lock
    "get_session_lock",
    "get_task_metrics",
    "has_message_marks",
    "is_eviction_immune",
    "record_archive_refetch_for_path",
    "reset_current_chat_id",
    "resolve_cache_ttl_prune_policy",
    "with_message_marks",
    "set_current_chat_id",
    # filter
    "should_filter",
    # summarizer
    "should_summarize",
    # title_recovery
    "InvalidGeneratedTitleRecoverySuite",
    "InvalidTitleReason",
    "InvalidTitleTaxonomy",
    "ProvisionalTitleRetryGate",
    "TitleRecoveryConfig",
    "TitleRecoveryState",
    "TitleRecoveryVerdict",
    "TitleValidationResult",
]
