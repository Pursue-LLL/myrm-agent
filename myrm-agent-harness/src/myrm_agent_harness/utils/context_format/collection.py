"""文档收集与来源标签

[INPUT]
- langchain_core.documents::Document (POS: LangChain 文档类型)
- core.context_vars::SourceIndexer (POS: 运行级来源编号函数的类型)
- utils.document_utils::extract_clean_content_for_context (POS: 文档内容提取)

[OUTPUT]
- format_document_header(): 格式化单个文档的头部信息
- DocumentCollection: 文档集合的中间状态（header、内容、元数据；三者按唯一 URL 同序）
- collect_and_deduplicate_urls(): 按 URL 去重收集文档，生成来源条目、header 与聚合内容

[POS]
上下文格式化的收集阶段。每个唯一 URL 对应一个来源条目、一个来源标签与一份聚合内容；
标签里的编号由运行级编号函数给出，没有时按出现顺序从 1 开始。
"""

from typing import NamedTuple

from langchain_core.documents import Document

from myrm_agent_harness.core.context_vars import SourceIndexer
from myrm_agent_harness.utils.document_utils import extract_clean_content_for_context


class DocumentCollection(NamedTuple):
    """文档集合的中间状态

    封装多个文档相关的映射表和元数据，避免传递多个独立的字典。
    提供类型安全和字段名自文档化的访问方式。
    三个映射表的键相同、顺序相同（唯一 URL 的首次出现顺序）。
    """

    url_to_header: dict[str, str]
    url_to_contents: dict[str, list[str]]
    sources_metadata: list[dict[str, object]]


def format_document_header(
    index: int,
    url: str,
    title: str = "",
    date: str = "",
    include_title: bool = True,
    include_date: bool = True,
) -> str:
    """格式化单个文档的头部信息

    Args:
        index: 文档序号
        url: 文档URL
        title: 文档标题
        date: 文档日期
        include_title: 是否包含标题
        include_date: 是否包含日期

    Returns:
        格式化的头部字符串，格式：【序号】 URL: xxx | Title: xxx | Date: xxx
    """
    header = f"【{index}】 URL: {url}"

    if include_title and title:
        header += f" | Title: {title}"

    if include_date and date:
        header += f" | Date: {date}"

    return header


def collect_and_deduplicate_urls(
    documents: list[Document],
    include_title: bool,
    include_date: bool,
    extract_clean_content: bool,
    index_for: SourceIndexer | None,
) -> DocumentCollection:
    """收集唯一URL并聚合内容

    遍历文档列表，按URL去重，为每个唯一URL生成元数据、header和聚合内容。
    多个文档共享同一URL时，内容会被聚合到同一条目下。

    Args:
        documents: 原始文档列表
        include_title: 是否在header中包含标题
        include_date: 是否在header中包含日期
        extract_clean_content: 是否提取干净内容（去除Front Matter）
        index_for: 来源编号函数，以将成为来源的条目为参数；None 时按出现顺序从 1 开始编号

    Returns:
        DocumentCollection: 包含所有URL相关映射和元数据的集合
    """
    sources_metadata = []
    url_to_header: dict[str, str] = {}
    url_to_contents: dict[str, list[str]] = {}

    for doc in documents:
        url = doc.metadata.get("url", "")

        if url not in url_to_header:
            title = doc.metadata.get("title", "")
            date = doc.metadata.get("date", "")
            snippet = doc.metadata.get("snippet", "") or doc.metadata.get("description", "")
            summary = doc.metadata.get("summary", "")

            entry: dict[str, object] = {
                "url": url,
                "title": title,
                "snippet": snippet,
                "date": date,
            }
            if summary:
                entry["summary"] = summary
            site_name = doc.metadata.get("site_name")
            if site_name:
                entry["site_name"] = site_name
            authority_description = doc.metadata.get("authority_description")
            if authority_description:
                entry["authority_description"] = authority_description
            sources_metadata.append(entry)

            header = format_document_header(
                # 条目已完整：编号函数据此认出稍后交给 SourceTracker 的同一个来源
                index=index_for(entry) if index_for is not None else len(url_to_header) + 1,
                url=url,
                title=title,
                date=date,
                include_title=include_title,
                include_date=include_date,
            )
            url_to_header[url] = header
            url_to_contents[url] = []

        content = extract_clean_content_for_context(doc.page_content) if extract_clean_content else doc.page_content
        url_to_contents[url].append(content.strip())

    return DocumentCollection(
        url_to_header=url_to_header,
        url_to_contents=url_to_contents,
        sources_metadata=sources_metadata,
    )
