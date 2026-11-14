"""工具结果过滤模块

1. 本文件的 INPUT/OUTPUT/POS 注释

[INPUT]
- langchain_core.language_models::BaseChatModel (POS: LangChain LLM 基类)
- utils.text_utils::get_token_count (POS: Token 计数工具)
- filters::FilterContext, RowSampleFilter, SemanticFilter, StructuralFilter (POS: 过滤器实现)
- filters.base::STRUCTURAL_CONTENT_TYPES, BaseFilter, ContentType, detect_content_type (POS: 内容类型检测)

[OUTPUT]
- FilteredResult: 过滤后的结果类（包含内容类型、摘要、结构概览、读取建议）
- should_filter(): 判断是否需要过滤（基于 token 阈值）
- create_filtered_result(): 创建过滤结果（使用混合过滤策略）
- format_filtered_message(): 格式化过滤后的消息
- FILTER_TOKEN_THRESHOLD: 过滤阈值常量（20000 tokens）
- ROW_LISTING_TOOLS: 结果为行列表的工具名集合（grep_tool / glob_tool）

[POS]
Tool result filter. Truncates large tool outputs and generates smart previews: the real first and last rows for row listings, structural extraction for structured data, LLM summarization otherwise.

"""

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from myrm_agent_harness.utils.text_utils import get_token_count

from .filters import FilterContext, RowSampleFilter, SemanticFilter, StructuralFilter
from .filters.base import STRUCTURAL_CONTENT_TYPES, BaseFilter, ContentType, detect_content_type

FILTER_TOKEN_THRESHOLD = 20000

# Tools whose result is a listing of independent rows (one match or path per line). Neither an outline
# nor a summary of such a listing says which rows matched; the real first and last rows do.
ROW_LISTING_TOOLS: frozenset[str] = frozenset({"grep_tool", "glob_tool"})


@dataclass
class FilteredResult:
    """过滤后的结果"""

    content_type: ContentType
    total_lines: int
    total_chars: int
    estimated_tokens: int
    summary: str
    structure_overview: str
    read_suggestions: list[str]
    llm_generated: bool = False


def should_filter(content: str, threshold: int = FILTER_TOKEN_THRESHOLD) -> bool:
    if not isinstance(content, str):
        return False
    token_count = get_token_count(content)
    return token_count > threshold


async def create_filtered_result(
    content: str,
    file_path: str,
    user_query: str,
    llm: BaseChatModel | None = None,
    file_id: str | None = None,
    tool_name: str | None = None,
) -> FilteredResult:
    """创建过滤结果（纯内存，智能预览）

    混合过滤策略：
    - 行列表工具（ROW_LISTING_TOOLS）：使用 RowSampleFilter（原样保留首尾行，无需 LLM）
    - 结构化数据（JSON/XML/代码/CSV/YAML/日志）：使用 StructuralFilter（无需 LLM）
    - 非结构化数据 + LLM 可用：使用 SemanticFilter + LLM
    - 非结构化数据 + LLM 不可用：降级为 StructuralFilter（head/tail 预览）
    """
    row_listing = tool_name in ROW_LISTING_TOOLS
    # A listing is typed by its tool, not by its text: result rows that quote code words or commas read as code or CSV.
    content_type: ContentType = "plain_text" if row_listing else detect_content_type(content)
    estimated_tokens = get_token_count(content)

    display_path = file_id if file_id else file_path
    filter_context = FilterContext(
        content=content, file_path=display_path, content_type=content_type, user_query=user_query
    )

    filter_instance: BaseFilter
    if row_listing:
        filter_instance = RowSampleFilter()
    elif content_type in STRUCTURAL_CONTENT_TYPES or llm is None:
        filter_instance = StructuralFilter()
    else:
        filter_instance = SemanticFilter(llm)

    filter_result = await filter_instance.filter(filter_context)

    return FilteredResult(
        content_type=content_type,
        total_lines=filter_result.total_lines,
        total_chars=filter_result.total_chars,
        estimated_tokens=estimated_tokens,
        summary=filter_result.summary,
        structure_overview=filter_result.structure_overview,
        read_suggestions=filter_result.read_suggestions,
        llm_generated=filter_result.llm_generated,
    )


def format_filtered_message(result: FilteredResult, *, saved_path: str | None = None) -> str:
    """Format a FilteredResult into a human/LLM-readable message.

    Args:
        result: The filtering result with content analysis.
        saved_path: Relative path where the full output was saved. Without one the message says that
                    no copy exists instead of sending the agent after a file it cannot read.
    """
    head = _FILTERED_HEAD.format(
        banner=_banner(_TITLE_SAVED if saved_path else _TITLE_NOT_SAVED),
        content_type=result.content_type,
        total_lines=result.total_lines,
        total_chars=result.total_chars,
        estimated_tokens=result.estimated_tokens,
        summary=result.summary,
        structure_overview=result.structure_overview,
    )
    if not saved_path:
        return head + _NOT_SAVED_NOTICE

    read_suggestions_text = "\n".join(f" {suggestion}" for suggestion in result.read_suggestions)
    return head + _RECOVER_FROM_DISK.format(read_suggestions_text=read_suggestions_text, saved_path=saved_path)


_BANNER_WIDTH = 62
_TITLE_SAVED = "LARGE OUTPUT TRUNCATED - USE file_read_tool TO RECOVER"
_TITLE_NOT_SAVED = "LARGE OUTPUT TRUNCATED - NO SAVED COPY"
_RULE = "━" * 64


def _banner(title: str) -> str:
    border = "═" * _BANNER_WIDTH
    return f"╔{border}╗\n║{title:^{_BANNER_WIDTH}}║\n╚{border}╝"


_FILTERED_HEAD = """{banner}

 Content Info:
  Type: {content_type} | Lines: {total_lines} | Chars: {total_chars} | Tokens: ~{estimated_tokens}

 Content Description:
{summary}

 Structure:
{structure_overview}
"""

_RECOVER_FROM_DISK = f"""
 TO GET FULL CONTENT:
{{read_suggestions_text}}

{_RULE}
Use file_read_tool on the saved path below when a full copy is needed.
Re-execute the tool only when the output cannot be recovered from disk.

 Full output saved to: {{saved_path}}
   Use file_read_tool to read specific portions of the saved file.
"""

_NOT_SAVED_NOTICE = f"""
{_RULE}
No copy of the full output was saved, so file_read_tool cannot recover it.
Re-execute the tool with a narrower scope (filters, pagination, a more specific query) to get the omitted part.
"""
