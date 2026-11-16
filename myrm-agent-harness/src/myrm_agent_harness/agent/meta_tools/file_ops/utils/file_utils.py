"""The ``path:START-END`` argument of the file tools: the file it names and the lines it asks for.

[INPUT]
- core.security.tool_registry::READ_RANGE_PATTERN (POS: the one grammar of a path argument's ``:START-END`` line range)
- core.operation_context::ViewRange (POS: View line range for partial reads)
- utils.path_utils::resolve_file_id_path (POS: resolves an ``@file_id`` to its path)

[OUTPUT]
- parse_path_with_range: the file path and the validated line range (positive numbers, ordered) of a path argument

[POS]
The validated reading of a path argument's range. Only a trailing ``:START-END`` or ``:START-`` is a range; every
other colon, such as a drive letter or the one in ``notes:v2.md``, belongs to the file name. The grammar is the one
the permission verdict strips ranges with (``strip_read_range``), so the file read is the file judged.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.tool_registry import READ_RANGE_PATTERN

from ..core.operation_context import ViewRange
from .path_utils import resolve_file_id_path


def parse_path_with_range(path_str: str) -> tuple[str, ViewRange | None]:
    """解析路径字符串，提取行号范围

    支持文件 ID 格式：@file_001:1-50
    支持 vault 指针：vault://uuid:1-50

    Args:
        path_str: 路径字符串，如 "file.py" 或 "file.py:1-50" 或 "@file_001:1-50"

    Returns:
        (文件路径, 行号范围) 元组

    Raises:
        ValueError: 当行号为非正整数（< 1）或结束行号小于起始行号时抛出明确异常。
    """
    match = READ_RANGE_PATTERN.match(path_str)
    if match:
        file_path = match.group(1)
        start = int(match.group(2))
        end_str = match.group(3)
        end = int(end_str) if end_str else -1  # 空字符串表示到文件末尾

        if start < 1:
            raise ValueError(
                f"Invalid line range start in '{path_str}': start line must be a positive integer (>= 1), got {start}"
            )
        if end != -1:
            if end < 1:
                raise ValueError(
                    f"Invalid line range end in '{path_str}': end line must be a positive integer (>= 1), got {end}"
                )
            if end < start:
                raise ValueError(
                    f"Invalid line range in '{path_str}': end line ({end}) cannot be less than start line ({start})"
                )

        # 解析文件 ID
        file_path = resolve_file_id_path(file_path)
        return file_path, ViewRange(start=start, end=end)

    # 没有行号范围，直接解析文件 ID
    resolved_path = resolve_file_id_path(path_str)
    return resolved_path, None
