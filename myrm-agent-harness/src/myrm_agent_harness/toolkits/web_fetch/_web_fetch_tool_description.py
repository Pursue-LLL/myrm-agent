"""web_fetch_tool LLM-visible description (prompt/cache SSOT).

Kept separate from ``web_fetch_agent_tools.py`` so static tests can import
without pulling fetch engine dependencies.

English and Chinese variants are both first-class LLM-facing strings.
Default locale is English; callers pass BCP-47 locale strings (e.g. ``zh-CN``).

[INPUT]
- utils.locale::is_chinese (POS: BCP-47 Chinese detection for description locale)

[OUTPUT]
- resolve_web_fetch_tool_description: Locale-aware description resolver; documents fetch_and_extract only when the tool offers it
- DEFAULT_WEB_FETCH_TOOL_DESCRIPTION_LOCALE: Locale used when the caller passes none

[POS]
Prompt SSOT for web_fetch_tool. Imported by web_fetch_agent_tools.py and static tests.
"""

from __future__ import annotations

from myrm_agent_harness.utils.locale import is_chinese

DEFAULT_WEB_FETCH_TOOL_DESCRIPTION_LOCALE = "en"

_EXTRACT_SECTION_EN = """
### fetch_and_extract

Retrieve **relevant content snippets** from known webpages (single or multiple URLs).

**Use cases:**
- Retrieve relevant info from webpages that can answer user questions; use this operation in most cases

**Parameters:**
- urls: Known and real target webpage URL list, no fabrication allowed
- questions: Query list, must be rewritten according to "query rewriting rules"
- operation: "fetch_and_extract"

**Query rewriting rules:**
- Generate 1-5 queries centered on user intent
- **Language alignment**: Query language should match target webpage language when possible
"""

_FULL_CONTENT_WITH_EXTRACT_EN = """
### fetch_full_content

Get the **full content** of known webpages (single or multiple URLs).
Long pages come back shortened; if the full text was saved, the result says how to read the omitted parts.

**Use cases:**
- User explicitly requests full page content
- Need to summarize or analyze the entire webpage

**Parameters:**
- urls: Known webpage URL list
- operation: "fetch_full_content"
"""

_PLAIN_EN = """Fetch the full content of known URLs as Markdown, including PDF, DOCX, XLSX and PPTX files.
When you need several pages, pass their URLs together in one call (up to 5).
Long pages come back shortened; if the full text was saved, the result says how to read the omitted parts.
WeChat Official Account articles (mp.weixin.qq.com/s/...) are supported; use the article URL exactly as the user provided it."""

_EXTRACT_HEADER_EN = """Reads the content of known URLs, including PDF, DOCX, XLSX and PPTX files. When you need several pages, pass their URLs together in one call.
{sections}
WeChat Official Account article links (mp.weixin.qq.com/s/...) are supported via fetch_full_content; use the real article URL the user provided."""

_EXTRACT_SECTION_ZH = """
### fetch_and_extract

从已知网页（单个或多个 URL）中检索**相关内容片段**。

**适用场景：**
- 从能够回答用户问题的网页中检索相关信息；大多数情况使用此操作

**参数：**
- urls：已知且真实的目标网页 URL 列表，禁止编造
- questions：查询列表，必须按「query 改写规则」改写
- operation："fetch_and_extract"

**Query 改写规则：**
- 围绕用户意图生成 1-5 条查询
- **语言对齐**：查询语言应尽量与目标网页语言一致
"""

_FULL_CONTENT_WITH_EXTRACT_ZH = """
### fetch_full_content

获取已知网页（单个或多个 URL）的**完整内容**。
过长的页面会被截短返回；若完整内容已保存，结果中会说明如何读取被省略的部分。

**适用场景：**
- 用户明确要求获取完整页面内容
- 需要总结或分析整个网页

**参数：**
- urls：已知网页 URL 列表
- operation："fetch_full_content"
"""

_PLAIN_ZH = """获取已知 URL 的完整内容（Markdown 格式），包括 PDF、DOCX、XLSX、PPTX 文件。需要读取多个页面时，请把 URL 合并到一次调用（最多 5 个）。
过长的页面会被截短返回；若完整内容已保存，结果中会说明如何读取被省略的部分。
支持微信公众号文章链接（mp.weixin.qq.com/s/...）；请原样使用用户提供的文章 URL。"""

_EXTRACT_HEADER_ZH = """读取已知 URL 的内容，包括 PDF、DOCX、XLSX、PPTX 文件。需要读取多个页面时，请把 URL 合并到一次调用。
{sections}
微信公众号文章链接（mp.weixin.qq.com/s/...）可通过 fetch_full_content 获取；使用用户提供的真实文章 URL。"""


def resolve_web_fetch_tool_description(
    enable_extract: bool, locale: str | None = DEFAULT_WEB_FETCH_TOOL_DESCRIPTION_LOCALE
) -> str:
    """Return the locale-aware tool description for the configured fetch mode.

    ``enable_extract`` mirrors the tool's runtime capability: when the reranker
    and embedding services are available, ``fetch_and_extract`` is offered and
    the description documents both operations; otherwise the tool has no
    ``operation`` argument and the description only covers reading pages in full.
    """
    chinese = is_chinese(locale)
    if not enable_extract:
        return _PLAIN_ZH if chinese else _PLAIN_EN
    if chinese:
        return _EXTRACT_HEADER_ZH.format(sections=_EXTRACT_SECTION_ZH + _FULL_CONTENT_WITH_EXTRACT_ZH)
    return _EXTRACT_HEADER_EN.format(sections=_EXTRACT_SECTION_EN + _FULL_CONTENT_WITH_EXTRACT_EN)


__all__ = [
    "DEFAULT_WEB_FETCH_TOOL_DESCRIPTION_LOCALE",
    "resolve_web_fetch_tool_description",
]
