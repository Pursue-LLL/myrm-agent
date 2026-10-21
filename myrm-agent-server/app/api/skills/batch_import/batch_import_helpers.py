"""批量导入接口的共享错误处理辅助函数。

[INPUT]
- myrm_agent_harness.backends.skills.scanning.archive_security::classify_archive_security_issue / format_archive_security_user_message (POS: 归档安全扫描，异常→用户可读消息)

[OUTPUT]
- _resolve_batch_import_error_message: 解析异常为面向用户的安全/格式错误消息
- _build_batch_import_error_detail: 构造 400 错误 payload（message + error_code）

[POS]
批量导入（preview/confirm）路由层共用的错误映射辅助；无业务状态，纯函数。
"""

import logging

from myrm_agent_harness.backends.skills.scanning.archive_security import (
    ArchiveSecurityViolation,
    classify_archive_security_issue,
    format_archive_security_user_message,
)

logger = logging.getLogger(__name__)


def _resolve_batch_import_error_message(
    error: Exception,
    violation: ArchiveSecurityViolation | None = None,
) -> str:
    resolved_violation = violation if violation is not None else classify_archive_security_issue(error)
    if resolved_violation is not None:
        return format_archive_security_user_message(resolved_violation)
    detail = str(error).strip()
    if detail:
        return f"解析压缩包失败，防爆防护触发或格式错误: {detail}"
    return "解析压缩包失败，防爆防护触发或格式错误"


def _build_batch_import_error_detail(
    message: str,
    violation: ArchiveSecurityViolation | None = None,
) -> dict[str, str]:
    return {
        "message": message,
        "error_code": violation.code.value if violation is not None else "",
    }
