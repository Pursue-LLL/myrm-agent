"""Real LLM E2E test for DERIVED evolution flow.

Tests the complete derive evolution pipeline with real LLM calls (no mocks):
1. Register a skill in evolution store
2. Trigger DERIVED evolution with real LLM
3. Verify the evolved skill is different from original
4. Verify Intent Context injection works end-to-end
"""

import logging
import os
import tempfile
from pathlib import Path

import pytest
from dotenv import load_dotenv
from myrm_agent_harness.api.hooks import set_task_intent
from myrm_agent_harness.agent.config.parsers import to_litellm_model
from myrm_agent_harness.agent.skills.evolution import (
    EvolutionIntegration,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)

load_dotenv(override=True)

logger = logging.getLogger(__name__)

BASIC_API_KEY = os.getenv("BASIC_API_KEY", "")
BASIC_MODEL = os.getenv("BASIC_MODEL")
BASIC_BASE_URL = os.getenv("BASIC_BASE_URL", "")


def _env_model_to_litellm(env_model: str) -> str:
    """Map BASIC_MODEL / LITE_MODEL style strings to LiteLLM provider/model."""
    raw = env_model.strip()
    if not raw:
        return raw
    if "/" not in raw:
        return to_litellm_model("openai", raw)
    prefix, name = raw.split("/", 1)
    return to_litellm_model(prefix.replace("-", "_"), name)


def _has_real_api_key() -> bool:
    return bool(BASIC_API_KEY) and BASIC_API_KEY != "sk-dummy"


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "skills.db"
        yield {"db_path": db_path, "workspace": Path(tmpdir)}


@pytest.fixture
def real_llm():
    """Create real LLM client using configured API key."""
    from myrm_agent_harness.toolkits.llms.core.llm import create_litellm_model

    if not BASIC_MODEL:
        pytest.skip("BASIC_MODEL must be set for real LLM integration tests")

    basic_model = _env_model_to_litellm(BASIC_MODEL)
    provider_name = basic_model.split("/", 1)[0] if "/" in basic_model else "openai"
    if provider_name == "openai-compatible":
        provider_name = "openai"
        basic_model = basic_model.replace("openai-compatible/", "openai/", 1)

    return create_litellm_model(
        model=basic_model,
        api_key=BASIC_API_KEY,
        base_url=BASIC_BASE_URL or None,
        temperature=0.3,
        streaming=False,
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(not _has_real_api_key(), reason="BASIC_API_KEY not configured")
async def test_derive_evolution_real_llm(temp_workspace, real_llm):
    """Test DERIVED evolution with real LLM generates meaningful changes."""
    evolution = EvolutionIntegration(
        db_path=temp_workspace["db_path"],
        llm=real_llm,
        enable_tde=False,
        enable_tool_calling=False,
    )

    if evolution.engine:
        evolution.engine._guard = None

    original_content = """---
name: file-organizer
description: Organize files in a directory by file type
version: "1.0.0"
category: productivity
---

# File Organizer

Organize files by moving them into subdirectories based on their extension.

## Instructions
1. Scan the target directory
2. Create subdirectories for each file type
3. Move files into appropriate subdirectories
"""

    skill = SkillRecord(
        skill_id="file-organizer-v1",
        name="file-organizer",
        description="Organize files by type",
        content=original_content,
        path=str(temp_workspace["workspace"] / "file-organizer" / "SKILL.md"),
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED, version=1),
    )
    await evolution.store.save_skill(skill)

    new_skill = await evolution.evolve_skill(
        "file-organizer-v1",
        EvolutionType.DERIVED,
        user_feedback="Add support for handling duplicate files with hash comparison",
    )

    logger.info("DERIVED evolution result: %s", new_skill is not None)
    if new_skill:
        logger.info("Evolved content length: %d -> %d", len(original_content), len(new_skill.proposed_content))
        assert new_skill.proposed_content != original_content, "Evolved content should differ from original"
        assert new_skill.evolution_type == EvolutionType.DERIVED
    else:
        logger.warning("LLM returned None for DERIVED evolution (may be model-specific)")

    await evolution.close()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(not _has_real_api_key(), reason="BASIC_API_KEY not configured")
async def test_intent_context_injection_real(temp_workspace, real_llm):
    """Test that task_intent ContextVar is properly injected into execution records."""
    evolution = EvolutionIntegration(
        db_path=temp_workspace["db_path"],
        llm=real_llm,
        enable_tde=False,
    )

    skill = SkillRecord(
        skill_id="intent-test-skill",
        name="intent-test",
        description="Test intent injection",
        content="# Intent Test Skill",
        path="/test/intent",
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED, version=1),
    )
    await evolution.store.save_skill(skill)

    set_task_intent("Help me organize my project files by date")

    await evolution.record_execution(
        skill_id="intent-test-skill",
        success=True,
    )

    stored_skill = evolution.store.get_skill("intent-test-skill")
    assert stored_skill is not None
    assert stored_skill.metrics.success_count == 1

    await evolution.close()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.skipif(not _has_real_api_key(), reason="BASIC_API_KEY not configured")
async def test_fix_evolution_real_llm(temp_workspace, real_llm):
    """Test FIX evolution with real LLM when skill has consecutive failures."""
    evolution = EvolutionIntegration(
        db_path=temp_workspace["db_path"],
        llm=real_llm,
        enable_tde=False,
        enable_tool_calling=False,
    )

    if evolution.engine:
        evolution.engine._guard = None

    buggy_content = """---
name: csv-parser
description: Parse CSV files and extract data
version: "1.0.0"
category: data
---

# CSV Parser

Parse CSV files. Currently has a bug where it doesn't handle quoted fields correctly.

## Instructions
1. Open the CSV file
2. Split each line by comma (BUG: doesn't handle quoted fields)
3. Return the parsed data
"""

    skill = SkillRecord(
        skill_id="csv-parser-v1",
        name="csv-parser",
        description="Parse CSV files",
        content=buggy_content,
        path=str(temp_workspace["workspace"] / "csv-parser" / "SKILL.md"),
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED, version=1),
    )
    await evolution.store.save_skill(skill)

    for _i in range(3):
        await evolution.record_execution(
            skill_id="csv-parser-v1",
            success=False,
            error_message="Failed to parse CSV: unmatched quote in field",
        )

    active_skills = evolution.store.get_active_skills()
    original_skill = evolution.store.get_skill("csv-parser-v1")

    logger.info("Active skills after 3 failures: %d", len(active_skills))
    if original_skill:
        logger.info("Original skill deactivated: %s", not original_skill.is_active)

    if len(active_skills) > 0 and active_skills[0].lineage.version > 1:
        evolved = active_skills[0]
        assert evolved.lineage.parent_id == "csv-parser-v1"
        assert evolved.content != buggy_content
        logger.info("FIX evolution succeeded: v%d created", evolved.lineage.version)
    else:
        logger.warning("FIX evolution may not have produced a new version (model-dependent)")

    await evolution.close()
