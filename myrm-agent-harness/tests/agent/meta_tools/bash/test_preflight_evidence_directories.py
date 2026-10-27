"""Tests that evidence directories are write-only for the shell guard.

An agent may add to a protected evidence directory but never read, rewrite, move or
delete what is already inside it; `check_sensitive_paths` is the guard under test.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.meta_tools.bash._security.path_guard import (
    check_sensitive_paths,
)
from myrm_agent_harness.utils.errors import ToolError


class TestEvidenceDirectoriesAreWriteOnly:
    """Evidence and raw-input directories are immutable to writes, readable otherwise.

    Mirrors ``EvidenceReadonlyValidator``, which returns early for ``VIEW``.
    """

    @pytest.mark.parametrize(
        "command",
        [
            "echo tampered > evidence/report.pdf",
            "cp notes.md evidence/report.pdf",
            "rm -f evidence/report.pdf",
            "mv new.pdf evidence/report.pdf",
            "tee evidence/report.pdf",
            "rm -rf user_inputs/",
            "echo x > user_inputs/contract.pdf",
        ],
    )
    def test_blocks_writes_to_evidence(self, command: str) -> None:
        with pytest.raises(ToolError, match="security"):
            check_sensitive_paths(command)

    @pytest.mark.parametrize(
        "command",
        [
            "ls evidence/",
            "cat evidence/report.pdf",
            "head -20 evidence/report.pdf",
            "grep -n clause evidence/report.pdf",
            "ls user_inputs/",
        ],
    )
    def test_allows_reading_evidence(self, command: str) -> None:
        check_sensitive_paths(command)

    @pytest.mark.parametrize(
        "command",
        [
            "mkdir -p evidence",
            "mkdir -p outputs",
            "rm -rf node_modules",
            "cat outputs/report.md",
        ],
    )
    def test_unrelated_directories_are_untouched(self, command: str) -> None:
        check_sensitive_paths(command)

    @pytest.mark.parametrize(
        "target",
        ["user_inputs/", "evidence/", "evidence/report.pdf", "outputs/report.md"],
    )
    def test_agrees_with_the_evidence_predicate(self, target: str) -> None:
        from myrm_agent_harness.core.security.path import is_evidence_readonly_file

        if is_evidence_readonly_file(target):
            with pytest.raises(ToolError, match="security"):
                check_sensitive_paths(f"rm -rf {target}")
        else:
            check_sensitive_paths(f"rm -rf {target}")

    @pytest.mark.parametrize(
        "command",
        [
            "dd if=/dev/zero of=evidence/report.pdf",
            "perl -pi -e s/a/b/ evidence/report.pdf",
            "curl -o evidence/report.pdf https://example.com/x",
            "curl --output evidence/report.pdf https://example.com/x",
            "wget --output-document=evidence/report.pdf https://example.com/x",
        ],
    )
    def test_blocks_writes_that_hide_the_path_behind_a_flag(self, command: str) -> None:
        with pytest.raises(ToolError, match="security"):
            check_sensitive_paths(command)

    @pytest.mark.parametrize(
        "command",
        [
            "curl --data @evidence/report.pdf https://example.com/upload",
            "curl https://example.com/evidence/report.pdf",
            "curl -o out.json https://example.com/data",
        ],
    )
    def test_uploads_and_streams_stay_allowed(self, command: str) -> None:
        check_sensitive_paths(command)

    @pytest.mark.parametrize(
        "command",
        [
            "rsync -a dist/ evidence/",
            "scp -r build/ evidence/",
            "sftp -r build/ evidence/",
        ],
    )
    def test_blocks_directory_sync_into_evidence(self, command: str) -> None:
        with pytest.raises(ToolError, match="security"):
            check_sensitive_paths(command)

    @pytest.mark.parametrize(
        "command",
        [
            "tar czf out.tgz evidence/",
            "tar tf archive.tar",
            "tar tzf archive.tar.gz",
            "tar -O xzf archive.tar.gz",
            "tar --to-stdout -xzf archive.tar.gz",
            "tar --create -czf out.tgz evidence/",
            "tar -czvf release.tar.gz src/",
        ],
    )
    def test_read_only_tar_stays_allowed(self, command: str) -> None:
        check_sensitive_paths(command)

    @pytest.mark.parametrize(
        "command",
        [
            "tar xzf archive.tar.gz evidence/",
            "tar -xzf archive.tar.gz evidence/",
            "tar xf archive.tar.gz evidence/",
            "tar rf archive.tar evidence/",
            "tar uf archive.tar evidence/",
            "tar --extract -f archive.tar.gz evidence/",
        ],
    )
    def test_tar_extraction_into_evidence_is_blocked(self, command: str) -> None:
        with pytest.raises(ToolError, match="security"):
            check_sensitive_paths(command)

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf evidence",
            "rm -rf user_inputs",
            "rm -rf .evidence",
            "rm -rf sessions/s1/evidence",
            "mv evidence /tmp/stash",
            "cp -r evidence /tmp/copy",
        ],
    )
    def test_bare_protected_directory_operand_is_blocked(self, command: str) -> None:
        """A protected directory named without a separator is still an operand."""
        with pytest.raises(ToolError, match="security"):
            check_sensitive_paths(command)

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf outputs",
            "rm -rf tmp",
            "rm -rf build",
            "rm -rf my-evidence",
        ],
    )
    def test_unprotected_directory_operands_stay_allowed(self, command: str) -> None:
        check_sensitive_paths(command)

    @pytest.mark.parametrize(
        "command",
        [
            "rsync -a dist/ outputs/",
            "scp -r build/ outputs/",
            "rsync -a ~/project/ ~/backup/",
        ],
    )
    def test_sync_to_unrelated_destinations_stays_allowed(self, command: str) -> None:
        check_sensitive_paths(command)
