"""Unit tests for competitor data auto-discovery service.

Validates detection logic, confidence scoring, memory/skill counting,
API key detection, and edge-case handling for the four supported sources
(Hermes, Claude Code, OpenClaw, Codex).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.migration.source_discovery import (
    DiscoveryResult,
    discover_external_sources,
)


@pytest.fixture()
def fake_home(tmp_path: Path) -> Path:
    return tmp_path


class TestDiscoverCompetitorsEmpty:
    """No competitor data present on disk."""

    def test_empty_home_returns_no_sources(self, fake_home: Path) -> None:
        result = discover_external_sources(str(fake_home))
        assert isinstance(result, DiscoveryResult)
        assert result.sources == []
        assert result.scan_path == str(fake_home)


class TestHermesDiscovery:
    """Hermes ~/.hermes detection and metadata extraction."""

    def _setup_hermes(
        self,
        home: Path,
        *,
        with_memory: bool = True,
        with_config: bool = True,
        with_soul: bool = False,
        with_skills: int = 0,
        with_env_keys: bool = False,
    ) -> Path:
        root = home / ".hermes"
        root.mkdir()
        if with_config:
            (root / "config.yaml").write_text("model: gpt-4o")
        if with_soul:
            (root / "SOUL.md").write_text("# Soul\nI am a helpful assistant")
        if with_memory:
            mem_dir = root / "memories"
            mem_dir.mkdir()
            (mem_dir / "MEMORY.md").write_text("- User likes Python\n- User prefers dark theme\n- Works at Acme")
            (mem_dir / "USER.md").write_text("- Name: Alice\n- Role: Engineer")
        if with_skills > 0:
            skills_dir = root / "skills"
            skills_dir.mkdir()
            for i in range(with_skills):
                skill_dir = skills_dir / f"skill_{i}"
                skill_dir.mkdir()
                (skill_dir / "SKILL.md").write_text(f"# Skill {i}")
        if with_env_keys:
            (root / ".env").write_text("OPENAI_API_KEY=sk-test-123\nANTHROPIC_API_KEY=ant-key")
        return root

    def test_hermes_high_confidence_with_memory_and_config(self, fake_home: Path) -> None:
        self._setup_hermes(fake_home)
        result = discover_external_sources(str(fake_home))
        assert len(result.sources) == 1
        src = result.sources[0]
        assert src.competitor == "hermes"
        assert src.confidence == "high"
        assert src.memory_count_estimate == 3

    def test_hermes_medium_confidence_config_only(self, fake_home: Path) -> None:
        self._setup_hermes(fake_home, with_memory=False, with_config=True)
        result = discover_external_sources(str(fake_home))
        assert len(result.sources) == 1
        assert result.sources[0].confidence == "medium"

    def test_hermes_medium_confidence_soul_only(self, fake_home: Path) -> None:
        self._setup_hermes(fake_home, with_memory=False, with_config=False, with_soul=True)
        result = discover_external_sources(str(fake_home))
        assert len(result.sources) == 1
        assert result.sources[0].confidence == "medium"

    def test_hermes_skill_counting(self, fake_home: Path) -> None:
        self._setup_hermes(fake_home, with_skills=3)
        result = discover_external_sources(str(fake_home))
        src = result.sources[0]
        assert src.skill_count == 3

    def test_hermes_api_key_detection(self, fake_home: Path) -> None:
        self._setup_hermes(fake_home, with_env_keys=True)
        result = discover_external_sources(str(fake_home))
        src = result.sources[0]
        assert src.has_api_keys is True

    def test_hermes_no_api_keys(self, fake_home: Path) -> None:
        self._setup_hermes(fake_home)
        result = discover_external_sources(str(fake_home))
        assert result.sources[0].has_api_keys is False

    def test_hermes_low_confidence_excluded(self, fake_home: Path) -> None:
        """An empty .hermes dir with no recognizable files is filtered out."""
        (fake_home / ".hermes").mkdir()
        result = discover_external_sources(str(fake_home))
        hermes = [s for s in result.sources if s.competitor == "hermes"]
        assert hermes == []


class TestClaudeDiscovery:
    """Claude ~/.claude detection."""

    def _setup_claude(self, home: Path, *, with_memory: bool = True, with_settings: bool = True, skill_count: int = 0) -> Path:
        root = home / ".claude"
        root.mkdir()
        if with_memory:
            (root / "CLAUDE.md").write_text("- User prefers TypeScript\n- Uses VS Code")
        if with_settings:
            (root / "settings.json").write_text('{"theme": "dark"}')
        if skill_count > 0:
            skills_dir = root / "skills"
            skills_dir.mkdir()
            for i in range(skill_count):
                (skills_dir / f"skill_{i}").mkdir()
        return root

    def test_claude_high_confidence(self, fake_home: Path) -> None:
        self._setup_claude(fake_home)
        result = discover_external_sources(str(fake_home))
        claude = [s for s in result.sources if s.competitor == "claude"]
        assert len(claude) == 1
        assert claude[0].confidence == "high"
        assert claude[0].memory_count_estimate == 2

    def test_claude_medium_confidence_settings_only(self, fake_home: Path) -> None:
        self._setup_claude(fake_home, with_memory=False)
        result = discover_external_sources(str(fake_home))
        claude = [s for s in result.sources if s.competitor == "claude"]
        assert len(claude) == 1
        assert claude[0].confidence == "medium"

    def test_claude_skill_counting_via_skills_dir(self, fake_home: Path) -> None:
        self._setup_claude(fake_home, skill_count=2)
        result = discover_external_sources(str(fake_home))
        claude = [s for s in result.sources if s.competitor == "claude"]
        assert claude[0].skill_count == 2

    def test_claude_commands_counted_as_skills(self, fake_home: Path) -> None:
        root = fake_home / ".claude"
        root.mkdir()
        (root / "CLAUDE.md").write_text("- memory line")
        commands_dir = root / "commands"
        commands_dir.mkdir()
        (commands_dir / "deploy.md").write_text("deploy script")
        (commands_dir / "test.md").write_text("test script")
        result = discover_external_sources(str(fake_home))
        claude = [s for s in result.sources if s.competitor == "claude"]
        assert claude[0].skill_count == 2


class TestOpenClawDiscovery:
    """OpenClaw ~/.openclaw detection."""

    def test_openclaw_high_confidence(self, fake_home: Path) -> None:
        root = fake_home / ".openclaw"
        root.mkdir()
        (root / "memory.json").write_text("[]")
        (root / "sessions.json").write_text("[]")
        result = discover_external_sources(str(fake_home))
        oc = [s for s in result.sources if s.competitor == "openclaw"]
        assert len(oc) == 1
        assert oc[0].confidence == "high"

    def test_openclaw_medium_confidence_single_file(self, fake_home: Path) -> None:
        root = fake_home / ".openclaw"
        root.mkdir()
        (root / "config.json").write_text("{}")
        result = discover_external_sources(str(fake_home))
        oc = [s for s in result.sources if s.competitor == "openclaw"]
        assert len(oc) == 1
        assert oc[0].confidence == "medium"

    def test_openclaw_low_confidence_excluded(self, fake_home: Path) -> None:
        (fake_home / ".openclaw").mkdir()
        result = discover_external_sources(str(fake_home))
        oc = [s for s in result.sources if s.competitor == "openclaw"]
        assert oc == []

    def test_openclaw_skill_counting(self, fake_home: Path) -> None:
        root = fake_home / ".openclaw"
        root.mkdir()
        (root / "memory.json").write_text("[]")
        (root / "sessions.json").write_text("[]")
        skills_dir = root / "skills"
        skills_dir.mkdir()
        (skills_dir / "skill_a.json").write_text("{}")
        (skills_dir / "skill_b.json").write_text("{}")
        result = discover_external_sources(str(fake_home))
        assert result.sources[0].skill_count == 2


class TestCodexDiscovery:
    """Codex ~/.codex detection."""

    def test_codex_high_confidence(self, fake_home: Path) -> None:
        root = fake_home / ".codex"
        root.mkdir()
        (root / "instructions.md").write_text("# Instructions")
        (root / "config.json").write_text("{}")
        result = discover_external_sources(str(fake_home))
        cdx = [s for s in result.sources if s.competitor == "codex"]
        assert len(cdx) == 1
        assert cdx[0].confidence == "high"

    def test_codex_medium_confidence_single_file(self, fake_home: Path) -> None:
        root = fake_home / ".codex"
        root.mkdir()
        (root / "instructions.md").write_text("use python")
        result = discover_external_sources(str(fake_home))
        cdx = [s for s in result.sources if s.competitor == "codex"]
        assert len(cdx) == 1
        assert cdx[0].confidence == "medium"

    def test_codex_low_confidence_excluded(self, fake_home: Path) -> None:
        (fake_home / ".codex").mkdir()
        result = discover_external_sources(str(fake_home))
        cdx = [s for s in result.sources if s.competitor == "codex"]
        assert cdx == []


class TestMultipleCompetitors:
    """Multiple external assistant installations co-exist."""

    def test_discover_all_competitors(self, fake_home: Path) -> None:
        for name, files in [
            (".hermes", {"config.yaml": "m: 1", "memories/MEMORY.md": "- fact"}),
            (".claude", {"CLAUDE.md": "- pref", "settings.json": "{}"}),
            (".openclaw", {"memory.json": "[]", "sessions.json": "[]"}),
            (".codex", {"instructions.md": "# I", "config.json": "{}"}),
        ]:
            root = fake_home / name
            root.mkdir(exist_ok=True, parents=True)
            for relpath, content in files.items():
                f = root / relpath
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(content)

        result = discover_external_sources(str(fake_home))
        competitors = {s.competitor for s in result.sources}
        assert "hermes" in competitors
        assert "claude" in competitors
        assert "openclaw" in competitors
        assert "codex" in competitors
        assert len(competitors) == 4


class TestEdgeCases:
    """Robustness and edge cases."""

    def test_nonexistent_home_dir(self, tmp_path: Path) -> None:
        fake = tmp_path / "nonexistent"
        result = discover_external_sources(str(fake))
        assert result.sources == []

    def test_memory_bullet_counting_complex_markdown(self, fake_home: Path) -> None:
        root = fake_home / ".hermes"
        root.mkdir()
        (root / "config.yaml").write_text("model: gpt-4o")
        mem_dir = root / "memories"
        mem_dir.mkdir()
        md = "# Section A\n- fact 1\n- fact 2\n\n# Section B\n* fact 3\n\nParagraph text (not a bullet)\n- fact 4"
        (mem_dir / "MEMORY.md").write_text(md)
        result = discover_external_sources(str(fake_home))
        src = result.sources[0]
        assert src.memory_count_estimate == 4

    def test_discovered_file_has_size(self, fake_home: Path) -> None:
        root = fake_home / ".hermes"
        root.mkdir()
        content = "model: gpt-4o\napi_key: abc"
        (root / "config.yaml").write_text(content)
        mem_dir = root / "memories"
        mem_dir.mkdir()
        (mem_dir / "MEMORY.md").write_text("- fact")
        result = discover_external_sources(str(fake_home))
        src = result.sources[0]
        config_file = next(f for f in src.files if f.kind == "config")
        assert config_file.size_bytes > 0
