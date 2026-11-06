"""[INPUT]
- app.core.utils.errors.* (POS: shared error primitives)

[OUTPUT]
- fold_user_home_paths, redact_error_payload, format_error_message, log_and_format_error

[POS]
API error utilities: home-path folding, payload redaction and error message formatting.
"""

from __future__ import annotations

import traceback

from myrm_agent_harness.api import redact_sensitive_text

from .constants import (
    _HOME_DIR_ROOT_RE,
    _HOME_DIR_UNIX_RE,
    _HOME_DIR_WIN_RE,
    logger,
)


def fold_user_home_paths(text: str) -> str:
    """Fold local user home paths (macOS/Linux/Windows) to '~' for privacy and concise UX."""
    if not text:
        return text
    text = _HOME_DIR_UNIX_RE.sub(r"\1~\2", text)
    text = _HOME_DIR_ROOT_RE.sub(r"\1~\2", text)
    text = _HOME_DIR_WIN_RE.sub(r"\1~\2", text)
    return text


def redact_error_payload(payload: object, max_depth: int = 10) -> object:
    """Recursively redact sensitive credentials and fold home directory paths in error payloads.

    Supports polymorphic payloads: str, dict, list, tuple, set, and primitive values.
    Limits recursion depth to prevent stack overflow on deeply nested payloads.
    """
    if max_depth <= 0:
        return "[TRUNCATED_NESTING]"

    if isinstance(payload, str):
        return fold_user_home_paths(redact_sensitive_text(payload))
    if isinstance(payload, dict):
        result: dict[str, object] = {}
        for k, v in payload.items():
            str_k = str(k)
            lower_k = str_k.lower()
            if any(term in lower_k for term in ("token", "secret", "password", "api_key", "apikey")) and isinstance(v, str):
                result[str_k] = "***REDACTED***"
            else:
                result[str_k] = redact_error_payload(v, max_depth - 1)
        return result
    if isinstance(payload, (list, tuple)):
        items = [redact_error_payload(item, max_depth - 1) for item in payload]
        return tuple(items) if isinstance(payload, tuple) else items
    if isinstance(payload, set):
        return [redact_error_payload(item, max_depth - 1) for item in payload]
    if isinstance(payload, (int, float, bool)) or payload is None:
        return payload
    return fold_user_home_paths(redact_sensitive_text(str(payload)))


def format_error_message(exception: Exception, context: str = "", include_traceback: bool = False) -> str:
    """格式化异常信息

    Args:
        exception: 异常对象
        context: 错误上下文描述
        include_traceback: 是否包含堆栈跟踪信息

    Returns:
        格式化后的错误信息字符串
    """
    error_type = type(exception).__name__
    error_msg = str(exception)

    # 如果异常的str()返回空字符串，使用repr()获取更多信息
    if not error_msg or error_msg.strip() == "":
        error_msg = repr(exception)

    # 如果仍然为空，提供默认错误信息
    if not error_msg or error_msg.strip() == "":
        error_msg = f"{error_type} occurred"

    if context:
        formatted_error = f"{context} - {error_type}: {error_msg}"
    else:
        formatted_error = f"{error_type}: {error_msg}"

    if include_traceback:
        tb = traceback.format_exc()
        formatted_error += f"\nStack trace:\n{tb}"

    return formatted_error


def log_and_format_error(
    exception: Exception,
    context: str = "",
    include_traceback: bool = False,
) -> str:
    """记录日志并格式化异常信息

    Args:
        exception: 异常对象
        context: 错误上下文描述
        include_traceback: 是否包含堆栈跟踪信息

    Returns:
        格式化后的错误信息字符串
    """
    formatted_error = format_error_message(exception, context, include_traceback)
    logger.warning(formatted_error)

    return formatted_error
