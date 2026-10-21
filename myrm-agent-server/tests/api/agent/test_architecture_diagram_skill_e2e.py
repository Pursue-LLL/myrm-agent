"""Contract test for the architecture-diagram prebuilt skill.

Validates what the server owns for the skill: it syncs from the prebuilt seeds, is discoverable
in the ``creative`` category, declares the tool authorizations its SKILL.md workflow needs, and
its ``.arch.json`` output maps to the architecture artifact type.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
from myrm_agent_harness.core.artifacts.constants import (
    ArtifactType,
    infer_artifact_type_from_extension,
)
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.skills import prebuilt_sync
from app.core.skills.store.reader import list_prebuilt_skills


@pytest.fixture
def temp_workspace_dir() -> Path:
    temp_dir = tempfile.mkdtemp(prefix="arch_skill_e2e_")
    yield Path(temp_dir)
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_architecture_diagram_skill_contract_and_metadata(temp_workspace_dir: Path) -> None:
    """Verify architecture-diagram skill metadata, sync discoverability, and YAML frontmatter contract."""
    storage = LocalStorageBackend(str(temp_workspace_dir))
    sync_result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert "architecture-diagram" in sync_result.skill_ids, "architecture-diagram must be synced"

    skills = await list_prebuilt_skills(storage)
    arch_skill = next((s for s in skills if s.id == "architecture-diagram"), None)
    assert arch_skill is not None, "architecture-diagram skill must be discovered"
    assert arch_skill.category == "creative"

    skill_file = Path(__file__).resolve().parents[3] / "assets" / "prebuilt_skills" / "architecture-diagram" / "SKILL.md"
    assert skill_file.exists(), f"SKILL.md must exist at {skill_file}"
    raw_md = skill_file.read_text(encoding="utf-8")

    # Verify tool authorizations
    tool_match = re.search(r"^allowed-tools:\s*(.+)$", raw_md, re.MULTILINE)
    assert tool_match is not None, "allowed-tools must be declared in frontmatter"
    allowed_tools = tool_match.group(1).split()
    assert "file_write_tool" in allowed_tools
    assert "file_read_tool" in allowed_tools

    # Verify artifact extension mapping
    assert infer_artifact_type_from_extension("system.arch.json") == ArtifactType.ARCHITECTURE
    assert infer_artifact_type_from_extension("workflow.arch.json") == ArtifactType.ARCHITECTURE
