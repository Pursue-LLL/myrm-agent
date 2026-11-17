"""Tests for the preload a ``[use skill]`` tag triggers (``SkillAgent._preload_explicit_skill``).

Covers:
- SOP injection with the strong signal, the user's arguments and the auxiliary file listing
- A SOP that quotes an error line is still injected
- Usage stats written by the preload
- Graceful degradation (no backend, unknown skill, unreadable or empty SOP, a failing loader)
- Unavailable skills (the signal carries a WARNING)
- Bundles (``[use a,b]``): merged SOPs, a missing skill, a skill without a readable SOP, the token budget
- The header names only the skills whose SOP was delivered (bundle and single form)

How the SOP reaches the model (template variable, content blocks) is covered in
test_explicit_skill_injection_delivery.py, the NOTE that names the skills a message could not carry in
test_explicit_skill_preload_notice.py, the tag grammar in test_skill_reference.py and what run() does with a
bundle in test_skill_run_usage.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.explicit_skill_stubs import StubSkillBackend, make_preload_agent, make_skill_metadata


class TestPreloadExplicitSkill:
    """Tests for SkillAgent._preload_explicit_skill."""

    @pytest.mark.asyncio
    async def test_successful_preload(self) -> None:
        """Normal path: skill found, SOP loaded, query rewritten."""
        skill = make_skill_metadata(name="daily_report_skill", storage_skill_id="daily_report_skill")
        backend = StubSkillBackend(content_map={"daily_report_skill": "# Daily Report\n\nGenerate reports."})
        agent = make_preload_agent(skills=[skill], backend=backend)

        query, matched, _preloaded = await agent._preload_explicit_skill(
            "[use daily_report_skill] generate today's report"
        )

        assert matched is not None
        assert matched.name == "daily_report_skill"
        assert "[IMPORTANT:" in query
        assert "daily_report_skill" in query
        assert "Do NOT call skill_select_tool" in query
        assert "# Daily Report" in query
        assert "generate today's report" in query

    @pytest.mark.asyncio
    async def test_preload_records_usage_stats(self, tmp_path: Path) -> None:
        """[use skill] preload must write .stats.json for Curator."""
        skill_dir = tmp_path / "preload_skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# preload\n")

        skill = make_skill_metadata(
            name="preload_skill",
            storage_skill_id="preload_skill",
            storage_path=str(skill_dir),
        )
        backend = StubSkillBackend(content_map={"preload_skill": "# Preload\n\nSOP."})

        from myrm_agent_harness.backends.skills.stats_collector import (
            SkillStatsCollector,
        )
        from myrm_agent_harness.backends.skills.usage_recorder import (
            begin_skill_run_usage,
            commit_skill_run_usage,
            set_stats_collector,
        )

        collector = SkillStatsCollector()
        set_stats_collector(collector)
        agent = make_preload_agent(skills=[skill], backend=backend)

        begin_skill_run_usage()
        await agent._preload_explicit_skill("[use preload_skill] run task")
        commit_skill_run_usage()

        stats = collector.get_stats(skill_dir)
        assert stats.call_count == 1
        assert stats.observed_count == 0
        set_stats_collector(None)

    @pytest.mark.asyncio
    async def test_user_args_preserved(self) -> None:
        """User arguments after [use] must appear at the end of the injected query."""
        skill = make_skill_metadata(name="test_skill")
        backend = StubSkillBackend(content_map={"test_skill": "# Test\n\nSOP content."})
        agent = make_preload_agent(skills=[skill], backend=backend)

        query, _, _preloaded = await agent._preload_explicit_skill("[use test_skill] my custom args here")
        assert query.endswith("my custom args here")

    @pytest.mark.asyncio
    async def test_no_args(self) -> None:
        """[use skill_name] without args should still inject SOP."""
        skill = make_skill_metadata(name="test_skill")
        backend = StubSkillBackend(content_map={"test_skill": "# Test\n\nSOP."})
        agent = make_preload_agent(skills=[skill], backend=backend)

        query, matched, _preloaded = await agent._preload_explicit_skill("[use test_skill]")
        assert matched is not None
        assert "# Test" in query
        assert not query.rstrip().endswith("\n\n")

    @pytest.mark.asyncio
    async def test_fallback_no_backend(self) -> None:
        """Without a skill_backend, query should pass through unchanged."""
        agent = make_preload_agent(skills=None, backend=None)
        agent.skill_backend = None

        query, matched, _preloaded = await agent._preload_explicit_skill("[use test_skill] args")
        assert matched is None
        assert query == "[use test_skill] args"

    @pytest.mark.asyncio
    async def test_fallback_skill_not_found(self) -> None:
        """If skill name doesn't exist, query passes through for Rule 6 fallback."""
        backend = StubSkillBackend()
        agent = make_preload_agent(skills=[], backend=backend)

        query, matched, _preloaded = await agent._preload_explicit_skill("[use nonexistent_skill] do something")
        assert matched is None
        assert query == "[use nonexistent_skill] do something"

    @pytest.mark.asyncio
    async def test_fallback_sop_load_error(self) -> None:
        """If SOP loading throws, query passes through unchanged."""
        skill = make_skill_metadata(name="broken_skill", storage_skill_id="broken_skill")
        backend = StubSkillBackend()
        agent = make_preload_agent(skills=[skill], backend=backend)

        query, matched, _preloaded = await agent._preload_explicit_skill("[use broken_skill] args")
        assert matched is None
        assert query == "[use broken_skill] args"

    @pytest.mark.asyncio
    async def test_fallback_empty_sop(self) -> None:
        """If SOP is empty, query passes through unchanged."""
        skill = make_skill_metadata(name="empty_skill", storage_skill_id="empty_skill")
        backend = StubSkillBackend(content_map={"empty_skill": ""})
        agent = make_preload_agent(skills=[skill], backend=backend)

        query, matched, _preloaded = await agent._preload_explicit_skill("[use empty_skill] args")
        assert matched is None
        assert query == "[use empty_skill] args"

    @pytest.mark.asyncio
    async def test_non_use_query_unchanged(self) -> None:
        """Regular messages should not trigger preloading."""
        backend = StubSkillBackend()
        agent = make_preload_agent(skills=[], backend=backend)

        query, matched, _preloaded = await agent._preload_explicit_skill("Just a normal question")
        assert matched is None
        assert query == "Just a normal question"

    @pytest.mark.asyncio
    async def test_strong_signal_format(self) -> None:
        """Verify the strong signal header matches the expected format."""
        skill = make_skill_metadata(name="test_skill")
        backend = StubSkillBackend(content_map={"test_skill": "# Test\n\nContent."})
        agent = make_preload_agent(skills=[skill], backend=backend)

        query, _, _preloaded = await agent._preload_explicit_skill("[use test_skill] args")
        first_line = query.split("\n")[0]
        assert first_line.startswith("[IMPORTANT:")
        assert "test_skill" in first_line
        assert "preloaded" in first_line.lower()

    @pytest.mark.asyncio
    async def test_unavailable_skill_includes_warning(self) -> None:
        """Unavailable skills should still load but include a WARNING in the signal."""
        skill = make_skill_metadata(name="ffmpeg_skill", storage_skill_id="ffmpeg_skill")
        skill.available = False
        skill.unavailable_reason = "ffmpeg not found on PATH"
        backend = StubSkillBackend(content_map={"ffmpeg_skill": "# FFmpeg\n\nConvert videos."})
        agent = make_preload_agent(skills=[skill], backend=backend)

        query, matched, _preloaded = await agent._preload_explicit_skill("[use ffmpeg_skill] convert file.mp4")
        assert matched is not None
        assert "WARNING" in query
        assert "UNAVAILABLE" in query
        assert "ffmpeg not found on PATH" in query
        assert "# FFmpeg" in query

    @pytest.mark.asyncio
    async def test_available_skill_no_warning(self) -> None:
        """Available skills should NOT include an UNAVAILABLE warning."""
        skill = make_skill_metadata(name="test_skill")
        backend = StubSkillBackend(content_map={"test_skill": "# Test\n\nContent."})
        agent = make_preload_agent(skills=[skill], backend=backend)

        query, _, _preloaded = await agent._preload_explicit_skill("[use test_skill] args")
        assert "UNAVAILABLE" not in query
        assert "WARNING" not in query

    @pytest.mark.asyncio
    async def test_unavailable_skill_default_reason(self) -> None:
        """Unavailable skill with no explicit reason uses default message."""
        skill = make_skill_metadata(name="gpu_skill", storage_skill_id="gpu_skill")
        skill.available = False
        skill.unavailable_reason = None
        backend = StubSkillBackend(content_map={"gpu_skill": "# GPU\n\nAccelerate."})
        agent = make_preload_agent(skills=[skill], backend=backend)

        query, matched, _preloaded = await agent._preload_explicit_skill("[use gpu_skill] run")
        assert matched is not None
        assert "dependency requirements not met" in query

    @pytest.mark.asyncio
    async def test_get_skill_document_exception_fallback(self) -> None:
        """If get_skill_document raises an unexpected exception, fallback gracefully."""
        from unittest.mock import patch

        skill = make_skill_metadata(name="crash_skill", storage_skill_id="crash_skill")
        backend = StubSkillBackend(content_map={"crash_skill": "# Crash\n\nContent."})
        agent = make_preload_agent(skills=[skill], backend=backend)

        with patch(
            "myrm_agent_harness.agent.meta_tools.skills.select.get_skill_document",
            side_effect=RuntimeError("unexpected failure"),
        ):
            query, matched, _preloaded = await agent._preload_explicit_skill("[use crash_skill] test")

        assert matched is None
        assert query == "[use crash_skill] test"

    @pytest.mark.asyncio
    async def test_preload_with_file_listing(self, tmp_path: Path) -> None:
        """Successful preload with auxiliary files includes file listing."""

        skill_dir = tmp_path / "deploy_skill"
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "deploy.sh").write_text("#!/bin/bash\necho deploy")

        skill = make_skill_metadata(
            name="deploy_skill",
            storage_skill_id="deploy_skill",
            storage_path=str(skill_dir),
        )
        backend = StubSkillBackend(
            content_map={"deploy_skill": "# Deploy\n\nRun deploy."},
            resource_map={"deploy_skill": ["scripts/deploy.sh"]},
        )
        agent = make_preload_agent(skills=[skill], backend=backend)

        query, matched, _preloaded = await agent._preload_explicit_skill("[use deploy_skill] prod")
        assert matched is not None
        assert "[Linked files]" in query
        assert "scripts/deploy.sh" in query
        assert "prod" in query

    @pytest.mark.asyncio
    async def test_sop_with_an_error_line_is_still_injected(self) -> None:
        """A real SOP may quote an error message; only a SOP that cannot be delivered falls back."""
        skill = make_skill_metadata(name="debug_skill", storage_skill_id="debug_skill")
        sop = "# Debug\n\nWhen the build fails you see:\nError: module not found\nThen check the lockfile."
        agent = make_preload_agent(skills=[skill], backend=StubSkillBackend(content_map={"debug_skill": sop}))

        query, matched, _preloaded = await agent._preload_explicit_skill("[use debug_skill] test")
        assert matched is not None
        assert "Error: module not found" in query

    # -- Multi-skill bundle tests --

    @pytest.mark.asyncio
    async def test_bundle_two_skills(self) -> None:
        """Comma-separated skills should merge SOPs with bundle header."""
        s1 = make_skill_metadata(name="skill_a", storage_skill_id="skill_a")
        s2 = make_skill_metadata(name="skill_b", storage_skill_id="skill_b")
        backend = StubSkillBackend(
            content_map={
                "skill_a": "# Skill A\n\nDo A.",
                "skill_b": "# Skill B\n\nDo B.",
            }
        )
        agent = make_preload_agent(skills=[s1, s2], backend=backend)

        query, matched, preloaded = await agent._preload_explicit_skill("[use skill_a,skill_b] run both")
        assert matched is not None
        assert matched.name == "skill_a"
        assert len(preloaded) == 2
        assert {skill.name for skill in preloaded} == {"skill_a", "skill_b"}
        assert "skills have been preloaded as a bundle" in query
        assert "--- Skill: skill_a ---" in query
        assert "--- Skill: skill_b ---" in query
        assert "# Skill A" in query
        assert "# Skill B" in query
        assert query.rstrip().endswith("run both")

    @pytest.mark.asyncio
    async def test_bundle_partial_skill_not_found(self) -> None:
        """If one skill in bundle is missing, load only the found ones."""
        s1 = make_skill_metadata(name="found_skill", storage_skill_id="found_skill")
        backend = StubSkillBackend(content_map={"found_skill": "# Found\n\nContent."})
        agent = make_preload_agent(skills=[s1], backend=backend)

        query, matched, _preloaded = await agent._preload_explicit_skill("[use found_skill,missing_skill] args")
        assert matched is not None
        assert matched.name == "found_skill"
        assert "# Found" in query
        assert "--- Skill: missing_skill ---" not in query
        assert "preloaded" in query.lower()

    @pytest.mark.asyncio
    async def test_bundle_skill_without_a_readable_sop_is_left_out(self) -> None:
        """A skill the backend lists but cannot serve is neither injected nor returned as preloaded."""
        readable = make_skill_metadata(name="readable_skill", storage_skill_id="readable_skill")
        unreadable = make_skill_metadata(name="unreadable_skill", storage_skill_id="unreadable_skill")
        backend = StubSkillBackend(content_map={"readable_skill": "# Readable\n\nContent."})
        agent = make_preload_agent(skills=[readable, unreadable], backend=backend)

        query, matched, preloaded = await agent._preload_explicit_skill("[use readable_skill,unreadable_skill] go")

        assert matched is not None
        assert matched.name == "readable_skill"
        assert [skill.name for skill in preloaded] == ["readable_skill"]
        assert "# Readable" in query
        assert "--- Skill: unreadable_skill ---" not in query

    @pytest.mark.asyncio
    async def test_bundle_all_skills_missing(self) -> None:
        """If all skills in bundle are missing, query passes through unchanged."""
        backend = StubSkillBackend()
        agent = make_preload_agent(skills=[], backend=backend)

        query, matched, _preloaded = await agent._preload_explicit_skill("[use x,y,z] args")
        assert matched is None
        assert query == "[use x,y,z] args"

    @pytest.mark.asyncio
    async def test_bundle_token_budget_enforcement(self) -> None:
        """When combined SOPs exceed _TOKEN_BUDGET_MAX, later skills are neither injected nor returned as preloaded."""
        big_sop = "# Big Skill\n\n" + ("x" * 12000)
        small_sop = "# Small Skill\n\nTiny."
        s1 = make_skill_metadata(name="big", storage_skill_id="big")
        s2 = make_skill_metadata(name="small", storage_skill_id="small")
        backend = StubSkillBackend(content_map={"big": big_sop, "small": small_sop})
        agent = make_preload_agent(skills=[s1, s2], backend=backend)

        query, matched, preloaded = await agent._preload_explicit_skill("[use big,small] test")
        assert matched is not None
        assert "# Big Skill" in query
        assert "# Small Skill" not in query
        assert [skill.name for skill in preloaded] == ["big"]

    @pytest.mark.asyncio
    async def test_single_skill_uses_single_header(self) -> None:
        """Single skill should use 'has been preloaded', not 'bundle' header."""
        skill = make_skill_metadata(name="solo", storage_skill_id="solo")
        backend = StubSkillBackend(content_map={"solo": "# Solo\n\nContent."})
        agent = make_preload_agent(skills=[skill], backend=backend)

        query, _, _preloaded = await agent._preload_explicit_skill("[use solo] go")
        assert "bundle" not in query.lower()
        assert '"solo" has been preloaded' in query

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("refs", "header"),
        [
            ("beta,alpha,gamma", "The following 2 skills have been preloaded as a bundle: alpha, gamma."),
            ("beta,alpha", 'The skill "alpha" has been preloaded by the user.'),
        ],
        ids=["bundle-header", "single-header"],
    )
    async def test_the_header_names_only_the_skills_whose_sop_was_delivered(self, refs: str, header: str) -> None:
        """The header tells the model which SOPs it already has, so a skill that delivered none is not named."""
        skills = [make_skill_metadata(name=name, storage_skill_id=name) for name in ("alpha", "beta", "gamma")]
        backend = StubSkillBackend(content_map={"alpha": "# Alpha\n\nDo A.", "gamma": "# Gamma\n\nDo G."})
        agent = make_preload_agent(skills=skills, backend=backend)

        query, _primary, _preloaded = await agent._preload_explicit_skill(f"[use {refs}] go")

        first_line = query.split("\n")[0]
        assert header in first_line
        assert "beta" not in first_line

    @pytest.mark.asyncio
    async def test_bundle_with_instruction_in_user_args(self) -> None:
        """[instruction: ...] in user_args should be forwarded as-is."""
        s1 = make_skill_metadata(name="a", storage_skill_id="a")
        s2 = make_skill_metadata(name="b", storage_skill_id="b")
        backend = StubSkillBackend(content_map={"a": "# A\n\nDo A.", "b": "# B\n\nDo B."})
        agent = make_preload_agent(skills=[s1, s2], backend=backend)

        query, matched, _preloaded = await agent._preload_explicit_skill("[use a,b] [instruction: be concise] do it")
        assert matched is not None
        assert "[instruction: be concise] do it" in query
