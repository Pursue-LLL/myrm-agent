"""[INPUT]
- langchain_core.messages::ToolMessage (POS: 消息类型)

[OUTPUT]
- smart_truncate_output / extract_text_content

[POS]
`_tool_helpers/` 的文本截断与提取；只处理字符串，不触碰安全策略。
"""

from __future__ import annotations


def smart_truncate_output(text: str, max_lines: int = 20) -> str:
    """Keep first N/2 and last N/2 lines, truncate middle.

    Prevents token inflation when including large tool outputs in error messages.
    """
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text

    keep = max_lines // 2
    truncated_count = len(lines) - max_lines
    return "\n".join(
        [
            *lines[:keep],
            f"... [truncated {truncated_count} lines for token optimization] ...",
            *lines[-keep:],
        ]
    )

def extract_text_content(content: str | list[str | dict[str, object]]) -> str:
    """Extract plain text from ToolMessage content (str or list of content blocks)."""
    if isinstance(content, str):
        return content
    return "".join(
        str(block.get("text") or "") for block in content if isinstance(block, dict) and block.get("type") == "text"
    )
