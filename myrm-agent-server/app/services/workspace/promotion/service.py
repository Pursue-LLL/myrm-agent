"""[INPUT]
- ScratchpadDraft, PromotionConfig, ProjectSeed from myrm_agent_harness.agent.context_management.scratchpad_promotion
- pathlib.Path for safe filesystem persistence

[OUTPUT]
- PromotedProjectResult: Dataclass recording the result of workspace promotion
- ProjectPromotionService: Business layer service driving seed compilation, path fencing, and filesystem persistence

[POS]
Server-side workspace promotion service for converting ephemeral scratchpads into persisted project workspaces.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from myrm_agent_harness.agent.context_management.scratchpad_promotion import (
    ProjectSeed,
    PromotionConfig,
    ScratchpadDraft,
    ScratchpadPromotionEngine,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PromotedProjectResult:
    project_name: str
    target_directory: str
    created_files: list[str]
    initial_context_prompt: str
    promoted_at: str
    provenance_metadata: dict[str, str] = field(default_factory=dict)


class ProjectPromotionService:
    """Business service governing scratchpad promotion and filesystem materialization."""

    @classmethod
    def get_default_workspace_root(cls) -> Path:
        env_root = os.environ.get("MYRM_WORKSPACE_ROOT")
        if env_root:
            return Path(env_root).resolve()
        return (Path.cwd() / "data" / "workspaces").resolve()

    @classmethod
    def promote_scratchpad(
        cls,
        title: str,
        content: str,
        target_project_name: str | None = None,
        init_readme: bool = True,
        temporary_tags: list[str] | None = None,
        base_dir: Path | None = None,
    ) -> PromotedProjectResult:
        draft = ScratchpadDraft(
            title=title.strip(),
            content=content.strip(),
            temporary_tags=temporary_tags or [],
        )
        config = PromotionConfig(
            target_project_name=target_project_name.strip() if target_project_name else None,
            init_readme=init_readme,
        )

        seed: ProjectSeed = ScratchpadPromotionEngine.compile_seed(draft, config)
        clean_project_name = cls._sanitize_dirname(seed.project_name)

        root = (base_dir or cls.get_default_workspace_root()).resolve()
        target_dir = root / clean_project_name

        # Ensure directory is within root and exists
        target_dir.mkdir(parents=True, exist_ok=True)

        created_files: list[str] = []
        for doc in seed.seeded_documents:
            file_path = (target_dir / doc.relative_path).resolve()
            # Fencing check to avoid path traversal
            if not str(file_path).startswith(str(target_dir)):
                logger.warning(f"Skipping dangerous path traversal document: {doc.relative_path}")
                continue
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(doc.content, encoding="utf-8")
            created_files.append(doc.relative_path)

        promoted_at = datetime.now(timezone.utc).isoformat()
        provenance = dict(seed.provenance_metadata)
        provenance["promoted_at"] = promoted_at

        logger.info(
            f"Successfully promoted scratchpad '{title}' into project '{clean_project_name}' at {target_dir} ({len(created_files)} files)"
        )

        return PromotedProjectResult(
            project_name=clean_project_name,
            target_directory=str(target_dir),
            created_files=created_files,
            initial_context_prompt=seed.initial_context_prompt,
            promoted_at=promoted_at,
            provenance_metadata=provenance,
        )

    @classmethod
    def _sanitize_dirname(cls, raw_name: str) -> str:
        clean = re.sub(r"[^\w\s-]", "", raw_name).strip()
        slug = "-".join(clean.split()).lower()
        return slug or "promoted-scratchpad-project"
