"""安全边界包装

[INPUT]
- core.security.detection.content_boundary::wrap_untrusted, wrap_tool_output (POS: 内容边界防御核心，五层防注入包装) [lazy]

[OUTPUT]
- wrap_with_external_sources_tag(): 安全边界包装（UNTRUSTED_DATA）+ 持久 cite reminder
- wrap_with_tool_output_tag(): 安全边界包装（TOOL_OUTPUT）

[POS]
工具结果的安全边界。外部数据源（会触发引用规则）与工具执行结果（不触发引用规则）各一个入口。
"""

_EXTERNAL_SOURCE_CITATION_REMINDER = (
    "\n\nWhen you use facts from the content above in your reply, "
    "add numbered source markers matching the source indices shown in this result (e.g. [1] or 【1】)."
)


def wrap_with_external_sources_tag(context: str, *, source: str = "external") -> str:
    """将上下文包装在安全边界标记中（UNTRUSTED_DATA）

    用于包裹外部数据源（web_search、web_fetch、browser、wiki、MCP远程数据），
    触发引用规则；具体引用格式由业务层 prompt/middleware 定义。

    安全：5 层防护（Unicode folding + invisible chars + pattern detection + random boundary + security notice）。
    """
    from myrm_agent_harness.core.security.detection.content_boundary import (
        wrap_untrusted,
    )

    wrapped = wrap_untrusted(context, source=source)
    return wrapped + _EXTERNAL_SOURCE_CITATION_REMINDER


def wrap_with_tool_output_tag(content: str) -> str:
    """将内容包装在安全边界标记中（TOOL_OUTPUT）

    用于包裹工具执行结果（代码输出、文件内容），防止 prompt injection，
    但不触发引用规则（模型无需添加引用标记）。

    安全：5 层防护（Unicode folding + invisible chars + pattern detection + random boundary + security notice）。
    """
    from myrm_agent_harness.core.security.detection.content_boundary import (
        wrap_tool_output,
    )

    return wrap_tool_output(content)
