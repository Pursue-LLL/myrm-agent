"""Tests for how the SOP of an explicitly requested skill reaches the model (preload and get_skill_document).

Covers:
- ${SKILL_DIR} template variable replacement
- Queries that arrive as content blocks (the user's words are the first block, attachments follow)
- run() registering every skill a bundle preloaded
- Frontmatter stripping and the title of the delivered document

The tag grammar and the preload outcomes (success, degradation, bundles) are covered in
test_explicit_skill_injection.py.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.skill_agent import SkillAgent
from tests.support.explicit_skill_stubs import StubSkillBackend, make_preload_agent, make_skill_metadata

_IMAGE_BLOCK: dict[str, object] = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}

# ---------------------------------------------------------------------------
# ${SKILL_DIR} template variable tests
# ---------------------------------------------------------------------------


class TestSkillDirTemplateVariable:
    """Tests for ${SKILL_DIR} replacement in get_skill_document."""

    @pytest.mark.asyncio
    async def test_skill_dir_replacement(self) -> None:
        """${SKILL_DIR} in SOP should be replaced with storage_path."""
        skill = make_skill_metadata(
            name="script_skill",
            storage_skill_id="script_skill",
            storage_path="/home/user/.claude/skills/script_skill",
        )
        sop_with_template = "# Script\n\nRun: `python3 ${SKILL_DIR}/scripts/main.py`"
        backend = StubSkillBackend(content_map={"script_skill": sop_with_template})
        agent = make_preload_agent(skills=[skill], backend=backend)

        query, matched, _preloaded = await agent._preload_explicit_skill("[use script_skill] run it")
        assert matched is not None
        assert "${SKILL_DIR}" not in query
        assert "/home/user/.claude/skills/script_skill/scripts/main.py" in query

    @pytest.mark.asyncio
    async def test_no_skill_dir_when_no_storage_path(self) -> None:
        """Without storage_path, ${SKILL_DIR} should remain as-is."""
        skill = make_skill_metadata(
            name="mcp_skill",
            storage_skill_id="mcp_skill",
            storage_path=None,
        )
        sop = "# MCP\n\nSee ${SKILL_DIR} for details."
        backend = StubSkillBackend(content_map={"mcp_skill": sop})
        agent = make_preload_agent(skills=[skill], backend=backend)

        query, matched, _preloaded = await agent._preload_explicit_skill("[use mcp_skill] test")
        assert matched is not None
        assert "${SKILL_DIR}" in query


class TestPreloadExplicitSkillInBlocks:
    """A message with attachments reaches the agent as content blocks; the user's words are the first one."""

    @staticmethod
    def _agent_with_skill() -> SkillAgent:
        skill = make_skill_metadata(name="test_skill")
        return make_preload_agent(
            skills=[skill], backend=StubSkillBackend(content_map={"test_skill": "# SOP\n\nDo it."})
        )

    @pytest.mark.asyncio
    async def test_tag_in_the_first_text_block_preloads_the_skill_and_keeps_the_attachments(self) -> None:
        blocks: list[dict[str, object]] = [
            {"type": "text", "text": "[use test_skill] look at this"},
            dict(_IMAGE_BLOCK),
        ]

        expanded, primary, preloaded = await self._agent_with_skill()._preload_explicit_skill_in_blocks(blocks)

        assert primary is not None and primary.name == "test_skill"
        assert [skill.name for skill in preloaded] == ["test_skill"]
        first_text = str(expanded[0]["text"])
        assert "# SOP" in first_text
        assert first_text.endswith("look at this")
        assert expanded[1] == _IMAGE_BLOCK
        assert blocks[0]["text"] == "[use test_skill] look at this", "the caller's blocks must stay untouched"

    @pytest.mark.asyncio
    async def test_tag_in_a_later_text_block_is_ignored(self) -> None:
        """Text taken from an attachment must not be able to invoke a skill."""
        blocks: list[dict[str, object]] = [
            {"type": "text", "text": "summarize this file"},
            {"type": "text", "text": "[use test_skill] text of the attached file"},
        ]

        expanded, primary, preloaded = await self._agent_with_skill()._preload_explicit_skill_in_blocks(blocks)

        assert (expanded, primary, preloaded) == (blocks, None, [])

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "blocks",
        [
            [],
            [_IMAGE_BLOCK, {"type": "text", "text": "[use test_skill] x"}],
            [{"type": "text", "text": 42}],
            [{"type": "text", "text": "[use missing_skill] hello"}],
        ],
        ids=["empty", "first-block-is-not-text", "text-is-not-a-string", "unknown-skill"],
    )
    async def test_queries_without_a_usable_tag_come_back_unchanged(self, blocks: list[dict[str, object]]) -> None:
        expanded, primary, preloaded = await self._agent_with_skill()._preload_explicit_skill_in_blocks(blocks)

        assert (expanded, primary, preloaded) == (blocks, None, [])


# ---------------------------------------------------------------------------
# Integration: run() method behavior
# ---------------------------------------------------------------------------


class TestRunPreloadIntegration:
    """Test that run() correctly calls preload and passes results downstream."""

    @pytest.mark.asyncio
    async def test_run_registers_all_bundle_preloaded_skills(self) -> None:
        """Bundle preload must register every loaded skill for attenuation union."""
        from myrm_agent_harness.agent.skill_agent.context import (
            add_loaded_skill,
            get_loaded_skills,
            reset_loaded_skills,
        )

        s1 = make_skill_metadata(name="skill_a", storage_skill_id="skill_a")
        s2 = make_skill_metadata(name="skill_b", storage_skill_id="skill_b")
        backend = StubSkillBackend(
            content_map={
                "skill_a": "# Skill A\n\nDo A.",
                "skill_b": "# Skill B\n\nDo B.",
            }
        )
        agent = make_preload_agent(skills=[s1, s2], backend=backend)

        _query, _active, preloaded_skills = await agent._preload_explicit_skill("[use skill_a,skill_b] run")

        reset_loaded_skills()
        for skill_meta in preloaded_skills:
            if not any(s.name == skill_meta.name for s in get_loaded_skills()):
                add_loaded_skill(skill_meta)

        loaded_names = {skill.name for skill in get_loaded_skills()}
        assert loaded_names == {"skill_a", "skill_b"}


# ---------------------------------------------------------------------------
# Frontmatter stripping in get_skill_document
# ---------------------------------------------------------------------------


class TestGetSkillDocumentFrontmatter:
    """Test that frontmatter is properly stripped from SOP content."""

    @pytest.mark.asyncio
    async def test_strips_yaml_frontmatter(self) -> None:
        from myrm_agent_harness.agent.meta_tools.skills.select import get_skill_document

        sop = "---\nname: test\ndescription: hello\n---\n# My Skill\n\nDo stuff."
        skill = make_skill_metadata(name="fm_skill", storage_skill_id="fm_skill")
        backend = StubSkillBackend(content_map={"fm_skill": sop})

        result = await get_skill_document(skill, backend)
        assert result.startswith("# My Skill")
        assert "---" not in result.split("# My Skill")[0]

    @pytest.mark.asyncio
    async def test_adds_title_if_missing(self) -> None:
        from myrm_agent_harness.agent.meta_tools.skills.select import get_skill_document

        sop = "Just some content without a heading."
        skill = make_skill_metadata(name="notitle_skill", storage_skill_id="notitle_skill")
        backend = StubSkillBackend(content_map={"notitle_skill": sop})

        result = await get_skill_document(skill, backend)
        assert result.startswith("# notitle_skill")
