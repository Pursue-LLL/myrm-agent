"""Tests for the pre-trust manifest: path canonicalisation, the plugin count, and the scans that must never block the prompt.

[INPUT]
- agent.security.workspace_trust.manifest::build_workspace_trust_manifest, canonicalize_workspace_path (POS: the disclosure under test)
- real files in a temp directory (POS: the file system decides what is a plugin, nothing is faked)
- monkeypatched scanners (POS: stand-ins for a scan that breaks half way)

[OUTPUT]
- Fails when a blank or relative path is canonicalised wrongly, when the plugin count is not the number of plugin folders, archives and the
  root descriptor, or when a scan that raises stops the manifest from being built instead of counting zero.

[POS]
``test_workspace_trust_hostile_reads.py`` pins what a hostile folder cannot do to the manifest; this file pins what an honest or half-readable
folder yields, so the prompt always opens.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.agent.security.workspace_trust import manifest as manifest_module
from myrm_agent_harness.agent.security.workspace_trust.manifest import (
    build_workspace_trust_manifest,
    canonicalize_workspace_path,
)


def _broken(*_args: object, **_kwargs: object) -> int:
    raise RuntimeError("the scan broke half way")


class TestCanonicalPath:
    def test_a_blank_path_has_no_canonical_form(self) -> None:
        assert canonicalize_workspace_path("   ") == ""

    def test_a_relative_path_is_refused(self) -> None:
        with pytest.raises(ValueError, match="absolute"):
            canonicalize_workspace_path("some/where")

    def test_the_home_shortcut_is_expanded_and_symlinks_are_resolved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = tmp_path / "real"
        real.mkdir()
        (tmp_path / "link").symlink_to(real, target_is_directory=True)
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("USERPROFILE", str(tmp_path))

        assert canonicalize_workspace_path("~/link") == str(real.resolve())


class TestPluginCount:
    def test_folders_with_a_descriptor_archives_and_the_root_descriptor_count(self, tmp_path: Path) -> None:
        plugins = tmp_path / ".myrm" / "plugins"
        (plugins / "with-descriptor").mkdir(parents=True)
        (plugins / "with-descriptor" / "plugin.json").write_text("{}")
        (plugins / "without-descriptor").mkdir()
        (plugins / "packed.zip").write_bytes(b"PK")
        (plugins / "notes.txt").write_text("not a plugin")
        (tmp_path / "plugin.json").write_text("{}")

        assert build_workspace_trust_manifest(str(tmp_path)).plugin_count == 3

    def test_a_folder_without_plugins_counts_none(self, tmp_path: Path) -> None:
        assert build_workspace_trust_manifest(str(tmp_path)).plugin_count == 0


class TestScansThatBreak:
    """The disclosure is advisory: whichever scan breaks, the prompt still opens and that count is zero."""

    def test_a_skill_scan_that_raises_counts_zero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("myrm_agent_harness.backends.skills.local.scan_workspace_skills", _broken)

        assert build_workspace_trust_manifest(str(tmp_path)).skill_count == 0

    def test_a_rule_scan_that_raises_counts_zero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("myrm_agent_harness.agent.workspace_rules.scanner.scan_workspace_rules", _broken)

        assert build_workspace_trust_manifest(str(tmp_path)).rule_count == 0

    def test_an_mcp_scan_that_raises_counts_zero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "mcp.json").write_text('{"mcpServers": {"one": {}}}')
        monkeypatch.setattr(manifest_module, "_count_declared_servers", _broken)

        assert build_workspace_trust_manifest(str(tmp_path)).mcp_count == 0

    def test_a_plugin_folder_that_cannot_be_listed_counts_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".myrm" / "plugins").mkdir(parents=True)
        real_iterdir = Path.iterdir

        def refuse_the_plugin_folder(self: Path) -> Iterator[Path]:
            if self.name == "plugins":
                raise PermissionError("not allowed")
            return real_iterdir(self)

        monkeypatch.setattr(Path, "iterdir", refuse_the_plugin_folder)

        assert build_workspace_trust_manifest(str(tmp_path)).plugin_count == 0
