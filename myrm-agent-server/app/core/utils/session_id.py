"""Safe session-id validation for filesystem path interpolation.

[INPUT]
- (none)

[OUTPUT]
- is_safe_session_id: validate a session/chat id (any value; non-strings are rejected) as a safe filesystem path component

[POS]
通用安全工具。为任何把 session_id/chat_id 拼进文件路径的调用方提供统一白名单校验，
防止路径穿越（`..`/反斜杠/空字节）逃逸出日志目录，并拒绝超过文件名长度上限的标识。
"""

from __future__ import annotations

import re

# Session IDs are server-generated opaque handles (UUID hex, kanban task ids,
# `oai-session-*`, `cron:*`). Restricting the allowed character set prevents a
# crafted ID from escaping the event-log directory via `..` / backslashes when
# it is interpolated into a filesystem path below. The 255-character cap is the
# width of the `chats.id` column, so every stored chat id passes, and the
# file-name length limit of the filesystems the ids are written to.
_SESSION_ID_RE = re.compile(r"[A-Za-z0-9:_-]{1,255}")


def is_safe_session_id(session_id: object) -> bool:
    """Return True only if ``session_id`` is a safe filesystem path component.

    Rejects path traversal (`..`), backslashes, NUL bytes, any character
    outside the whitelist and ids longer than 255 characters. A ``False``
    return means the id must never be interpolated into a path. Non-string
    inputs (e.g. ``None``) also return ``False`` so callers never surface a
    TypeError from a hot path.
    """
    if not isinstance(session_id, str):
        return False
    return bool(_SESSION_ID_RE.fullmatch(session_id))


__all__ = ["is_safe_session_id"]
