"""Memory→Wiki Automatic Archiving Service.

[INPUT]
langchain_core.language_models::BaseChatModel (POS: LangChain LLM 基类)
myrm_agent_harness.toolkits.wiki::WikiCompiler (POS: Wiki 编译核心引擎)
myrm_agent_harness.toolkits.wiki::WikiQueryEngine (POS: Wiki 查询与增强引擎)
myrm_agent_harness.toolkits.wiki::WikiLinter (POS: Wiki 健康维护核心引擎)
myrm_agent_harness.toolkits.wiki::WikiStructure (POS: Wiki 文件系统抽象层)
myrm_agent_harness.toolkits.wiki::WikiConfig (POS: Wiki 配置中心)

[OUTPUT]
MemoryToWikiArchiver: Memory→Wiki 自动归档服务

[POS]
业务层 Memory→Wiki 集成服务。负责将 SessionNotes（压缩后的会话记忆）自动归档到 Wiki：
触发条件（≥10 轮对话 + ≥500 字符），多租户隔离（per-user wiki），自动编译。
为用户提供持久化的、结构化的长期知识库。

## Integration with Memory System

1. **Trigger Point**: After context compression (when memory is summarized)
2. **Data Source**: SessionNotes (structured conversation memory)
3. **Archival Logic**: Extract high-value concepts and archive to wiki
4. **Benefits**:
   - Prevents context waste (valuable insights preserved)
   - Builds long-term knowledge (beyond single conversation)
   - Automatic organization (LLM structures the knowledge)

## Multi-Tenant Design

- Each user gets isolated wiki directory: `~/.myrm/users/{user_id}/wiki/`
- Memory archival runs per-user (no cross-tenant leakage)
- Control plane can aggregate wikis for organization-level knowledge
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory import MemoryManager

from myrm_agent_harness.toolkits.wiki import (
    SemanticSearchFn,
    WikiCompiler,
    WikiConfig,
    WikiLinter,
    WikiQueryEngine,
    WikiStructure,
)
from myrm_agent_harness.utils.logger_utils import get_agent_logger

logger = get_agent_logger(__name__)


class MemoryToWikiArchiver:
    """
    Automatic Memory→Wiki archiving service.

    Converts SessionNotes (compressed memory) into wiki articles.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        wiki_dir: Path | str | None = None,
        config: WikiConfig | None = None,
        search_fn: SemanticSearchFn | None = None,
        manager: "MemoryManager" | None = None,
    ):
        """
        Initialize archiver for the single-tenant sandbox.

        Args:
            llm: LLM for wiki compilation
            wiki_dir: Directory for the wiki (defaults to {MYRM_DATA_DIR}/wiki)
            config: Optional WikiConfig (uses defaults if not provided)
            search_fn: Optional semantic search function injected from retriever
        """
        self._llm = llm
        self._config = config or WikiConfig()

        from app.config.settings import settings

        if wiki_dir:
            resolved_wiki_dir = Path(wiki_dir).expanduser()
        else:
            resolved_wiki_dir = Path(settings.database.state_dir) / "wiki"

        public_dirs: list[Path] = []
        from app.platform_utils.deployment_capabilities import get_deployment_capabilities

        if get_deployment_capabilities().is_sandbox_instance:
            import os

            public_vols_env = os.getenv("MYRM_PUBLIC_WIKI_VOLUMES", "")
            public_dirs = [Path(v.strip()) for v in public_vols_env.split(";") if v.strip()]

        self._structure = WikiStructure(resolved_wiki_dir, public_dirs=public_dirs)
        self._structure.ensure_structure()

        from myrm_agent_harness.toolkits.wiki import WikiPendingEditsManager
        from myrm_agent_harness.toolkits.wiki.retrieval.indexer import WikiIndexer

        vector_store = getattr(manager, "_vector", None) if manager else None
        embedding = getattr(manager, "_embedding", None) if manager else None

        indexer = WikiIndexer(self._structure, self._config, vector_store=vector_store, embedding=embedding)

        self._compiler = WikiCompiler(llm, self._structure, self._config, indexer=indexer)
        self._query_engine = WikiQueryEngine(
            llm,
            self._structure,
            self._config,
            search_fn=search_fn,
        )
        self._query_engine._indexer = indexer
        self._linter = WikiLinter(llm, self._structure, self._config)

        self._queue = self._compiler._queue
        self._pending_mgr = WikiPendingEditsManager(self._structure, indexer=indexer)

        # Start the background drainer for this user's queue
        self._compiler.start_background_worker()

        logger.info(f"Initialized wiki archiver at {resolved_wiki_dir}")

    async def archive_memory(
        self,
        session_notes_json: str,
        conversation_turns: int,
    ) -> bool:
        """
        Archive memory to wiki if valuable.

        Args:
            session_notes_json: SessionNotes JSON from memory system
            conversation_turns: Number of conversation turns

        Returns:
            True if archived, False if skipped
        """
        if not self._config.auto_archive_enabled:
            logger.debug("Auto-archive disabled")
            return False

        if conversation_turns < self._config.auto_archive_min_turns:
            logger.debug(f"Skipping archive: {conversation_turns} < {self._config.auto_archive_min_turns} turns")
            return False

        try:
            import json

            parsed = json.loads(session_notes_json)
            if not isinstance(parsed, dict):
                logger.error("Session notes JSON must be an object")
                return False
            notes: dict[str, object] = parsed

            content = self._format_memory_as_document(notes)

            if len(content) < 500:
                logger.debug("Skipping archive: content too short")
                return False

            import uuid

            session_id = notes.get("session_id", "unknown")
            file_name = f"conversation_{session_id}_{uuid.uuid4().hex[:8]}.md"
            raw_path = self._structure.get_raw_file_path(file_name)
            raw_path.write_text(content, encoding="utf-8")
            logger.info(f"Archived memory to: {raw_path}")

            await self._compiler.compile_all()
            logger.info("Wiki compilation complete")

            return True

        except Exception as e:
            logger.error(f"Failed to archive memory: {e}")
            return False

    def _format_memory_as_document(self, notes: dict[str, object]) -> str:
        """Format SessionNotes as a markdown document for wiki ingestion."""
        lines = [
            f"# Conversation: {notes.get('session_id', 'unknown')}",
            "",
            f"**Created**: {notes.get('created_at', 'N/A')}",
            f"**Updated**: {notes.get('updated_at', 'N/A')}",
            "",
        ]

        primary_goal = notes.get("primary_goal")
        if primary_goal:
            lines.extend(
                [
                    "## Primary Goal",
                    "",
                    str(primary_goal),
                    "",
                ]
            )

        key_decisions = notes.get("key_decisions")
        if key_decisions and isinstance(key_decisions, list):
            lines.extend(["## Key Decisions", ""])
            for decision in key_decisions:
                lines.append(f"- {decision}")
            lines.append("")

        technical_context = notes.get("technical_context")
        if technical_context:
            lines.extend(
                [
                    "## Technical Context",
                    "",
                    str(technical_context),
                    "",
                ]
            )

        important_facts = notes.get("important_facts")
        if important_facts and isinstance(important_facts, list):
            lines.extend(["## Important Facts", ""])
            for fact in important_facts:
                lines.append(f"- {fact}")
            lines.append("")

        open_questions = notes.get("open_questions")
        if open_questions and isinstance(open_questions, list):
            lines.extend(["## Open Questions", ""])
            for question in open_questions:
                lines.append(f"- {question}")
            lines.append("")

        return "\n".join(lines)

    async def query_wiki(self, question: str) -> str:
        """
        Query user's wiki knowledge base.

        Args:
            question: Question to ask

        Returns:
            Answer from wiki
        """
        result = await self._query_engine.query(question)
        return str(result.answer)

    async def maintain_wiki(self) -> None:
        """Run wiki maintenance (health checks + auto-repair)."""
        await self._linter.lint_and_maintain()
        logger.info("Wiki maintenance complete")

    def get_wiki_path(self) -> Path:
        """Get the path to user's wiki directory."""
        return Path(self._structure.base_dir)
