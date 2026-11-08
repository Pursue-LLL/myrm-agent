"""Agent-facing descriptions of the Wiki tools, in English and Chinese.

[INPUT]
- utils.locale::is_chinese (POS: BCP-47 locale normalization and Chinese-family detection)

[OUTPUT]
- resolve_wiki_ingest_description / resolve_wiki_query_description / resolve_wiki_apply_description: the tool
  description for a locale (Chinese for a Chinese locale, English otherwise)

[POS]
Prompt text of wiki_ingest_tool, wiki_query_tool and wiki_apply_tool, shared by the LangChain tools and the MCP
adapter so the two surfaces describe the tools identically.
"""

from __future__ import annotations

from myrm_agent_harness.utils.locale import is_chinese

WIKI_INGEST_DESCRIPTION_EN = """Ingest documents into the Wiki knowledge base (supports Web URLs, local files like PDF/Word/Excel/Markdown, or raw text).

Use this when users want to add reference materials or documents to their knowledge base.
If folder_path is provided, the document is categorized under that subdirectory.
Supported inputs:
- Web URLs: fetched and converted to markdown
- Local file paths: text/markdown or parsed binary documents (PDF, DOCX, XLSX, PPTX)
- Raw text: saved as a markdown document
Automatically parsed and queued for knowledge compilation.
"""

WIKI_INGEST_DESCRIPTION_ZH = """将文档录入 Wiki 知识库（支持网页 URL、本地 PDF/Word/Excel/Markdown 等文件或纯文本内容）。

适用场景：用户希望向个人/团队知识库添加参考资料或文档。
若提供 folder_path，文档将归类至该逻辑子目录下。
支持输入类型：
- 网页 URL：抓取并转换为 Markdown
- 本地文件路径：文本/Markdown 或自动解析的二进制文档（PDF、DOCX、XLSX、PPTX）
- 纯文本内容：直接保存为 Markdown 文档
自动解析并加入知识库编译索引队列。
"""

WIKI_QUERY_DESCRIPTION_EN = """Query the Wiki knowledge base.

Searches relevant wiki articles and returns grounded context with source citations.
Search here first when answering questions about project concepts, domain knowledge, team notes, or compiled research.
When the tool refuses (insufficient evidence), tell the user honestly that the
knowledge base has no verified basis for the question and suggest ingesting source
documents - never guess or invent an answer.
"""

WIKI_QUERY_DESCRIPTION_ZH = """检索 Wiki 知识库。

搜索相关 Wiki 概念词条与文档，返回带有来源引用的可信上下文。
在回答有关项目概念、领域知识、团队笔记或沉淀研究的问题时优先在此搜索。
当工具返回拒答（证据不足）时，必须如实告知用户知识库中无可靠依据，
并建议补充录入相关源文档——严禁猜测或编造答案。
"""

WIKI_APPLY_DESCRIPTION_EN = """Apply a narrow, structured mutation to a wiki concept page.

Protects managed sections (Compiled Truth, Timeline, claims frontmatter).
Writes are staged as pending drafts for human review and publish only after
approval; report the note as awaiting review, not published.
Do not use whole-page rewrites; pick the smallest op that fits:
- create_note: Create a new structured note (requires concept_name and body; optional tags/aliases/sources)
- patch_compiled_truth: Update the core facts section (requires concept_name and compiled_truth)
- append_timeline: Append a milestone bullet (requires concept_name and timeline_entry)
- update_metadata: Update frontmatter tags, aliases, or source citations (requires concept_name and tags/aliases/sources)
"""

WIKI_APPLY_DESCRIPTION_ZH = """对 Wiki 概念页面应用结构化更新。

保护受管区域（核心事实 Compiled Truth、时间线 Timeline、元数据 frontmatter）。
通过本工具写入的内容会进入待审箱等待人工审核，批准后才发布；请告知用户
笔记处于待审状态，而非已发布。
请勿全量重写整个页面，按需选择最轻量的操作：
- create_note: 创建新结构化笔记（需 concept_name 与 body；可选 tags/aliases/sources）
- patch_compiled_truth: 局部修正核心事实段落（需 concept_name 与 compiled_truth）
- append_timeline: 追加里程碑时间线条目（需 concept_name 与 timeline_entry）
- update_metadata: 更新标签、别名或引用来源（需 concept_name 与 tags/aliases/sources）
"""


def resolve_wiki_ingest_description(locale: str | None = None) -> str:
    """Resolve localized description for wiki_ingest_tool."""
    return WIKI_INGEST_DESCRIPTION_ZH if is_chinese(locale) else WIKI_INGEST_DESCRIPTION_EN


def resolve_wiki_query_description(locale: str | None = None) -> str:
    """Resolve localized description for wiki_query_tool."""
    return WIKI_QUERY_DESCRIPTION_ZH if is_chinese(locale) else WIKI_QUERY_DESCRIPTION_EN


def resolve_wiki_apply_description(locale: str | None = None) -> str:
    """Resolve localized description for wiki_apply_tool."""
    return WIKI_APPLY_DESCRIPTION_ZH if is_chinese(locale) else WIKI_APPLY_DESCRIPTION_EN
