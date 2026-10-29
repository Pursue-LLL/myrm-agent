"""Tests for which rule files a workspace directory contributes, and in which priority order."""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.agent.workspace_rules import scanner
from myrm_agent_harness.agent.workspace_rules.rule_read_guard import RuleReadGuard
from myrm_agent_harness.agent.workspace_rules.scanner import RuleFile


def _scan_directory(directory: Path) -> list[RuleFile]:
    return scanner._scan_directory(directory, RuleReadGuard(directory))


@pytest.fixture()
def workspace_dir(tmp_path: Path) -> Path:
    """Create a temporary workspace with .git marker."""
    (tmp_path / ".git").mkdir()
    return tmp_path


class TestScanDirectory:
    def test_discovers_agents_md(self, workspace_dir: Path) -> None:
        (workspace_dir / "AGENTS.md").write_text("# Project Rules")
        results = _scan_directory(workspace_dir)
        assert len(results) >= 1
        assert any(r.source == "AGENTS.md" for r in results)

    def test_discovers_claude_md(self, workspace_dir: Path) -> None:
        (workspace_dir / "CLAUDE.md").write_text("# Claude Rules")
        results = _scan_directory(workspace_dir)
        assert any(r.source == "CLAUDE.md" for r in results)

    def test_discovers_cursorrules(self, workspace_dir: Path) -> None:
        (workspace_dir / ".cursorrules").write_text("Cursor config here")
        results = _scan_directory(workspace_dir)
        assert any(r.source == ".cursorrules" for r in results)

    def test_discovers_myrm_rules_dir(self, workspace_dir: Path) -> None:
        rules_dir = workspace_dir / ".myrm" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "coding.md").write_text("# Coding Standards")
        results = _scan_directory(workspace_dir)
        assert any(r.source == ".myrm/rules" for r in results)

    def test_discovers_cursor_rules_mdc(self, workspace_dir: Path) -> None:
        rules_dir = workspace_dir / ".cursor" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "style.mdc").write_text("Style rules content")
        results = _scan_directory(workspace_dir)
        assert any(r.source == ".cursor/rules" for r in results)

    def test_discovers_hermes_md(self, workspace_dir: Path) -> None:
        (workspace_dir / ".hermes.md").write_text("# Hermes project rules")
        results = _scan_directory(workspace_dir)
        assert any(r.source == ".hermes.md" for r in results)

    def test_discovers_hermes_md_uppercase(self, workspace_dir: Path) -> None:
        (workspace_dir / "HERMES.md").write_text("# HERMES project config")
        results = _scan_directory(workspace_dir)
        assert any(r.source == "HERMES.md" for r in results)

    def test_first_match_wins_priority(self, workspace_dir: Path) -> None:
        (workspace_dir / "AGENTS.md").write_text("# Agents")
        (workspace_dir / "CLAUDE.md").write_text("# Claude")
        cursor_dir = workspace_dir / ".cursor" / "rules"
        cursor_dir.mkdir(parents=True)
        (cursor_dir / "rule.mdc").write_text("Cursor rule")
        results = _scan_directory(workspace_dir)
        # Should contain AGENTS.md (global) AND rule.mdc (specific), but NOT CLAUDE.md
        assert len(results) == 2
        sources = [r.source for r in results]
        assert "AGENTS.md" in sources
        assert ".cursor/rules" in sources
        assert "CLAUDE.md" not in sources

    def test_discovers_claude_subdir(self, workspace_dir: Path) -> None:
        claude_dir = workspace_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "CLAUDE.md").write_text("# Claude Code project rules")
        results = _scan_directory(workspace_dir)
        assert any(r.source == ".claude/CLAUDE.md" for r in results)
        assert any("Claude Code project rules" in r.content for r in results)

    def test_claude_subdir_deduped_against_root(self, workspace_dir: Path) -> None:
        """When both CLAUDE.md and .claude/CLAUDE.md exist, only CLAUDE.md is loaded (First-Match-Wins)."""
        (workspace_dir / "CLAUDE.md").write_text("# Root Claude rules")
        claude_dir = workspace_dir / ".claude"
        claude_dir.mkdir()
        (claude_dir / "CLAUDE.md").write_text("# Subdir Claude rules")
        results = _scan_directory(workspace_dir)
        sources = [r.source for r in results]
        assert ".claude/CLAUDE.md" not in sources
        assert "CLAUDE.md" in sources

    def test_hermes_md_overrides_agents_md(self, workspace_dir: Path) -> None:
        (workspace_dir / ".hermes.md").write_text("# Hermes rules")
        (workspace_dir / "AGENTS.md").write_text("# Agent rules")
        results = _scan_directory(workspace_dir)
        sources = {r.source for r in results}
        assert ".hermes.md" in sources
        assert "AGENTS.md" not in sources

    def test_discovers_windsurfrules(self, workspace_dir: Path) -> None:
        (workspace_dir / ".windsurfrules").write_text("# Windsurf project rules")
        results = _scan_directory(workspace_dir)
        assert any(r.source == ".windsurfrules" for r in results)
        assert any("Windsurf project rules" in r.content for r in results)

    def test_discovers_soul_md(self, workspace_dir: Path) -> None:
        (workspace_dir / "SOUL.md").write_text("# Agent persona definition")
        results = _scan_directory(workspace_dir)
        assert any(r.source == "SOUL.md" for r in results)
        assert any("Agent persona definition" in r.content for r in results)

    def test_discovers_soul_md_lowercase(self, workspace_dir: Path) -> None:
        (workspace_dir / "soul.md").write_text("# lowercase soul rules")
        results = _scan_directory(workspace_dir)
        # On case-insensitive FS (macOS), SOUL.md matches first since it's higher priority
        assert any(r.source in ("soul.md", "SOUL.md") for r in results)
        assert any("lowercase soul rules" in r.content for r in results)

    def test_soul_md_overridden_by_higher_priority(self, workspace_dir: Path) -> None:
        """SOUL.md has lower priority than .myrm.md; First-Match-Wins blocks it."""
        (workspace_dir / ".myrm.md").write_text("# Myrm rules")
        (workspace_dir / "SOUL.md").write_text("# Soul rules")
        results = _scan_directory(workspace_dir)
        sources = {r.source for r in results}
        assert ".myrm.md" in sources
        assert "SOUL.md" not in sources

    def test_soul_md_overrides_agents_md(self, workspace_dir: Path) -> None:
        """SOUL.md has higher priority than AGENTS.md."""
        (workspace_dir / "SOUL.md").write_text("# Soul persona")
        (workspace_dir / "AGENTS.md").write_text("# Agent rules")
        results = _scan_directory(workspace_dir)
        sources = {r.source for r in results}
        assert "SOUL.md" in sources
        assert "AGENTS.md" not in sources

    def test_discovers_memory_md(self, workspace_dir: Path) -> None:
        (workspace_dir / "MEMORY.md").write_text("# Project background and context")
        results = _scan_directory(workspace_dir)
        assert any(r.source == "MEMORY.md" for r in results)
        assert any("Project background and context" in r.content for r in results)

    def test_discovers_memory_md_lowercase(self, workspace_dir: Path) -> None:
        (workspace_dir / "memory.md").write_text("# lowercase memory file")
        results = _scan_directory(workspace_dir)
        assert any(r.source in ("memory.md", "MEMORY.md") for r in results)
        assert any("lowercase memory file" in r.content for r in results)

    def test_memory_md_overridden_by_soul_md(self, workspace_dir: Path) -> None:
        """SOUL.md has higher priority than MEMORY.md; First-Match-Wins blocks it."""
        (workspace_dir / "SOUL.md").write_text("# Soul persona")
        (workspace_dir / "MEMORY.md").write_text("# Memory context")
        results = _scan_directory(workspace_dir)
        sources = {r.source for r in results}
        assert "SOUL.md" in sources
        assert "MEMORY.md" not in sources

    def test_memory_md_overrides_agents_md(self, workspace_dir: Path) -> None:
        """MEMORY.md has higher priority than AGENTS.md."""
        (workspace_dir / "MEMORY.md").write_text("# Project memory")
        (workspace_dir / "AGENTS.md").write_text("# Agent rules")
        results = _scan_directory(workspace_dir)
        sources = {r.source for r in results}
        assert "MEMORY.md" in sources
        assert "AGENTS.md" not in sources

    def test_discovers_clinerules(self, workspace_dir: Path) -> None:
        (workspace_dir / ".clinerules").write_text("# Cline IDE rules")
        results = _scan_directory(workspace_dir)
        assert any(r.source == ".clinerules" for r in results)
        assert any("Cline IDE rules" in r.content for r in results)

    def test_clinerules_overridden_by_cursorrules(self, workspace_dir: Path) -> None:
        """.cursorrules has higher priority than .clinerules; First-Match-Wins blocks it."""
        (workspace_dir / ".cursorrules").write_text("# Cursor rules")
        (workspace_dir / ".clinerules").write_text("# Cline rules")
        results = _scan_directory(workspace_dir)
        sources = {r.source for r in results}
        assert ".cursorrules" in sources
        assert ".clinerules" not in sources

    def test_discovers_copilot_instructions(self, workspace_dir: Path) -> None:
        github_dir = workspace_dir / ".github"
        github_dir.mkdir()
        (github_dir / "copilot-instructions.md").write_text("# Copilot instructions")
        results = _scan_directory(workspace_dir)
        assert any(r.source == ".github/copilot-instructions.md" for r in results)
        assert any("Copilot instructions" in r.content for r in results)

    def test_copilot_instructions_overridden_by_agents_md(self, workspace_dir: Path) -> None:
        (workspace_dir / "AGENTS.md").write_text("# Agents")
        (workspace_dir / ".windsurfrules").write_text("# Windsurf")
        github_dir = workspace_dir / ".github"
        github_dir.mkdir()
        (github_dir / "copilot-instructions.md").write_text("# Copilot")
        results = _scan_directory(workspace_dir)
        sources = {r.source for r in results}
        assert "AGENTS.md" in sources
        assert ".windsurfrules" not in sources
        assert ".github/copilot-instructions.md" not in sources
