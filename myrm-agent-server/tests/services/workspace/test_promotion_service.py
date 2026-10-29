"""Unit tests for the scratchpad promotion service's path fencing.

[INPUT]
- app.services.workspace.promotion.service::ProjectPromotionService
- myrm_agent_harness.agent.context_management.scratchpad_promotion (seed compilation)

[OUTPUT]
- Coverage that a seeded document can only land inside the project directory.

[POS]
myrm-agent-server/tests/services/workspace/test_promotion_service.py
"""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.agent.context_management.scratchpad_promotion import (
    ScratchpadDraft,
    ScratchpadPromotionEngine,
    SeedDocument,
)

from app.services.workspace.promotion.service import ProjectPromotionService


def test_a_seeded_document_that_leaves_the_project_directory_is_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seed = ScratchpadPromotionEngine.compile_seed(ScratchpadDraft(title="Alpha", content="body"))
    # A sibling whose name merely starts with the project directory's name is outside it.
    seed.seeded_documents.append(SeedDocument(relative_path="../alpha-evil/note.md", content="nope"))
    monkeypatch.setattr(ScratchpadPromotionEngine, "compile_seed", classmethod(lambda cls, draft, config=None: seed))

    result = ProjectPromotionService.promote_scratchpad("Alpha", "body", target_project_name="alpha", base_dir=tmp_path)

    assert "../alpha-evil/note.md" not in result.created_files
    assert not (tmp_path / "alpha-evil").exists()


def test_seeded_documents_inside_the_project_directory_are_written(tmp_path: Path) -> None:
    result = ProjectPromotionService.promote_scratchpad("Alpha", "body", target_project_name="alpha", base_dir=tmp_path)

    assert "README.md" in result.created_files
    assert (tmp_path / "alpha" / "README.md").is_file()
