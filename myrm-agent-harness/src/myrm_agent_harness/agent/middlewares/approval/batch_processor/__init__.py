"""审批批处理门面。

[OUTPUT]
evaluate_tool_batch / apply_approval_decisions / build_interrupt_payload 以及测试依赖的内部函数。

[POS]
`app...approval.batch_processor` 的唯一入口；YOLO 分支在 yolo.py，其余决策在 core.py。
"""

from myrm_agent_harness.agent.middlewares.approval.batch_processor.core import (
    _evaluate_skill_hooks_for_tool,
    _get_runtime_domains,
    _run_llm_review,
    _truncate_tool_args,
    apply_approval_decisions,
    build_interrupt_payload,
    evaluate_tool_batch,
    register_security_reviewer,
    reset_runtime_domains,
)
from myrm_agent_harness.agent.middlewares.approval.batch_processor.yolo import operator_as_key_deny_message

__all__ = [
    "_evaluate_skill_hooks_for_tool",
    "_get_runtime_domains",
    "_run_llm_review",
    "_truncate_tool_args",
    "apply_approval_decisions",
    "build_interrupt_payload",
    "evaluate_tool_batch",
    "operator_as_key_deny_message",
    "register_security_reviewer",
    "reset_runtime_domains",
]
