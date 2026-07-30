"""
[INPUT] ArtifactVault, Artifact ORM, AssessmentImportLedger ORM, MilestoneService, KanbanService
[OUTPUT] AssessmentImportService: artifact -> milestone/kanban import orchestration
[POS] 项目评估导入服务。将评估类 Markdown 工件解析为里程碑和看板任务，基于不可变导入台账执行幂等拦截并输出回执。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from myrm_agent_harness.toolkits.kanban.types import (
    KANBAN_SOURCE_CHAT_METADATA_KEY,
    TaskPriority,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.database.connection import get_session
from app.database.models.artifact import Artifact, ArtifactVersion
from app.database.models.assessment_import import AssessmentImportLedger
from app.database.models.project import Project
from app.platform_utils.workspace_root import get_workspace_root
from app.services.kanban import KanbanService
from app.services.project.milestone_service import MilestoneService

_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+\.\s+)(?:\[[ xX]\]\s*)?(.+?)\s*$")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_INLINE_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MULTISPACE_RE = re.compile(r"\s+")
_IMPORT_BOARD_DESCRIPTION_PREFIX = "Imported from artifact "
_TEXT_TOKEN_RE = re.compile(r"[A-Za-z0-9\u4e00-\u9fff]")

_DEFAULT_MAX_MILESTONES = 8
_DEFAULT_MAX_TASKS_PER_MILESTONE = 25
logger = logging.getLogger(__name__)
ERROR_ARTIFACT_VERSION_ALREADY_IMPORTED = "Artifact version already imported for this project"
ERROR_NO_ACTIONABLE_TASKS = "Artifact markdown has checklist items but none are actionable tasks"
ERROR_NO_IMPORTABLE_TASKS = "Artifact markdown does not contain importable task list items"
_NON_ACTIONABLE_PREFIXES: tuple[str, ...] = (
    "note",
    "notes",
    "summary",
    "context",
    "background",
    "risk",
    "risks",
    "assumption",
    "assumptions",
    "说明",
    "背景",
    "风险",
    "假设",
    "总结",
    "备注",
)


@dataclass(slots=True, frozen=True)
class ParsedMilestone:
    title: str
    description: str
    tasks: list[str]


def _clean_inline_markdown(text: str) -> str:
    normalized = _INLINE_LINK_RE.sub(r"\1", text)
    normalized = _INLINE_CODE_RE.sub(r"\1", normalized)
    normalized = _INLINE_BOLD_RE.sub(r"\1", normalized)
    normalized = normalized.replace("*", " ").replace("_", " ")
    normalized = _MULTISPACE_RE.sub(" ", normalized)
    return normalized.strip(" -:\t")


def _clip(text: str, limit: int) -> str:
    trimmed = text.strip()
    if len(trimmed) <= limit:
        return trimmed
    return trimmed[: max(0, limit - 1)].rstrip() + "…"


def _extract_sections(content: str) -> list[tuple[int, str, list[str]]]:
    sections: list[tuple[int, str, list[str]]] = []
    current_level: int | None = None
    current_title = ""
    current_lines: list[str] = []

    for raw_line in content.splitlines():
        heading_match = _HEADING_RE.match(raw_line)
        if heading_match:
            if current_level is not None:
                sections.append((current_level, current_title, current_lines))
            current_level = len(heading_match.group(1))
            current_title = _clean_inline_markdown(heading_match.group(2))
            current_lines = []
            continue
        if current_level is not None:
            current_lines.append(raw_line)

    if current_level is not None:
        sections.append((current_level, current_title, current_lines))

    return sections


def _is_actionable_task(text: str) -> bool:
    normalized = text.strip()
    if len(normalized) < 4:
        return False
    if normalized.startswith(("http://", "https://")):
        return False
    lower = normalized.lower().lstrip("-*# ").strip()
    for prefix in _NON_ACTIONABLE_PREFIXES:
        if lower == prefix or lower.startswith(f"{prefix}:") or lower.startswith(f"{prefix}："):
            return False
    if _TEXT_TOKEN_RE.search(normalized) is None:
        return False
    return True


def _extract_tasks(lines: list[str], max_tasks: int) -> tuple[list[str], bool]:
    tasks: list[str] = []
    seen: set[str] = set()
    had_list_items = False
    for line in lines:
        match = _LIST_ITEM_RE.match(line)
        if not match:
            continue
        had_list_items = True
        task_text = _clean_inline_markdown(match.group(1))
        if not task_text:
            continue
        clipped = _clip(task_text, 500)
        if not _is_actionable_task(clipped):
            continue
        lower = clipped.lower()
        if lower in seen:
            continue
        seen.add(lower)
        tasks.append(clipped)
        if len(tasks) >= max_tasks:
            break
    return tasks, had_list_items


def _extract_description(lines: list[str]) -> str:
    fragments: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _LIST_ITEM_RE.match(stripped):
            continue
        if stripped.startswith("```"):
            continue
        cleaned = _clean_inline_markdown(stripped)
        if cleaned:
            fragments.append(cleaned)
        if len(fragments) >= 3:
            break
    return _clip(" ".join(fragments), 5000)


def parse_assessment_markdown(
    content: str,
    *,
    fallback_title: str,
    max_milestones: int = _DEFAULT_MAX_MILESTONES,
    max_tasks_per_milestone: int = _DEFAULT_MAX_TASKS_PER_MILESTONE,
) -> list[ParsedMilestone]:
    if max_milestones < 1:
        raise ValueError("max_milestones must be at least 1")
    if max_tasks_per_milestone < 1:
        raise ValueError("max_tasks_per_milestone must be at least 1")

    sections = _extract_sections(content)
    parsed: list[ParsedMilestone] = []
    had_list_items_anywhere = False

    for level, title, lines in sections:
        if level > 3:
            continue
        tasks, had_list_items = _extract_tasks(lines, max_tasks=max_tasks_per_milestone)
        had_list_items_anywhere = had_list_items_anywhere or had_list_items
        if not tasks:
            continue
        milestone_title = _clip(title or fallback_title, 500)
        description = _extract_description(lines)
        parsed.append(ParsedMilestone(title=milestone_title, description=description, tasks=tasks))
        if len(parsed) >= max_milestones:
            break

    if parsed:
        return parsed

    doc_tasks, had_doc_list_items = _extract_tasks(
        content.splitlines(),
        max_tasks=max_tasks_per_milestone,
    )
    if not doc_tasks:
        if had_list_items_anywhere or had_doc_list_items:
            raise ValueError(ERROR_NO_ACTIONABLE_TASKS)
        raise ValueError(ERROR_NO_IMPORTABLE_TASKS)

    default_title = _clip(fallback_title or "Assessment Import", 500)
    return [ParsedMilestone(title=default_title, description="", tasks=doc_tasks)]


def _latest_version(artifact: Artifact) -> ArtifactVersion:
    if not artifact.versions:
        raise ValueError("Artifact has no versions")
    return sorted(artifact.versions, key=lambda version: version.created_at, reverse=True)[0]


async def _load_artifact_content(
    artifact_id: str,
) -> tuple[Artifact, ArtifactVersion, str]:
    async with get_session() as db:
        stmt = (
            select(Artifact)
            .options(selectinload(Artifact.versions))
            .where(Artifact.id == artifact_id, Artifact.is_deleted.is_(False))
        )
        result = await db.execute(stmt)
        artifact = result.scalars().first()
    if artifact is None:
        raise FileNotFoundError("Artifact not found")

    latest = _latest_version(artifact)
    vault_uri = latest.vault_uri
    object_id = vault_uri[len("vault://"):] if vault_uri.startswith("vault://") else vault_uri
    object_path = ArtifactVault(get_workspace_root()).get_object_path(object_id)
    if not object_path.exists():
        raise FileNotFoundError("Artifact content not found on disk")

    content = object_path.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError("Artifact content is empty")

    return artifact, latest, content


async def _assert_project_exists(project_id: str) -> None:
    async with get_session() as db:
        stmt = select(Project).where(Project.id == project_id)
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise FileNotFoundError("Project not found")


def _build_import_board_description(artifact_id: str) -> str:
    return f"{_IMPORT_BOARD_DESCRIPTION_PREFIX}{artifact_id}"


async def _reserve_import_slot(
    project_id: str,
    *,
    artifact_id: str,
    artifact_version_id: str,
    source_chat_id: str | None,
) -> int:
    async with get_session() as db:
        ledger = AssessmentImportLedger(
            project_id=project_id,
            artifact_id=artifact_id,
            artifact_version_id=artifact_version_id,
            source_chat_id=source_chat_id,
            status="reserved",
        )
        db.add(ledger)
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            stmt = select(AssessmentImportLedger.id).where(
                AssessmentImportLedger.project_id == project_id,
                AssessmentImportLedger.artifact_version_id == artifact_version_id,
            )
            exists = (await db.execute(stmt)).scalar_one_or_none()
            if exists is not None:
                raise ValueError(ERROR_ARTIFACT_VERSION_ALREADY_IMPORTED) from exc
            raise
        await db.refresh(ledger)
        return int(ledger.id)


async def _finalize_import_slot(
    import_id: int,
    *,
    total_milestones: int,
    total_tasks: int,
) -> None:
    async with get_session() as db:
        slot = await db.get(AssessmentImportLedger, import_id)
        if slot is None:
            return
        slot.status = "completed"
        slot.total_milestones = total_milestones
        slot.total_tasks = total_tasks
        await db.commit()


async def _release_import_slot(import_id: int) -> None:
    async with get_session() as db:
        slot = await db.get(AssessmentImportLedger, import_id)
        if slot is None:
            return
        await db.delete(slot)
        await db.commit()


def _build_board_name(milestone_title: str, index: int, total: int) -> str:
    if total <= 1:
        return _clip(milestone_title, 255)
    return _clip(f"{milestone_title} ({index}/{total})", 255)


class AssessmentImportService:
    """导入评估工件到项目里程碑和看板任务。"""

    @staticmethod
    async def import_from_artifact(
        project_id: str,
        *,
        artifact_id: str,
        source_chat_id: str | None = None,
        max_milestones: int = _DEFAULT_MAX_MILESTONES,
        max_tasks_per_milestone: int = _DEFAULT_MAX_TASKS_PER_MILESTONE,
    ) -> dict[str, object]:
        await _assert_project_exists(project_id)
        artifact, latest_version, content = await _load_artifact_content(artifact_id)
        parsed_milestones = parse_assessment_markdown(
            content,
            fallback_title=artifact.name or "Assessment Import",
            max_milestones=max_milestones,
            max_tasks_per_milestone=max_tasks_per_milestone,
        )

        kanban_service = KanbanService.get_instance()
        imported_rows: list[dict[str, object]] = []
        total_tasks = 0
        effective_source_chat_id = source_chat_id or artifact.chat_id
        imported_at = datetime.now(UTC).isoformat()
        created_board_ids: list[str] = []
        created_milestone_ids: list[str] = []
        import_id = await _reserve_import_slot(
            project_id,
            artifact_id=artifact.id,
            artifact_version_id=latest_version.id,
            source_chat_id=effective_source_chat_id,
        )

        try:
            for index, parsed in enumerate(parsed_milestones, start=1):
                milestone = await MilestoneService.create_milestone(
                    project_id,
                    title=parsed.title,
                    description=parsed.description,
                    acceptance_criteria="",
                )
                milestone_id = str(milestone["id"])
                created_milestone_ids.append(milestone_id)

                board = await kanban_service.create_board(
                    name=_build_board_name(parsed.title, index, len(parsed_milestones)),
                    description=_build_import_board_description(artifact.id),
                    project_id=project_id,
                    milestone_id=milestone_id,
                )
                created_board_ids.append(board.board_id)

                created_tasks = 0
                for task_title in parsed.tasks:
                    metadata_patch: dict[str, object] = {
                        "assessment_import": {
                            "artifact_id": artifact.id,
                            "artifact_version_id": latest_version.id,
                            "project_id": project_id,
                            "milestone_id": milestone_id,
                            "imported_at": imported_at,
                        }
                    }
                    if effective_source_chat_id:
                        metadata_patch[KANBAN_SOURCE_CHAT_METADATA_KEY] = effective_source_chat_id

                    await kanban_service.add_task(
                        board_id=board.board_id,
                        title=task_title,
                        priority=TaskPriority.NORMAL,
                        metadata_patch=metadata_patch,
                    )
                    created_tasks += 1

                total_tasks += created_tasks
                imported_rows.append(
                    {
                        "milestone_id": milestone_id,
                        "milestone_title": milestone["title"],
                        "board_id": board.board_id,
                        "board_name": board.name,
                        "task_count": created_tasks,
                    }
                )
        except Exception:
            for board_id in reversed(created_board_ids):
                try:
                    await kanban_service.delete_board(board_id)
                except Exception as cleanup_error:
                    logger.warning("Failed to rollback imported board %s: %s", board_id, cleanup_error)
            for milestone_id in reversed(created_milestone_ids):
                try:
                    await MilestoneService.delete_milestone(milestone_id)
                except Exception as cleanup_error:
                    logger.warning("Failed to rollback imported milestone %s: %s", milestone_id, cleanup_error)
            try:
                await _release_import_slot(import_id)
            except Exception as cleanup_error:
                logger.warning("Failed to rollback import slot %s: %s", import_id, cleanup_error)
            raise

        await _finalize_import_slot(
            import_id,
            total_milestones=len(imported_rows),
            total_tasks=total_tasks,
        )
        return {
            "import_id": import_id,
            "project_id": project_id,
            "artifact_id": artifact.id,
            "artifact_version_id": latest_version.id,
            "source_chat_id": effective_source_chat_id,
            "imported_milestones": imported_rows,
            "total_milestones": len(imported_rows),
            "total_tasks": total_tasks,
            "imported_at": imported_at,
        }
