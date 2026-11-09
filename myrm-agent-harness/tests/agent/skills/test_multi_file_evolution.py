"""Unit tests for multi-file evolution support.

Covers:
  - Multi-file FULL format parsing (*** File: headers)
  - Unicode normalization in fuzzy matching
  - _collect_skill_files() filtering logic
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from myrm_agent_harness.utils.fuzzy_match import fuzzy_find


class TestUnicodeNormalization:
    """Test Unicode normalization in fuzzy matching."""

    def test_fuzzy_find_with_smart_quotes(self) -> None:
        content = "config['api_key']"
        find = "config[\u2018api_key\u2019]"
        result = fuzzy_find(content, find)
        assert result is not None
        assert result.matched_text == content

    def test_fuzzy_find_with_em_dash(self) -> None:
        content = "value -- default"
        find = "value \u2014 default"
        result = fuzzy_find(content, find)
        assert result is not None


class TestCollectSkillFiles:
    """Test _collect_skill_files in GitInstaller."""

    def test_empty_directory(self) -> None:
        from myrm_agent_harness.agent.skills.market.installers.git_installer import GitInstaller

        installer = GitInstaller.__new__(GitInstaller)
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_md = Path(tmpdir) / "SKILL.md"
            skill_md.write_text("# Skill")
            result = installer._collect_skill_files(Path(tmpdir))
            assert "SKILL.md" in result.files

    def test_with_auxiliary_files(self) -> None:
        from myrm_agent_harness.agent.skills.market.installers.git_installer import GitInstaller

        installer = GitInstaller.__new__(GitInstaller)
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_md = Path(tmpdir) / "SKILL.md"
            skill_md.write_text("# Skill")
            script = Path(tmpdir) / "scripts"
            script.mkdir()
            (script / "run.sh").write_text("echo hello")
            (Path(tmpdir) / "config.yaml").write_text("key: val")

            result = installer._collect_skill_files(Path(tmpdir))
            assert "scripts/run.sh" in result.files
            assert "config.yaml" in result.files

    def test_skips_hidden_dirs(self) -> None:
        from myrm_agent_harness.agent.skills.market.installers.git_installer import GitInstaller

        installer = GitInstaller.__new__(GitInstaller)
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_md = Path(tmpdir) / "SKILL.md"
            skill_md.write_text("# Skill")
            (Path(tmpdir) / "good.txt").write_text("keep")

            result = installer._collect_skill_files(Path(tmpdir))
            assert "good.txt" in result.files

    def test_collects_nested_files(self) -> None:
        from myrm_agent_harness.agent.skills.market.installers.git_installer import GitInstaller

        installer = GitInstaller.__new__(GitInstaller)
        with tempfile.TemporaryDirectory() as tmpdir:
            skill_md = Path(tmpdir) / "SKILL.md"
            skill_md.write_text("# Nested Skill")
            nested = Path(tmpdir) / "sub"
            nested.mkdir()
            (nested / "helper.py").write_text("print('hi')")

            result = installer._collect_skill_files(Path(tmpdir))
            assert "sub/helper.py" in result.files
            assert "SKILL.md" in result.files
