"""LangChain tools for Wiki toolkit.

[INPUT]
- langchain_core.tools::tool (POS: LangChain tool decorator)
- .pipeline.compiler::WikiCompiler (POS: Wiki compilation core engine)
- .retrieval.query::WikiQueryEngine (POS: Wiki query and enhancement engine)
- .core.structure::WikiStructure (POS: Wiki file system abstraction layer)
- .source_loader::fetch_url_markdown, read_local_file, looks_like_local_path (POS: Readable text of a URL or local file for ingestion)
- .ingest_chunking::split_if_large (POS: Cuts a large document into compile-sized raw/ sources)
- .wiki_tool_descriptions::resolve_wiki_ingest_description, resolve_wiki_query_description, resolve_wiki_apply_description (POS: Localized tool descriptions)

[OUTPUT]
- create_wiki_tools: creates 3 LangChain agent tools (ingest, query, apply)
- retrieval.source_citations::build_wiki_query_sources (POS: Shared wiki citation metadata builder)

[POS]
LangChain tool integration layer for Wiki toolkit. Wraps WikiCompiler and
WikiQueryEngine into agent-facing StructuredTools for Agent use. Provides end-to-end
automation: ingest triggers compilation, query archives high-value results for knowledge
compounding, and ingestion sources are loaded by source_loader (FetchEngine for URLs, file parsers for files); a
source that has no readable text is refused, never written to raw/.
Query metadata forwards layered citations, asset hit metadata, and read-time evidence snapshot_status for Chat/Settings UI.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated

from langchain_core.tools import BaseTool, tool

from myrm_agent_harness.utils.logger_utils import get_agent_logger

from .core.frontmatter_contract import WikiProvenance
from .core.structure import WikiStructure
from .ingest_chunking import split_if_large
from .pipeline.apply import (
    WikiApplyError,
    WikiApplyOp,
    WikiApplyRequest,
    apply_wiki_mutation,
)
from .pipeline.compiler import WikiCompiler
from .retrieval.indexer import WikiIndexer
from .retrieval.query import WikiQueryEngine
from .retrieval.source_citations import (
    attach_wiki_scope_id,
    build_wiki_query_sources,
    format_evidence_cards_context,
)
from .source_loader import SourceLoadError, fetch_url_markdown, looks_like_local_path, read_local_file
from .wiki_tool_descriptions import (
    resolve_wiki_apply_description,
    resolve_wiki_ingest_description,
    resolve_wiki_query_description,
)

logger = get_agent_logger(__name__)


def create_wiki_tools(
    compiler: WikiCompiler,
    query_engine: WikiQueryEngine,
    structure: WikiStructure,
    *,
    wiki_scope_id: str | None = None,
    locale: str | None = None,
) -> list[BaseTool]:
    """Create agent-facing wiki tools (ingest + query + apply).

    Compile/maintain are Settings/REST operations and are not exposed to the LLM.
    """
    return create_wiki_agent_tools(
        compiler,
        query_engine,
        structure,
        wiki_scope_id=wiki_scope_id,
        locale=locale,
    )


def create_wiki_agent_tools(
    compiler: WikiCompiler,
    query_engine: WikiQueryEngine,
    structure: WikiStructure,
    *,
    wiki_scope_id: str | None = None,
    locale: str | None = None,
) -> list[BaseTool]:
    """Create LangChain tools exposed to the agent at Turn1."""

    @tool("wiki_ingest_tool", description=resolve_wiki_ingest_description(locale))
    async def wiki_ingest(
        source: Annotated[
            str,
            "URL or file path to ingest (supports Web URLs, local documents like PDF/Word/Excel/Markdown, or raw text)",
        ],
        filename: Annotated[str, "Optional custom filename for the ingested document"] = "",
        folder_path: Annotated[
            str,
            "Optional logical folder path to categorize this document (e.g., 'Research/AI')",
        ] = "",
    ) -> str:
        logger.info(f"Ingesting: {source[:100]}")

        try:
            if source.startswith("http://") or source.startswith("https://"):
                content = await fetch_url_markdown(source)
                resolved_filename = filename or f"web_{hashlib.sha256(source.encode()).hexdigest()[:12]}.md"
                resolved_filename = Path(resolved_filename).name
                if folder_path:
                    safe_folder = structure._sanitize_path(folder_path)
                    full_path = f"{safe_folder}/{resolved_filename}"
                else:
                    full_path = resolved_filename

                from myrm_agent_harness.toolkits.wiki.pipeline.ingress import (
                    UrlMarkdownIngressRequest,
                    publish_url_markdown_ingress,
                )

                chunks = split_if_large(content, full_path)
                ingested_count = 0
                display_path = full_path

                for idx, (chunk_path, chunk_content) in enumerate(chunks):
                    ingress_result = await publish_url_markdown_ingress(
                        structure,
                        UrlMarkdownIngressRequest(
                            url=source,
                            filename=resolved_filename,
                            folder_path=folder_path,
                            relative_path=chunk_path if len(chunks) > 1 else "",
                            localize_public_assets=idx == 0,
                        ),
                        markdown=chunk_content,
                    )
                    if ingress_result.conflict:
                        return (
                            f"Raw source already exists with different content: "
                            f"{ingress_result.relative_path}. "
                            "Use Settings Wiki import to supersede or choose a different filename."
                        )
                    if ingress_result.security_blocked:
                        return (
                            f"Raw source rejected due to sensitive content: "
                            f"{ingress_result.relative_path}. "
                            "Remove credentials before ingesting."
                        )
                    if ingress_result.written:
                        compiler.enqueue_file(structure.get_raw_file_path(ingress_result.relative_path))
                        ingested_count += 1
                        display_path = ingress_result.relative_path

                if ingested_count == 0:
                    return "Failed to ingest document: no content was written to raw/"

                logger.info(f"Ingested {ingested_count} chunk(s) for: {display_path}")
                suffix = f" ({ingested_count} chunks)" if ingested_count > 1 else ""
                return f"Successfully ingested document: {display_path}{suffix}. Compilation queued."
            elif looks_like_local_path(source):
                src_path = Path(source)
                content = await read_local_file(src_path)
                filename = filename or src_path.name
                if not filename.endswith(".md"):
                    filename = Path(filename).stem + ".md"
            else:
                if not source.strip():
                    raise SourceLoadError("The source is empty")
                content = source
                filename = filename or f"text_{hashlib.sha256(source.encode()).hexdigest()[:12]}.md"

            filename = Path(filename).name

            if folder_path:
                safe_folder = structure._sanitize_path(folder_path)
                full_path = f"{safe_folder}/{filename}"
            else:
                full_path = filename

            chunks = split_if_large(content, full_path)
            ingested_count = 0

            from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import (
                RawConflictPolicy,
                RawGateError,
                RawPublishRequest,
                publish_raw,
            )

            for chunk_path, chunk_content in chunks:
                try:
                    result = await publish_raw(
                        structure,
                        RawPublishRequest(
                            relative_path=chunk_path,
                            content=chunk_content,
                            conflict_policy=RawConflictPolicy.FAIL,
                        ),
                        caller="agent",
                    )
                except RawGateError as exc:
                    if exc.code == "raw_conflict":
                        return (
                            f"Raw source already exists with different content: {chunk_path}. "
                            "Use Settings Wiki import to supersede or choose a different filename."
                        )
                    if exc.code == "raw_security_blocked":
                        return (
                            f"Raw source rejected due to sensitive content: {chunk_path}. "
                            "Remove credentials before ingesting."
                        )
                    return f"Failed to ingest document: {exc.message}"

                if result.security_blocked:
                    return (
                        f"Raw source rejected due to sensitive content: {chunk_path}. "
                        "Remove credentials before ingesting."
                    )

                if result.written:
                    compiler.enqueue_file(result.absolute_path)
                    ingested_count += 1

            logger.info(f"Ingested {ingested_count} chunk(s) for: {full_path}")
            suffix = f" ({ingested_count} chunks)" if ingested_count > 1 else ""
            return f"Successfully ingested document: {full_path}{suffix}. Compilation queued."

        except SourceLoadError as exc:
            logger.warning(f"Nothing to ingest from {source[:100]}: {exc}")
            return f"Failed to ingest document: {exc}"
        except Exception as e:
            logger.error(f"Failed to ingest {source}: {e}")
            return "Failed to ingest document"

    @tool("wiki_query_tool", description=resolve_wiki_query_description(locale))
    async def wiki_query(
        question: Annotated[
            str,
            "Question to ask the wiki knowledge base (e.g. concept definitions, architecture patterns, team facts)",
        ],
    ) -> dict[str, object] | str:
        logger.info(f"Querying wiki: {question[:100]}")

        try:
            result = await query_engine.query(question)

            # Hard refusal gate: below-threshold confidence means the wiki has no
            # verified basis — return an honest refusal instead of soft-copy the LLM
            # may ignore and hallucinate over. Template stays question-free (zero
            # interpolation) so raw user input can never inject instructions.
            if result.refused:
                return (
                    "REFUSED: the wiki knowledge base has no verified basis for this "
                    "question (evidence below confidence floor). Tell the user honestly "
                    "that no reliable answer exists in the knowledge base and suggest "
                    "ingesting the relevant source documents. Do not guess."
                )

            from myrm_agent_harness.utils.context_format import (
                wrap_with_external_sources_tag,
            )

            evidence_context = format_evidence_cards_context(
                result.answer,
                result.source_snippets,
                structure=structure,
            )

            # Moderate-confidence advisory header (answer-level; snippet-level claim
            # confidence is already annotated per evidence card). Reuses the engine's
            # own archive verdict: not refused but also not archive-grade confidence.
            if not result.should_archive:
                evidence_context = (
                    f"[Confidence: {result.confidence_score:.2f} | moderate - verify "
                    f"critical facts before relying on this]\n\n{evidence_context}"
                )

            wrapped_context = wrap_with_external_sources_tag(evidence_context, source="LLM-Wiki")

            sources = attach_wiki_scope_id(
                build_wiki_query_sources(result, structure=structure),
                wiki_scope_id,
            )

            # Archive only when high confidence and verified source snippets exist to prevent synthetic contamination
            if result.should_archive and result.confidence_score >= 0.8 and result.source_snippets:
                try:
                    await _archive_query_result(structure, compiler, question, result.answer)
                except Exception as archive_err:
                    logger.warning(f"Query archive failed (non-blocking): {archive_err}")

            return {"content": wrapped_context, "metadata": {"sources": sources}}

        except Exception as e:
            logger.error(f"Query failed: {e}")
            return "Query failed"

    @tool("wiki_apply_tool", description=resolve_wiki_apply_description(locale))
    async def wiki_apply(
        op: Annotated[
            str,
            "Operation: 'create_note' (new note with body), 'patch_compiled_truth' (update core facts with compiled_truth), 'append_timeline' (add event with timeline_entry), or 'update_metadata' (tags/aliases)",
        ],
        concept_name: Annotated[str, "Concept path, e.g. 'research/react-hooks' or 'team/onboarding'"],
        compiled_truth: Annotated[str, "For patch_compiled_truth: New Compiled Truth section content"] = "",
        timeline_entry: Annotated[str, "For append_timeline: Milestone or event bullet to append"] = "",
        body: Annotated[str, "For create_note: Main note content"] = "",
        tags: Annotated[
            str,
            "Comma-separated tags for update_metadata or create_note (e.g. 'frontend,react')",
        ] = "",
        aliases: Annotated[
            str,
            "Comma-separated aliases for update_metadata or create_note (e.g. 'Hooks,React Hooks')",
        ] = "",
        sources: Annotated[str, "Comma-separated source references for update_metadata or create_note"] = "",
        clear_confidence: Annotated[bool, "For update_metadata: Reset frontmatter confidence score"] = False,
    ) -> str:
        try:
            apply_op = WikiApplyOp(op.strip().lower())
        except ValueError:
            allowed = ", ".join(member.value for member in WikiApplyOp if member != WikiApplyOp.REPLACE_FULL_DOCUMENT)
            return f"Invalid op '{op}'. Allowed: {allowed}"

        def _split_csv(raw: str) -> tuple[str, ...] | None:
            if not raw.strip():
                return None
            return tuple(part.strip() for part in raw.split(",") if part.strip())

        request = WikiApplyRequest(
            op=apply_op,
            concept_name=concept_name.strip(),
            compiled_truth=compiled_truth,
            timeline_entry=timeline_entry,
            body=body,
            tags=_split_csv(tags),
            aliases=_split_csv(aliases),
            sources=_split_csv(sources),
            clear_confidence=clear_confidence,
            provenance=WikiProvenance.AGENT,
        )
        indexer = WikiIndexer(structure)
        try:
            result = await apply_wiki_mutation(structure, indexer, request, caller="agent")
        except WikiApplyError as exc:
            return f"Wiki apply failed ({exc.code}): {exc.message}"

        suffix = ""
        if result.created:
            suffix = " (created)"
        elif result.appended is False and apply_op == WikiApplyOp.APPEND_TIMELINE:
            suffix = " (duplicate skipped)"
        return f"{result.message}{suffix}"

    return [wiki_ingest, wiki_query, wiki_apply]


async def _archive_query_result(
    structure: WikiStructure,
    compiler: WikiCompiler,
    question: str,
    answer: str,
) -> None:
    """Archive a high-quality Q&A pair back into raw/ for knowledge compounding."""
    content = f"# Query\n\n{question}\n\n# Answer\n\n{answer}"
    doc_hash = hashlib.sha256(question.encode()).hexdigest()[:12]
    filename = f"query_archive_{doc_hash}.md"

    from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate import (
        RawConflictPolicy,
        RawPublishRequest,
        publish_raw,
    )

    result = await publish_raw(
        structure,
        RawPublishRequest(
            relative_path=filename,
            content=content,
            conflict_policy=RawConflictPolicy.PUT_IF_ABSENT,
        ),
        caller="agent",
    )
    if not result.written:
        return

    compiler.enqueue_file(result.absolute_path)
    logger.info(f"Archived query result for knowledge compounding: {filename}")
