"""文档列表格式化

[INPUT]
- langchain_core.documents::Document (POS: LangChain 文档类型)
- core.context_vars::SourceIndexer (POS: 运行级来源编号函数的类型)
- utils.text_utils::PLANNING_ENCODING, get_token_count (POS: Token 计算与截断)
- utils.context_format.collection::collect_and_deduplicate_urls (POS: 按 URL 去重收集文档，生成来源条目与标签)
- utils.context_format.budget::TruncationStats, MAX_SINGLE_DOC_TOKENS, allocate_tokens_weighted, apply_token_truncation, estimate_token_overhead, truncate_documents_to_fit_budget (POS: token 预算估算、分配与截断)

[OUTPUT]
- format_documents_with_metadata(): 格式化文档列表为字符串（带元数据），支持精确token控制

[POS]
上下文格式化的入口。收集、预算控制、拼接三个阶段的编排，输出格式统一。
"""

import logging

from langchain_core.documents import Document

from myrm_agent_harness.core.context_vars import SourceIndexer
from myrm_agent_harness.utils.context_format.budget import (
    MAX_SINGLE_DOC_TOKENS,
    TruncationStats,
    allocate_tokens_weighted,
    apply_token_truncation,
    estimate_token_overhead,
    truncate_documents_to_fit_budget,
)
from myrm_agent_harness.utils.context_format.collection import collect_and_deduplicate_urls
from myrm_agent_harness.utils.text_utils import PLANNING_ENCODING, get_token_count

logger = logging.getLogger(__name__)


def format_documents_with_metadata(
    documents: list[Document],
    questions: list[str] | None = None,
    include_title: bool = True,
    include_date: bool = True,
    extract_clean_content: bool = True,
    max_content_tokens: int | None = None,
    total_max_tokens: int | None = None,
    token_encoding: str = PLANNING_ENCODING,
    index_for: SourceIndexer | None = None,
) -> tuple[list[dict[str, object]], str, TruncationStats | None]:
    """格式化文档列表，返回结构化元数据和上下文字符串

    纯粹的格式化功能，不包含引用逻辑。支持三级token控制：
    - 优先级1: total_max_tokens（全局预算，自适应估算+加权分配）
    - 优先级2: max_content_tokens（单文档限制）
    - 优先级3: 字符fallback（tiktoken失败时）

    自适应估算策略：基于首个header预检分级（25/40/70 tokens），精确计算questions前缀。

    极端场景处理：当预算严重不足（estimated_overhead > total_max_tokens）时，
    动态裁剪文档数量以满足预算（保留Top优先级），确保final_tokens严格≤total_max_tokens。
    如预算连1个文档都无法容纳，返回空结果。会发出ERROR日志提示推荐预算值。

    Args:
        documents: 文档列表
        questions: 查询关键词列表，会在上下文开头添加前缀（精确计算tokens）
        include_title: 是否在头部包含标题
        include_date: 是否在头部包含日期
        extract_clean_content: 是否提取干净的内容（去除Front Matter但保留section）
        max_content_tokens: 单文档内容最大token数
        total_max_tokens: 总token预算。推荐: ≥ num_docs * 120
        token_encoding: tiktoken编码器名称
        index_for: 来源编号函数（运行内同一来源编号不变），其结果写进每个来源的标签；
            None 时每次调用都从 1 开始按出现顺序编号。预算裁掉的文档占用的编号不会回收

    Returns:
        元组：(结构化元数据列表, 格式化的上下文字符串, 截断统计信息)
        元数据格式: [{"url": "...", "title": "...", "snippet": "...", "date": "..."}, ...]
    """
    if not documents:
        return [], "", None

    # 阶段 1：收集并去重 URL
    collection = collect_and_deduplicate_urls(documents, include_title, include_date, extract_clean_content, index_for)

    num_urls = len(collection.url_to_header)
    truncated_count = 0
    truncation_stats = None

    # 计算完整输入的original_tokens（用于统计）
    original_tokens = 0
    if total_max_tokens or max_content_tokens:
        # collection当前包含所有输入文档
        original_parts = [
            collection.url_to_header[url] + "\n\n" + "\n".join(collection.url_to_contents[url]) + "\n\n"
            for url in collection.url_to_header
        ]
        original_text = "".join(original_parts).strip()
        original_tokens = get_token_count(original_text, token_encoding)

    # 阶段 2：Token 控制
    if total_max_tokens or max_content_tokens:
        # 自适应估算与分配
        if total_max_tokens:
            questions_budget, header_budget, separator_budget, header_per_doc = estimate_token_overhead(
                collection, questions, token_encoding
            )
            estimated_overhead = questions_budget + header_budget + separator_budget

            # 预算不足时动态裁剪
            if estimated_overhead > total_max_tokens:
                result = truncate_documents_to_fit_budget(
                    collection,
                    estimated_overhead,
                    total_max_tokens,
                    questions_budget,
                    header_per_doc,
                )
                if result is None:
                    return [], "", None

                collection, estimated_overhead = result
                # 更新文档数量
                num_urls = len(collection.url_to_header)

            # 分配内容预算
            content_budget = max(0, total_max_tokens - estimated_overhead)

            if content_budget < num_urls * 20:
                logger.warning(
                    f"Insufficient token budget: total={total_max_tokens}, questions={questions_budget}, "
                    f"headers≈{header_budget}, separators={separator_budget}, content={content_budget}, "
                    f"docs={num_urls}, per_doc={content_budget // num_urls if num_urls > 0 else 0}. "
                    f"Recommend: total_max_tokens >= {estimated_overhead + num_urls * 80}"
                )

            allocations = allocate_tokens_weighted(content_budget, num_urls)
        else:
            # 仅max_content_tokens控制：使用统一的单文档限制
            # 若max_content_tokens为None，使用默认上限（实际不会截断）
            single_doc_limit = max_content_tokens if max_content_tokens is not None else MAX_SINGLE_DOC_TOKENS
            allocations = [single_doc_limit] * num_urls

        # 应用截断
        url_final_content, truncated_count = apply_token_truncation(
            collection, allocations, max_content_tokens, token_encoding
        )
    else:
        # 无 token 控制：直接拼接
        url_final_content = {url: "\n\n".join(collection.url_to_contents[url]) for url in collection.url_to_header}

    # 阶段 3：最终拼接
    formatted_parts = [
        f"{collection.url_to_header[url]}\n\n{url_final_content[url]}\n\n" for url in collection.url_to_header
    ]
    formatted_text = "".join(formatted_parts).strip()

    if questions:
        keywords_str = ", ".join(questions)
        formatted_text = f"relevant results for keywords [{keywords_str}]:\n{formatted_text}"

    # 计算统计信息
    if total_max_tokens or max_content_tokens:
        final_tokens = get_token_count(formatted_text, token_encoding)

        truncation_stats = TruncationStats(
            original_tokens=original_tokens,
            final_tokens=final_tokens,
            truncated_docs=truncated_count,
            total_docs=num_urls,
            retention_ratio=(final_tokens / original_tokens if original_tokens > 0 else 1.0),
        )

        if total_max_tokens:
            logger.info(
                f"Token control: {original_tokens}→{final_tokens} tokens, "
                f"truncated {truncated_count}/{num_urls} docs, retention={truncation_stats.retention_ratio:.1%}"
            )

    return collection.sources_metadata, formatted_text, truncation_stats
