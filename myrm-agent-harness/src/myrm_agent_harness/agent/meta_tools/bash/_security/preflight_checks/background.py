"""识别未加引号的后台 & 运算符。

[POS]
bash 预检子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def check_unquoted_background_ampersand(command: str) -> str | None:
    """Detect unquoted background ampersand operators that would detach orphan processes.

    Skips:
    - Double ampersands: ``&&`` (logical AND)
    - Redirection targets/syntax: ``2>&1``, ``>&``, ``&>``
    - Quoted ampersands: ``"..."``, ``'...'``
    - Trailing background ampersand (which is safely handled by ``strip_trailing_background_ampersand``)

    Returns:
        An error message if a detached/intermediate background ampersand is detected, else None.
    """
    cleaned = command.rstrip()
    if cleaned.endswith("&") and not cleaned.endswith("&&"):
        cleaned = cleaned[:-1].rstrip()

    in_single_quote = False
    in_double_quote = False
    escaped = False
    length = len(cleaned)
    i = 0

    while i < length:
        char = cleaned[i]

        if escaped:
            escaped = False
            i += 1
            continue

        if char == "\\":
            escaped = True
            i += 1
            continue

        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            i += 1
            continue

        if char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            i += 1
            continue

        if not in_single_quote and not in_double_quote and char == "&":
            # Check if this is '&&'
            if i + 1 < length and cleaned[i + 1] == "&":
                i += 2
                continue

            # Check if this is part of redirection: '>&', '2>&1', '&>', '&>>'
            # Preceding '>'
            if i > 0 and cleaned[i - 1] == ">":
                i += 1
                continue
            # Following '>'
            if i + 1 < length and cleaned[i + 1] == ">":
                i += 1
                continue

            # Preceding digit before '>' (e.g. 2>&1) - covered by cleaned[i-1] == '>' above

            # Found an unquoted intermediate background operator '&'
            return (
                "Detached background operator '&' detected inside compound command. "
                "In foreground execution, intermediate '&' creates orphaned background processes "
                "that escape process group tracking. "
                "For long-running background services, use bash_code_execute_tool with run_in_background=True. "
                "For sequential commands, use '&&' or separate tool invocations."
            )

        i += 1

    return None
