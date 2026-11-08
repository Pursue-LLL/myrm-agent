"""Token 预算控制

[INPUT]
- utils.text_utils::get_token_count, truncate_by_tokens_with_boundary (POS: Token 计算与截断)
- utils.context_format.collection::DocumentCollection (POS: 文档集合的中间状态)

[OUTPUT]
- TruncationStats: 截断统计信息（原始tokens、最终tokens、截断数、保留率）
- MAX_SINGLE_DOC_TOKENS: 只设单文档上限时的默认上限
- allocate_tokens_weighted(): 按重要性加权分配token预算
- estimate_token_overhead(): 自适应估算questions前缀、header与分隔符的token开销
- truncate_documents_to_fit_budget(): 预算严重不足时裁剪文档数量
- apply_token_truncation(): 按分配的预算在句子边界截断每个文档的内容

[POS]
上下文格式化的 token 预算阶段。估算开销、在文档间分配内容预算、按预算截断内容。
"""

import logging
from typing import NamedTuple

from myrm_agent_harness.utils.context_format.collection import DocumentCollection
from myrm_agent_harness.utils.text_utils import get_token_count, truncate_by_tokens_with_boundary

logger = logging.getLogger(__name__)

_SEPARATOR_TOKEN_OVERHEAD = 2
MAX_SINGLE_DOC_TOKENS = 50000


class TruncationStats(NamedTuple):
    """截断统计信息"""

    original_tokens: int
    final_tokens: int
    truncated_docs: int
    total_docs: int
    retention_ratio: float


def allocate_tokens_weighted(total_budget: int, num_docs: int) -> list[int]:
    """按重要性加权分配token预算

    Top-3文档获得更多预算(25%, 15%, 10%)，其余平均分配。

    Args:
        total_budget: 总token预算
        num_docs: 文档数量

    Returns:
        每个文档的token分配列表
    """
    if num_docs <= 0:
        return []
    if num_docs <= 3:
        return [total_budget // num_docs] * num_docs

    weights = (0.25, 0.15, 0.10)
    allocations = [int(total_budget * w) for w in weights]
    remaining = (total_budget - sum(allocations)) // (num_docs - 3)
    return allocations + [remaining] * (num_docs - 3)


def estimate_token_overhead(
    collection: DocumentCollection,
    questions: list[str] | None,
    token_encoding: str,
) -> tuple[int, int, int, int]:
    """自适应估算token开销

    基于首个header的实际token数进行分级估算（25/40/70），
    精确计算questions前缀开销，计算总的header和分隔符开销。

    Args:
        collection: 文档集合
        questions: 查询关键词列表
        token_encoding: tiktoken编码器名称

    Returns:
        questions_budget: questions前缀的token开销
        header_budget: 所有header的总token开销
        separator_budget: 所有分隔符的总token开销
        header_per_doc: 每个文档的header估算值
    """
    num_urls = len(collection.url_to_header)

    # 快速预检第一个header，推测整体开销级别
    first_url = next(iter(collection.url_to_header))
    first_header_tokens = get_token_count(collection.url_to_header[first_url], token_encoding)

    # 分级估算
    if first_header_tokens <= 20:
        header_per_doc = 25
    elif first_header_tokens <= 35:
        header_per_doc = 40
    else:
        header_per_doc = 70

    # 计算questions前缀开销
    questions_budget = 0
    if questions:
        keywords_str = ", ".join(questions)
        questions_prefix = f"relevant results for keywords [{keywords_str}]:\n"
        questions_budget = get_token_count(questions_prefix, token_encoding)

    header_budget = num_urls * header_per_doc
    separator_budget = num_urls * _SEPARATOR_TOKEN_OVERHEAD

    return questions_budget, header_budget, separator_budget, header_per_doc


def truncate_documents_to_fit_budget(
    collection: DocumentCollection,
    estimated_overhead: int,
    total_max_tokens: int,
    questions_budget: int,
    header_per_doc: int,
) -> tuple[DocumentCollection, int] | None:
    """当预算严重不足时动态裁剪文档数量

    当 estimated_overhead > total_max_tokens 时，计算最多可容纳的文档数，
    只保留前 max_docs 个文档（保留Top优先级），返回裁剪的文档集合。

    Args:
        collection: 原始文档集合
        estimated_overhead: 估算的总开销
        total_max_tokens: 总token预算
        questions_budget: questions前缀开销
        header_per_doc: 每个文档的header估算值

    Returns:
        None: 预算连1个文档都无法容纳
        tuple: (裁剪的DocumentCollection, 更新的estimated_overhead)
    """
    num_urls = len(collection.url_to_header)
    per_doc_overhead = header_per_doc + _SEPARATOR_TOKEN_OVERHEAD
    available_for_docs = total_max_tokens - questions_budget
    max_docs = available_for_docs // per_doc_overhead if per_doc_overhead > 0 else 0

    if max_docs == 0:
        logger.error(
            f"Critical: Budget too small for even 1 document. "
            f"Required: {questions_budget + per_doc_overhead}, available: {total_max_tokens}. "
            f"Recommend: total_max_tokens >= {questions_budget + per_doc_overhead + 80}"
        )
        return None

    logger.error(
        f"Critical: Budget insufficient, truncating {num_urls} → {max_docs} documents. "
        f"Estimated overhead: {estimated_overhead}, budget: {total_max_tokens}. "
        f"Recommend: total_max_tokens >= {estimated_overhead + num_urls * 80}"
    )

    # 裁剪数据结构：保留下来的文档沿用已写进 header 的编号
    kept_urls = list(collection.url_to_header)[:max_docs]
    truncated_collection = DocumentCollection(
        url_to_header={url: collection.url_to_header[url] for url in kept_urls},
        url_to_contents={url: collection.url_to_contents[url] for url in kept_urls},
        sources_metadata=collection.sources_metadata[:max_docs],
    )

    # 重新计算overhead
    header_budget = max_docs * header_per_doc
    separator_budget = max_docs * _SEPARATOR_TOKEN_OVERHEAD
    updated_overhead = questions_budget + header_budget + separator_budget

    return truncated_collection, updated_overhead


def apply_token_truncation(
    collection: DocumentCollection,
    allocations: list[int],
    max_content_tokens: int | None,
    token_encoding: str,
) -> tuple[dict[str, str], int]:
    """应用token截断到文档内容

    对每个文档应用分配的token预算进行截断。
    如果设置了 max_content_tokens，则取 min(allocation, max_content_tokens)。
    使用句子边界智能截断，确保不会在句子中间截断。

    Args:
        collection: 文档集合
        allocations: 每个文档的token分配列表（与文档集合中的 URL 顺序一致）
        max_content_tokens: 单文档token上限（可选）
        token_encoding: tiktoken编码器名称

    Returns:
        url_final_content: URL到截断后内容的映射
        truncated_count: 被截断的文档数量
    """
    url_final_content: dict[str, str] = {}
    truncated_count = 0

    for url, allocation in zip(collection.url_to_header, allocations, strict=False):
        content_parts = collection.url_to_contents[url]
        full_content = "\n\n".join(content_parts)

        if max_content_tokens is not None and allocation > max_content_tokens:
            allocation = max_content_tokens

        truncated_content = truncate_by_tokens_with_boundary(full_content, allocation, token_encoding)
        if len(truncated_content) < len(full_content):
            truncated_count += 1

        url_final_content[url] = truncated_content

    return url_final_content, truncated_count
