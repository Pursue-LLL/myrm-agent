"""Kanban TaskRunner — bridges KanbanTask to the Agent execution pipeline.

Implements the ``TaskRunner`` protocol from the harness layer, wiring each
task through ``AgentProfileResolver`` → ``AgentFactory`` → ``GeneralAgent``
so that WorkBoard tasks execute with the full agent profile (model, skills,
tools, memory, security).

[INPUT]
- myrm_agent_harness.toolkits.kanban.protocols::TaskRunner (POS: Harness protocol.)
- myrm_agent_harness.toolkits.kanban.context_builder::build_task_context (POS: Worker context.)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask, TaskTimeoutError (POS: Kanban domain types.)
- app.services.agent.profile_resolver::AgentProfileResolver (POS: Agent profile resolution.)
- app.ai_agents.agents::AgentFactory, GeneralAgentParams (POS: Agent creation.)
- app.core.storage::files_service (POS: File storage for attachment content resolution.)
- app.services.files.attachment_settings::should_extract_document_text (POS: extractDocumentText personal setting.)
- app.services.files.content_extraction (POS: PDF/Office bytes-to-text for attachments.)

[OUTPUT]
- KanbanTaskRunner: Concrete TaskRunner implementation.
- _build_multimodal_query: Multimodal LLM input (image_url; PDF/Office text or [Attachment: name] fallback).

[POS]
Server-layer TaskRunner that executes kanban tasks through the agent pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from myrm_agent_harness.toolkits.kanban.context_builder import build_task_context
from myrm_agent_harness.toolkits.kanban.protocols import KanbanStore
from myrm_agent_harness.toolkits.kanban.types import (
    KanbanTask,
    TaskEventKind,
    TaskTimeoutError,
)

from app.services.agent.profile_resolver import (
    DEFAULT_ENABLED_BUILTIN_TOOLS,
    resolve_builtin_tool_flags,
)

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 600
_CHANNEL_NAME = "kanban"
_WORKTREE_DIR_NAME = ".worktrees"


@dataclass
class _StreamAccumulator:
    """Accumulates agent stream events into a final result."""

    chunks: list[str] = field(default_factory=list)
    usage: dict[str, int] | None = None
    error: str | None = None

    def add(self, event: dict[str, object]) -> None:
        event_type = event.get("type", "")
        if event_type == "message" and isinstance(event.get("data"), str):
            self.chunks.append(str(event["data"]))
        elif event_type == "message_end" and isinstance(event.get("usage"), dict):
            raw = event["usage"]
            self.usage = {str(k): _coerce_int(v) for k, v in raw.items()}
        elif event_type == "error":
            error_msg = event.get("error", "unknown agent error")
            error_type = event.get("error_type", "")
            self.error = f"{error_type}: {error_msg}" if error_type else str(error_msg)

    def to_result(self) -> tuple[bool, str]:
        if self.error:
            return False, self.error
        text = "".join(self.chunks).strip()
        if not text:
            return False, "agent returned empty response"
        return True, text


def _coerce_int(v: object) -> int:
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            return 0
    return 0


_IMAGE_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".svg",
        ".tiff",
        ".ico",
        ".avif",
    }
)
_PDF_EXTENSIONS = frozenset({".pdf"})
_DOCUMENT_EXTENSIONS = frozenset(
    {
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".odt",
        ".ods",
        ".odp",
        ".rtf",
    }
)


def _classify_content_type(content_type: str, filename: str) -> str:
    """Classify a file as 'image', 'pdf', 'document', or 'other'."""
    import os

    ext = os.path.splitext(filename)[1].lower()
    if ext in _IMAGE_EXTENSIONS or content_type.startswith("image/"):
        return "image"
    if ext in _PDF_EXTENSIONS or content_type == "application/pdf":
        return "pdf"
    if ext in _DOCUMENT_EXTENSIONS:
        return "document"
    return "other"


class KanbanTaskRunner:
    """Concrete TaskRunner that executes tasks through the Agent pipeline.

    Each task is executed by creating a ``GeneralAgent`` with the task's
    assigned agent profile (or the default profile if none is assigned).
    The task context (description, prior attempts, parent results, comments)
    is assembled by ``build_task_context`` and passed as the agent prompt.
    """

    def __init__(
        self,
        store: KanbanStore,
        *,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._store = store
        self._timeout_seconds = timeout_seconds

    async def run(self, task: KanbanTask) -> tuple[bool, str]:
        """Execute a kanban task through the agent pipeline.

        Effective timeout: ``task.max_runtime_seconds`` when set, otherwise
        ``self._timeout_seconds`` (constructor default).  On timeout a
        ``TaskTimeoutError`` is raised so the dispatcher can distinguish
        timeouts from generic crashes.
        """
        context = await build_task_context(self._store, task.task_id)
        profile = await self._resolve_profile(task.agent_id)

        query_input = await self._build_multimodal_query(task, context)

        workspace_root = await self._resolve_workspace(task)

        effective_timeout = task.max_runtime_seconds or self._timeout_seconds
        t0 = time.monotonic()
        try:
            return await asyncio.wait_for(
                self._execute_agent(task, query_input, profile, workspace_root),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - t0
            logger.warning(
                "Kanban task %s timed out after %.0fs (limit %ds)",
                task.task_id[:8],
                elapsed,
                effective_timeout,
            )
            raise TaskTimeoutError(
                task_id=task.task_id,
                elapsed_seconds=elapsed,
                limit_seconds=effective_timeout,
            ) from None
        except Exception as exc:
            logger.warning("Kanban task %s failed: %s", task.task_id[:8], exc)
            return False, str(exc)

    async def _resolve_base_dir(self, task: KanbanTask) -> str | None:
        """Resolve effective base directory: task-level > board-level default."""
        if task.workspace_path:
            return task.workspace_path
        if not task.board_id:
            return None
        board = await self._store.get_board(task.board_id)
        if board and board.settings and board.settings.default_workdir:
            return board.settings.default_workdir
        return None

    async def _resolve_workspace(self, task: KanbanTask) -> str | None:
        """Resolve the effective workspace root for a task.

        Priority: task.workspace_path > board.settings.default_workdir > None.
        When ``task.branch`` is set, creates a git worktree under
        ``<workspace>/.worktrees/<safe_branch_name>/`` and returns its path.
        """
        base_dir = await self._resolve_base_dir(task)

        if not base_dir:
            return None

        if not task.branch:
            return base_dir

        worktree_path = await self._create_worktree(
            base_dir,
            task.branch,
            task.task_id,
        )
        if worktree_path:
            await self._store.add_event(
                task.task_id,
                TaskEventKind.BRANCH_SWITCHED,
                payload={
                    "branch": task.branch,
                    "worktree_path": worktree_path,
                },
            )
            return worktree_path

        logger.warning(
            "Worktree creation failed for task %s, falling back to base_dir",
            task.task_id[:8],
        )
        return base_dir

    @staticmethod
    def _worktree_dir(base_dir: str, branch: str, task_id: str) -> str:
        safe_name = branch.replace("/", "-").replace("\\", "-")
        return os.path.join(
            base_dir,
            _WORKTREE_DIR_NAME,
            f"{safe_name}-{task_id[:8]}",
        )

    async def _create_worktree(
        self,
        base_dir: str,
        branch: str,
        task_id: str,
    ) -> str | None:
        """Create a git worktree for isolated task execution."""
        worktree_dir = self._worktree_dir(base_dir, branch, task_id)

        if Path(worktree_dir).exists():
            logger.info(
                "Worktree already exists at %s for task %s",
                worktree_dir,
                task_id[:8],
            )
            return worktree_dir

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "git",
                    "worktree",
                    "add",
                    "--force",
                    "-B",
                    branch,
                    worktree_dir,
                    "HEAD",
                ],
                cwd=base_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(
                    "git worktree add failed (rc=%d): %s",
                    result.returncode,
                    result.stderr.strip(),
                )
                return None

            logger.info(
                "Created worktree at %s (branch=%s) for task %s",
                worktree_dir,
                branch,
                task_id[:8],
            )
            return worktree_dir
        except Exception as exc:
            logger.warning(
                "Failed to create worktree for task %s: %s",
                task_id[:8],
                exc,
            )
            return None

    async def cleanup_worktree(self, task: KanbanTask) -> None:
        """Remove the git worktree when a task is archived.

        Called by the service layer on ARCHIVED transitions.
        """
        if not task.branch:
            return

        base_dir = await self._resolve_base_dir(task)
        if not base_dir:
            return

        worktree_dir = self._worktree_dir(base_dir, task.branch, task.task_id)

        if not Path(worktree_dir).exists():
            return

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "worktree", "remove", "--force", worktree_dir],
                cwd=base_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info(
                    "Cleaned up worktree at %s for archived task %s",
                    worktree_dir,
                    task.task_id[:8],
                )
            else:
                logger.warning(
                    "git worktree remove failed (rc=%d): %s",
                    result.returncode,
                    result.stderr.strip(),
                )
        except Exception as exc:
            logger.warning(
                "Failed to cleanup worktree for task %s: %s",
                task.task_id[:8],
                exc,
            )

    async def _build_multimodal_query(
        self,
        task: KanbanTask,
        text_context: str,
    ) -> str | list[dict[str, object]]:
        """Assemble a multimodal query when the task has attachments.

        - Images → OpenAI ``image_url`` content blocks
        - PDFs → extract text via pdf_extract service
        - Documents → extract text via document_extract service
        - Other → skip (agent can access files via tools)

        Returns plain text if no image attachments exist.
        """
        attachment_ids = await self._load_attachment_ids(task.task_id)
        if not attachment_ids:
            return text_context

        from app.core.channel_bridge.config_loader import load_user_configs
        from app.core.storage import files_service
        from app.services.files.attachment_settings import should_extract_document_text

        configs = await load_user_configs()
        extract_documents = should_extract_document_text(configs.personal_settings_dict)

        image_urls: list[str] = []
        extra_text_parts: list[str] = []

        for fid in attachment_ids:
            try:
                file_info = await files_service.get_file(fid)
                if file_info is None:
                    logger.warning("Attachment %s not found, skipping", fid)
                    continue

                kind = _classify_content_type(
                    file_info.content_type,
                    file_info.filename,
                )
                content_url = f"/api/v1/files/{fid}/content"

                if kind == "image":
                    image_urls.append(content_url)
                elif kind == "pdf":
                    if extract_documents:
                        extracted = await self._extract_pdf_text(fid)
                        if extracted:
                            extra_text_parts.append(f"\n## Attachment: {file_info.filename}\n{extracted}")
                        else:
                            extra_text_parts.append(f"\n[Attachment: {file_info.filename}]")
                    else:
                        extra_text_parts.append(f"\n[Attachment: {file_info.filename}]")
                elif kind == "document":
                    if extract_documents:
                        extracted = await self._extract_document_text(fid)
                        if extracted:
                            extra_text_parts.append(f"\n## Attachment: {file_info.filename}\n{extracted}")
                        else:
                            extra_text_parts.append(f"\n[Attachment: {file_info.filename}]")
                    else:
                        extra_text_parts.append(f"\n[Attachment: {file_info.filename}]")
            except Exception:
                logger.warning("Failed to process attachment %s", fid, exc_info=True)

        full_text = text_context
        if extra_text_parts:
            full_text += "\n" + "\n".join(extra_text_parts)

        if not image_urls:
            return full_text

        content: list[dict[str, object]] = [
            {"type": "text", "text": full_text},
        ]
        for url in image_urls:
            content.append(
                {"type": "image_url", "image_url": {"url": url}},
            )
        return content

    async def _load_attachment_ids(self, task_id: str) -> list[str]:
        """Load attachment file IDs from DB."""
        from app.core.kanban.adapters.sqlalchemy_mapping import get_attachment_ids
        from app.database.connection import get_session
        from app.database.models.kanban import KanbanTaskModel

        async with get_session() as session:
            m = await session.get(KanbanTaskModel, task_id)
            return get_attachment_ids(m) if m else []

    async def _extract_pdf_text(self, file_id: str) -> str:
        """Extract text from a PDF file using the pdf_extract service."""
        try:
            from app.core.storage import files_service

            content = await files_service.get_file_content(file_id)
            if not content:
                return ""

            from app.services.files.content_extraction import extract_pdf_text_from_bytes

            return await extract_pdf_text_from_bytes(content)
        except Exception:
            logger.warning("PDF extraction failed for %s", file_id, exc_info=True)
            return ""

    async def _extract_document_text(self, file_id: str) -> str:
        """Extract text from an Office document."""
        try:
            from app.core.storage import files_service

            content = await files_service.get_file_content(file_id)
            if not content:
                return ""

            from app.services.files.content_extraction import (
                extract_document_text_from_bytes,
            )

            meta = await files_service.get_file(file_id)
            filename = getattr(meta, "filename", "") if meta else ""
            return await extract_document_text_from_bytes(content, filename=filename or "document.bin")
        except Exception:
            logger.warning("Document extraction failed for %s", file_id, exc_info=True)
            return ""

    async def _resolve_profile(
        self,
        agent_id: str | None,
    ) -> _ResolvedProfile | None:
        """Resolve agent profile, returning None for default profile."""
        if not agent_id:
            return None
        try:
            from app.services.agent.profile_resolver import get_agent_profile_resolver

            resolved = await get_agent_profile_resolver().resolve(agent_id)
            if resolved is None:
                logger.warning("Agent %s not found, using default profile", agent_id)
                return None
            return _ResolvedProfile.from_resolved(resolved)
        except Exception as exc:
            logger.warning("Failed to resolve agent %s: %s", agent_id, exc)
            return None

    async def _execute_agent(
        self,
        task: KanbanTask,
        context: str | list[dict[str, object]],
        profile: _ResolvedProfile | None,
        workspace_root: str | None = None,
    ) -> tuple[bool, str]:
        """Create and run a GeneralAgent for the task."""
        from app.ai_agents.agents import AgentFactory, GeneralAgentParams
        from app.core.channel_bridge.config_loader import load_user_configs
        from app.core.channel_bridge.config_parsers import (
            extract_fallback_model_configs,
            extract_retrieval_models,
            verify_search_service_available,
        )
        from app.core.channel_bridge.model_resolver import (
            enrich_model_context_window,
            resolve_model_config,
        )

        user_cfgs = await load_user_configs()

        board = await self._store.get_board(task.board_id) if task.board_id else None
        zombie_timeout = board.settings.zombie_timeout_seconds if board and board.settings else 120

        embedding_cfg, reranker_cfg = extract_retrieval_models(user_cfgs.retrieval_dict)
        fallback_model_cfg, fallback_lite_model_cfg = extract_fallback_model_configs(
            user_cfgs.providers_dict,
        )

        from myrm_agent_harness.toolkits.retriever.embedding.factory import (
            EmbeddingConfig,
        )
        from myrm_agent_harness.toolkits.retriever.reranker.factory import (
            RerankerConfig,
        )

        GeneralAgentParams.model_rebuild(
            _types_namespace={
                "EmbeddingConfig": EmbeddingConfig,
                "RerankerConfig": RerankerConfig,
            },
        )

        # Build security config — auto-enable YOLO for unattended execution
        security_config_raw = dict(user_cfgs.security_config_dict or {})
        if not security_config_raw.get("yolo_mode_enabled", False):
            security_config_raw["yolo_mode_enabled"] = True
            security_config_raw["yolo_mode_enabled_at"] = time.time()
            security_config_raw["yolo_mode_timeout"] = None

        # Resolve model config
        model_override = profile.model if profile else None
        model_cfg = resolve_model_config(
            user_cfgs.providers_dict,
            model_override=model_override,
        )
        model_cfg = enrich_model_context_window(model_cfg, user_cfgs.providers_dict)

        # Resolve shared memory contexts
        memory_shared_context_ids: list[str] = []
        try:
            from app.services.memory.shared_context import resolve_shared_context_ids

            memory_shared_context_ids = await resolve_shared_context_ids(
                agent_id=task.agent_id,
                channel_id=_CHANNEL_NAME,
                conversation_id=task.task_id,
                task_id=task.task_id,
            )
        except Exception as exc:
            logger.warning(
                "Task %s: failed to resolve shared memory contexts: %s",
                task.task_id[:8],
                exc,
            )

        enabled_builtin_tools: list[str] = list(DEFAULT_ENABLED_BUILTIN_TOOLS)
        if profile is not None:
            enabled_builtin_tools = list(profile.enabled_builtin_tools)

        # Worker agents always get kanban tools
        if "kanban" not in enabled_builtin_tools:
            enabled_builtin_tools.append("kanban")

        task_user_instructions: str | None = profile.system_prompt if profile else None
        if profile and profile.agent_type == "team" and profile.subagent_ids:
            from app.ai_agents.team_protocol import build_leader_protocol_prompt

            leader_protocol = await build_leader_protocol_prompt(list(profile.subagent_ids))
            task_user_instructions = (
                f"{task_user_instructions}\n\n{leader_protocol}" if task_user_instructions else leader_protocol
            )

        declared_roots: tuple[str, ...] = ()
        if workspace_root:
            declared_roots = (workspace_root,)

        params = GeneralAgentParams(
            query=context,
            model_cfg=model_cfg,
            fallback_model_cfg=fallback_model_cfg,
            fallback_lite_model_cfg=fallback_lite_model_cfg,
            search_service_cfg=user_cfgs.search_cfg,
            chat_id=task.task_id,
            agent_id=task.agent_id,
            embedding_config=embedding_cfg,
            reranker_config=reranker_cfg,
            security_config_raw=security_config_raw,
            agent_security_raw=profile.security_overrides if profile else None,
            channel_name=_CHANNEL_NAME,
            declared_allowed_roots=declared_roots,
            enable_web_search=(
                user_cfgs.search_is_user_configured and await verify_search_service_available(user_cfgs.search_cfg)
            ),
            kanban_tool_mode="worker",
            kanban_current_task_id=task.task_id,
            kanban_max_runtime_seconds=task.max_runtime_seconds,
            kanban_zombie_timeout_seconds=zombie_timeout,
            **resolve_builtin_tool_flags(enabled_builtin_tools),
            auto_restore_domains=list(profile.auto_restore_domains) if profile else [],
            unattended_mode=True,
            user_instructions=task_user_instructions,
            agent_skill_ids=list(dict.fromkeys((*(profile.skill_ids if profile else []), *task.extra_skill_ids))),
            subagent_ids=(list(profile.subagent_ids) if profile and profile.subagent_ids else None),
            max_iterations=profile.max_iterations if profile else None,
            memory_policy=profile.memory_policy if profile else None,
            memory_decay_profile=profile.memory_decay_profile if profile else None,
            engine_params=profile.engine_params if profile else None,
            memory_shared_context_ids=memory_shared_context_ids,
        )

        agent = AgentFactory.create_general_agent(params)
        agent.approval_session_key = f"kanban:{task.task_id}"

        try:
            acc = _StreamAccumulator()

            async def _open_stream(query_input: object):
                async for event in agent.process_stream(
                    query=query_input,
                    chat_history=None,
                    chat_id=task.task_id,
                ):
                    if isinstance(event, dict):
                        yield event

            from app.services.agent.fission_config import (
                max_parallel_from_engine_params,
            )
            from app.services.agent.swarm_fission_resume import (
                stream_with_swarm_fission_resume,
            )

            async for event in stream_with_swarm_fission_resume(
                agent,
                context,
                _open_stream,
                max_concurrent=max_parallel_from_engine_params(profile.engine_params if profile else None),
            ):
                acc.add(event)

            return acc.to_result()
        finally:
            await agent.close()


@dataclass(frozen=True, slots=True)
class _ResolvedProfile:
    """Subset of ResolvedAgentProfile needed by KanbanTaskRunner."""

    agent_type: str
    system_prompt: str | None
    model: str | None
    skill_ids: tuple[str, ...]
    subagent_ids: tuple[str, ...] | None
    security_overrides: dict[str, object] | None
    max_iterations: int | None
    memory_policy: object | None
    memory_decay_profile: str | None
    engine_params: dict[str, object] | None
    auto_restore_domains: tuple[str, ...]
    enabled_builtin_tools: tuple[str, ...]

    @classmethod
    def from_resolved(cls, resolved: object) -> _ResolvedProfile:
        """Create from a ResolvedAgentProfile instance."""
        return cls(
            agent_type=getattr(resolved, "agent_type", "individual"),
            system_prompt=getattr(resolved, "system_prompt", None),
            model=getattr(resolved, "model", None),
            skill_ids=getattr(resolved, "skill_ids", ()),
            subagent_ids=getattr(resolved, "subagent_ids", None),
            security_overrides=getattr(resolved, "security_overrides", None),
            max_iterations=getattr(resolved, "max_iterations", None),
            memory_policy=getattr(resolved, "memory_policy", None),
            memory_decay_profile=getattr(resolved, "memory_decay_profile", None),
            engine_params=getattr(resolved, "engine_params", None),
            auto_restore_domains=getattr(resolved, "auto_restore_domains", ()),
            enabled_builtin_tools=getattr(resolved, "enabled_builtin_tools", DEFAULT_ENABLED_BUILTIN_TOOLS),
        )
