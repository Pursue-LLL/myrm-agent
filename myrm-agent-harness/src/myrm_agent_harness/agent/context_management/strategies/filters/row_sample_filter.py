"""行列表过滤器

[INPUT]
- base::BaseFilter, FilterContext, FilterResult, generate_smart_read_suggestions (POS: 过滤器基类、数据结构和读取建议)
- utils.text_utils::get_token_count, smart_truncate (POS: Token 计数与按行对齐的头尾截断)

[OUTPUT]
- ROW_SAMPLE_MAX_CHARS: 行样本的字符上限
- RowSampleFilter: 行列表过滤器（原样保留首尾行，不依赖 LLM）

[POS]
Row listing filter. Cuts a listing of independent rows (one match or path per line) down to its real first and last rows, because a summary of such a listing cannot say which rows matched.

"""

from myrm_agent_harness.utils.text_utils import get_token_count, smart_truncate

from .base import BaseFilter, FilterContext, FilterResult, generate_smart_read_suggestions

# About 1k tokens: enough rows to act on, and a small share of the size that triggers filtering.
ROW_SAMPLE_MAX_CHARS = 3000


class RowSampleFilter(BaseFilter):
    """Keeps the first and last rows of a listing exactly as returned; a marker shows where the middle was cut."""

    async def filter(self, context: FilterContext) -> FilterResult:
        total_lines = len(context.content.splitlines())
        return FilterResult(
            file_path=context.file_path,
            content_type=context.content_type,
            total_lines=total_lines,
            total_chars=len(context.content),
            estimated_tokens=get_token_count(context.content),
            summary=(
                "Result listing, shown verbatim: the first and last lines are kept and a [Truncated: ...] marker "
                "shows where the middle was cut."
            ),
            structure_overview=smart_truncate(context.content, ROW_SAMPLE_MAX_CHARS),
            read_suggestions=generate_smart_read_suggestions(context.file_path, total_lines, context.content_type),
        )
