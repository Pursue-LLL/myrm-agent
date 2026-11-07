"""[INPUT]
- .circuit_breaker (POS: 熔断状态读写)
- .fallback (POS: 确定性摘要)
- .guard (POS: 超时保护调用)
- .processor (POS: 摘要处理器实现)

[OUTPUT]
- SummarizeProcessor: 结构化会话摘要处理器
- 熔断与降级函数（供框架守卫与测试使用）

[POS]
`...processors.summarize_processor` 的唯一入口；实现按熔断/降级/守卫/处理器分层。
"""

from myrm_agent_harness.agent.context_management.pipeline.processors.summarize_processor.circuit_breaker import (
    MAX_CONSECUTIVE_SUMMARIZE_FAILURES,
    _classify_error_type,
    _get_failures,
    _is_circuit_open,
    _is_half_open_probe,
    _record_fallback_call,
    _set_failures,
)
from myrm_agent_harness.agent.context_management.pipeline.processors.summarize_processor.fallback import (
    _build_deterministic_summary,
    _extract_focus_topic,
)
from myrm_agent_harness.agent.context_management.pipeline.processors.summarize_processor.processor import (
    SummarizeProcessor,
)

__all__ = [
    "MAX_CONSECUTIVE_SUMMARIZE_FAILURES",
    "SummarizeProcessor",
    "_build_deterministic_summary",
    "_classify_error_type",
    "_extract_focus_topic",
    "_get_failures",
    "_is_circuit_open",
    "_is_half_open_probe",
    "_record_fallback_call",
    "_set_failures",
]
