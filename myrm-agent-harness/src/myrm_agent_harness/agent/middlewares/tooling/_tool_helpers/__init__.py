"""[INPUT]
- .helpers (POS: 错误分类、校验、PII 与信任衰减)
- .hook_results (POS: hook 结果与事件)
- .timeouts (POS: 超时策略)
- .truncation (POS: 文本截断与提取)

[OUTPUT]
- 工具拦截中间件使用的全部无状态助手

[POS]
`myrm_agent_harness.agent.middlewares.tooling._tool_helpers` 的唯一门面；实现按职责分层。
"""

from myrm_agent_harness.agent.middlewares.tooling._tool_helpers.helpers import (
    _CONFIG_OR_AUTH_FAMILY_BROWSER,
    _CONFIG_OR_AUTH_FAMILY_SEARCH,
    NON_RETRYABLE_ERRORS,
    TERMINAL_CONFIG_OR_AUTH,
    apply_validation_result,
    check_semantic_failure_retryable,
    check_tool_params_pii,
    check_tool_result_pii,
    check_trust_attenuation,
    classify_terminal_error,
    format_tool_error,
    is_non_retryable,
    is_semantic_business_error,
    make_error_msg,
    run_content_validation,
)
from myrm_agent_harness.agent.middlewares.tooling._tool_helpers.hook_results import (
    build_hook_failure_result,
    emit_archive_restore_block_status,
    emit_hook_failure_event,
)
from myrm_agent_harness.agent.middlewares.tooling._tool_helpers.timeouts import get_tool_timeout
from myrm_agent_harness.agent.middlewares.tooling._tool_helpers.truncation import (
    extract_text_content,
    smart_truncate_output,
)

__all__ = [
    "NON_RETRYABLE_ERRORS",
    "TERMINAL_CONFIG_OR_AUTH",
    "_CONFIG_OR_AUTH_FAMILY_BROWSER",
    "_CONFIG_OR_AUTH_FAMILY_SEARCH",
    "apply_validation_result",
    "build_hook_failure_result",
    "check_semantic_failure_retryable",
    "check_tool_params_pii",
    "check_tool_result_pii",
    "check_trust_attenuation",
    "classify_terminal_error",
    "emit_archive_restore_block_status",
    "emit_hook_failure_event",
    "extract_text_content",
    "format_tool_error",
    "get_tool_timeout",
    "is_non_retryable",
    "is_semantic_business_error",
    "make_error_msg",
    "run_content_validation",
    "smart_truncate_output",
]
