"""Chat stream to structured Markdown Wiki knowledge extractor.

[INPUT]
- .models::ChatKnowledgeExtractRequest, ChatKnowledgeExtractResult
- re, time (standard library)

[OUTPUT]
- ChatToKnowledgeArchiver: Extracts core concepts, architecture decisions, and actions from raw chat context.

[POS]
Distills non-structured chat stream discussions into standardized Markdown Wiki pages ready for WikiCompiler ingestion.
"""

from __future__ import annotations

import re
from typing import List

from app.services.weekly_report.models import (
    ChatKnowledgeExtractRequest,
    ChatKnowledgeExtractResult,
)


class ChatToKnowledgeArchiver:
    """Extracts structured decisions and concepts from chat streams into Wiki format."""

    @staticmethod
    def _sanitize_slug(title: str) -> str:
        """Convert title into clean kebab-case or underscore-safe file path."""
        cleaned = re.sub(r"[^\w\s-]", "", title).strip().lower()
        return re.sub(r"[-\s]+", "_", cleaned) or "decision"

    @classmethod
    def extract_from_chat(
        cls, request: ChatKnowledgeExtractRequest
    ) -> ChatKnowledgeExtractResult:
        """Extract key concepts and format as standard Wiki Markdown document."""
        context = request.chat_context.strip()
        if not context:
            return ChatKnowledgeExtractResult(
                concept_title="",
                summary="",
                markdown_content="",
                wiki_rel_path="",
                tags=[],
                success=False,
                error_message="Empty chat context provided",
            )

        # Extract title from explicit heading, slash command, or first meaningful line
        lines = [line.strip() for line in context.splitlines() if line.strip()]
        title = "Team Discussion Decision"
        tags: List[str] = [request.channel, "chat_distilled"]

        for line in lines:
            if line.startswith("# "):
                title = line.lstrip("# ").strip()
                break
            elif "决策" in line or "方案" in line or "Decision:" in line or "RFC" in line:
                title = line.replace("Decision:", "").strip()
                break
            elif len(line) <= 60 and not line.startswith("//"):
                title = line
                break

        slug = cls._sanitize_slug(title)
        wiki_rel_path = f"{request.target_wiki_category}/{slug}.md"

        # Generate frontmatter and body
        summary = lines[0] if lines else "Distilled knowledge from discussion."
        markdown_body = cls._build_wiki_markdown(
            title=title,
            channel=request.channel,
            session_id=request.session_id,
            author=request.author,
            context=context,
            tags=tags,
        )

        return ChatKnowledgeExtractResult(
            concept_title=title,
            summary=summary,
            markdown_content=markdown_body,
            wiki_rel_path=wiki_rel_path,
            tags=tags,
            success=True,
        )

    @staticmethod
    def _build_wiki_markdown(
        title: str,
        channel: str,
        session_id: str,
        author: str,
        context: str,
        tags: List[str],
    ) -> str:
        """Construct standard Markdown format with YAML frontmatter."""
        tags_formatted = "\n".join(f"  - {t}" for t in tags)
        return (
            f"---\n"
            f"title: {title}\n"
            f"category: decisions\n"
            f"source_channel: {channel}\n"
            f"session_id: {session_id}\n"
            f"author: {author}\n"
            f"tags:\n{tags_formatted}\n"
            f"---\n\n"
            f"# {title}\n\n"
            f"## Context & Consensus\n\n"
            f"{context}\n\n"
            f"## Action Items & Impact\n"
            f"- Extracted automatically from channel `{channel}` conversation.\n"
        )
