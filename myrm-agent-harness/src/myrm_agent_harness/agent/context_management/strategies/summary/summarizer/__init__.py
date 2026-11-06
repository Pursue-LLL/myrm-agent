"""[INPUT]
- myrm_agent_harness.agent.context_management.strategies.summary.summarizer.audit::_log_merge_quality / _record_summarize_to_metrics / _summarize_full_with_audit / _summarize_incremental_with_audit (POS: 摘要策略子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.agent.context_management.strategies.summary.summarizer.budget::_build_budget_hint / _cap_summary_if_needed (POS: 摘要策略子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.agent.context_management.strategies.summary.summarizer.guard::_guard_aux_context / should_summarize (POS: 摘要策略子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.agent.context_management.strategies.summary.summarizer.invocation::_build_summary_invocation_messages / _coerce_to_structured_summary / _FallbackSummaryModel / _get_structured_llm_or_parser / _invoke_summary / _redact_summary_fields / _stream_with_progress (POS: 摘要策略子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.agent.context_management.strategies.summary.summarizer.summary::generate_structured_summary (POS: 摘要策略子包的一部分；由 __init__.py 聚合导出。)

[OUTPUT]
- _log_merge_quality
- _record_summarize_to_metrics
- _summarize_full_with_audit
- _summarize_incremental_with_audit
- _build_budget_hint
- _cap_summary_if_needed
- _guard_aux_context
- should_summarize
- _build_summary_invocation_messages
- _coerce_to_structured_summary
- _FallbackSummaryModel
- _get_structured_llm_or_parser
- _invoke_summary
- _redact_summary_fields
- _stream_with_progress
- generate_structured_summary

[POS]
`...summary.summarizer` 的唯一入口；实现按调用/守卫/生成/审计分层。
"""

from myrm_agent_harness.agent.context_management.strategies.summary.summarizer.audit import (
    _log_merge_quality,
    _record_summarize_to_metrics,
    _summarize_full_with_audit,
    _summarize_incremental_with_audit,
)
from myrm_agent_harness.agent.context_management.strategies.summary.summarizer.budget import (
    _build_budget_hint,
    _cap_summary_if_needed,
)
from myrm_agent_harness.agent.context_management.strategies.summary.summarizer.guard import (
    _guard_aux_context,
    should_summarize,
)
from myrm_agent_harness.agent.context_management.strategies.summary.summarizer.invocation import (
    _build_summary_invocation_messages,
    _coerce_to_structured_summary,
    _FallbackSummaryModel,
    _get_structured_llm_or_parser,
    _invoke_summary,
    _redact_summary_fields,
    _stream_with_progress,
)
from myrm_agent_harness.agent.context_management.strategies.summary.summarizer.summary import (
    generate_structured_summary,
)

__all__ = [
    "_FallbackSummaryModel",
    "_build_budget_hint",
    "_build_summary_invocation_messages",
    "_cap_summary_if_needed",
    "_coerce_to_structured_summary",
    "_get_structured_llm_or_parser",
    "_guard_aux_context",
    "_invoke_summary",
    "_log_merge_quality",
    "_record_summarize_to_metrics",
    "_redact_summary_fields",
    "_stream_with_progress",
    "_summarize_full_with_audit",
    "_summarize_incremental_with_audit",
    "generate_structured_summary",
    "should_summarize",
]
