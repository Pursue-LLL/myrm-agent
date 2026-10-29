"""Tests for the reads behind the workspace trust disclosure: a hostile folder must not stall or exhaust the prompt.

[INPUT]
- agent.security.workspace_trust.manifest::build_workspace_trust_manifest (POS: the pre-trust scan under test)
- agent.security.workspace_trust.repo_policy::load_repo_command_prefixes, MAX_WORKSPACE_CONFIG_CHARS (POS: config reader)
- backends.skills.local::scan_workspace_skills (POS: workspace skill scan the manifest counts)
- tests.support.guarded_child::run_guarded (POS: child process killed on a memory or time overrun)

[OUTPUT]
- Fails when the manifest of a folder holding an endless device, a FIFO or a multi-gigabyte sparse file as ``SKILL.md``,
  ``mcp.json`` or ``.myrm/config.toml`` does not finish within a bounded amount of memory and time, or when a folder of ordinary
  files is disclosed with other counts or prefixes than the files declare.

[POS]
The trust prompt is the first thing a user sees for a folder they have not trusted yet, so everything the manifest reads
runs on untrusted bytes. The hostile cases run in a guarded child process (a regression ends as a failed assertion, not
as an exhausted machine); the readable-folder cases pin that bounding the reads changed nothing for honest files.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.agent.security.workspace_trust.manifest import build_workspace_trust_manifest
from myrm_agent_harness.agent.security.workspace_trust.repo_policy import (
    MAX_WORKSPACE_CONFIG_CHARS,
    load_repo_command_prefixes,
)
from tests.support.guarded_child import run_guarded

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="FIFOs, device nodes and sparse files are POSIX")
SPARSE_BYTES = 512 * 1024 * 1024

_SKILL = "---\nname: demo\ndescription: A demo skill used by the trust tests.\n---\n\nBody.\n"

_CHILD = """
import json, sys
from myrm_agent_harness.agent.security.workspace_trust.manifest import build_workspace_trust_manifest

manifest = build_workspace_trust_manifest(sys.argv[1])
print(json.dumps({
    "skills": manifest.skill_count,
    "mcps": manifest.mcp_count,
    "prefixes": list(manifest.repo_command_prefixes),
    "has_config": manifest.has_myrm_config,
}))
"""


def _skill_dir(root: Path) -> Path:
    directory = root / "skills" / "demo"
    directory.mkdir(parents=True)
    return directory


def _sparse(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    try:
        os.truncate(path, SPARSE_BYTES)
    except OSError:
        pytest.skip("the file system does not hold sparse files this large")


def _manifest_in_child(root: Path) -> dict[str, object]:
    run = run_guarded(f"import sys; sys.argv = ['child', {str(root)!r}]\n{_CHILD}", max_rss_mb=256, timeout_s=20.0)

    assert not run.over_memory, f"the scan held {run.peak_rss_mb:.0f} MB"
    assert not run.timed_out, "the scan did not finish"
    assert run.returncode == 0, run.stderr
    manifest: dict[str, object] = json.loads(run.stdout)
    return manifest


@POSIX_ONLY
class TestHostileFolderIsDisclosedWithinBounds:
    def test_a_skill_that_is_an_endless_device(self, tmp_path: Path) -> None:
        (_skill_dir(tmp_path) / "SKILL.md").symlink_to("/dev/zero")

        assert _manifest_in_child(tmp_path)["skills"] == 0

    def test_a_skill_that_is_a_fifo(self, tmp_path: Path) -> None:
        os.mkfifo(_skill_dir(tmp_path) / "SKILL.md")

        assert _manifest_in_child(tmp_path)["skills"] == 0

    def test_a_sparse_mcp_config_counts_as_one_unreadable_server(self, tmp_path: Path) -> None:
        _sparse(tmp_path / "mcp.json")

        assert _manifest_in_child(tmp_path)["mcps"] == 1

    def test_a_sparse_repo_config_declares_nothing(self, tmp_path: Path) -> None:
        _sparse(tmp_path / ".myrm" / "config.toml")

        outcome = _manifest_in_child(tmp_path)

        assert outcome["prefixes"] == []
        assert outcome["has_config"] is True


class TestHonestFolderIsDisclosedAsBefore:
    def test_a_skill_is_counted(self, tmp_path: Path) -> None:
        (_skill_dir(tmp_path) / "SKILL.md").write_text(_SKILL, encoding="utf-8")

        assert build_workspace_trust_manifest(str(tmp_path)).skill_count == 1

    def test_a_skill_with_invalid_utf8_is_still_skipped(self, tmp_path: Path) -> None:
        (_skill_dir(tmp_path) / "SKILL.md").write_bytes(_SKILL.encode() + b"\xff\xfe")

        assert build_workspace_trust_manifest(str(tmp_path)).skill_count == 0

    def test_a_skill_over_the_size_limit_is_still_skipped(self, tmp_path: Path) -> None:
        (_skill_dir(tmp_path) / "SKILL.md").write_text(_SKILL + "x" * (1024 * 1024), encoding="utf-8")

        assert build_workspace_trust_manifest(str(tmp_path)).skill_count == 0

    def test_a_skill_over_the_limit_in_bytes_but_not_in_characters_is_still_skipped(self, tmp_path: Path) -> None:
        # 400,000 characters of three bytes each: 1.2 MB on disk, well under the character limit of the bounded read.
        (_skill_dir(tmp_path) / "SKILL.md").write_text(_SKILL + "\u4e2d" * 400_000, encoding="utf-8")

        assert build_workspace_trust_manifest(str(tmp_path)).skill_count == 0

    def test_mcp_servers_are_counted_by_name(self, tmp_path: Path) -> None:
        (tmp_path / "mcp.json").write_text(json.dumps({"mcpServers": {"a": {}, "b": {}}}), encoding="utf-8")
        (tmp_path / ".cursor").mkdir()
        (tmp_path / ".cursor" / "mcp.json").write_text("{not json", encoding="utf-8")

        assert build_workspace_trust_manifest(str(tmp_path)).mcp_count == 3

    def test_an_mcp_config_over_the_limit_counts_as_one_unreadable_server(self, tmp_path: Path) -> None:
        servers: dict[str, dict[str, object]] = {f"s{i}": {} for i in range(MAX_WORKSPACE_CONFIG_CHARS // 8)}
        (tmp_path / "mcp.json").write_text(json.dumps({"mcpServers": servers}), encoding="utf-8")

        assert build_workspace_trust_manifest(str(tmp_path)).mcp_count == 1

    def test_declared_prefixes_are_read(self, tmp_path: Path) -> None:
        config = tmp_path / ".myrm" / "config.toml"
        config.parent.mkdir()
        config.write_text('[security]\ncommand_prefixes = ["make lint"]\n', encoding="utf-8")

        assert load_repo_command_prefixes(tmp_path) == ("make lint",)

    def test_a_repo_config_over_the_limit_declares_nothing_and_says_why(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        config = tmp_path / ".myrm" / "config.toml"
        config.parent.mkdir()
        padding = "# " + "x" * MAX_WORKSPACE_CONFIG_CHARS + "\n"
        config.write_text(padding + '[security]\ncommand_prefixes = ["make lint"]\n', encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            assert load_repo_command_prefixes(tmp_path) == ()

        assert "larger than" in caplog.text
