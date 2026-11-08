"""上下文格式化工具

[INPUT]
- utils.context_format.boundary::wrap_with_external_sources_tag, wrap_with_tool_output_tag (POS: 工具结果的安全边界)
- utils.context_format.budget::TruncationStats (POS: token 预算估算、分配与截断)
- utils.context_format.collection::format_document_header (POS: 按 URL 去重收集文档，生成来源条目与标签)
- utils.context_format.formatter::format_documents_with_metadata (POS: 文档列表格式化入口)

[OUTPUT]
- format_document_header(): 格式化单个文档的头部信息
- format_documents_with_metadata(): 格式化文档列表为字符串（带元数据），支持精确token控制
- TruncationStats: 截断统计信息（原始tokens、最终tokens、截断数、保留率）
- wrap_with_external_sources_tag(): 安全边界包装（UNTRUSTED_DATA）+ 持久 cite reminder
- wrap_with_tool_output_tag(): 安全边界包装（TOOL_OUTPUT）

[POS]
`myrm_agent_harness.utils.context_format` 的唯一门面。文档与上下文的格式化逻辑统一管理，输出格式一致。
"""

from myrm_agent_harness.utils.context_format.boundary import wrap_with_external_sources_tag, wrap_with_tool_output_tag
from myrm_agent_harness.utils.context_format.budget import TruncationStats
from myrm_agent_harness.utils.context_format.collection import format_document_header
from myrm_agent_harness.utils.context_format.formatter import format_documents_with_metadata

__all__ = [
    "TruncationStats",
    "format_document_header",
    "format_documents_with_metadata",
    "wrap_with_external_sources_tag",
    "wrap_with_tool_output_tag",
]
