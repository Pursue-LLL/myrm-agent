"""An export says what it could not include; a file that merely vanished while it ran is not a loss."""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.infra.state_archive import read_manifest

from app.services.instance_archive import export_service
from app.services.instance_archive.export_service import ExportResult, build_export
from tests.services.instance_archive.conftest import PERMISSIONS_ENFORCED


def _export(source: Path, dest: Path) -> ExportResult:
    return build_export(
        state_dir=source,
        dest=dest,
        user_id="user-a",
        app_version="1.0.0",
        deploy_mode="local",
        config_key=None,
        passphrase=None,
    )


def test_an_export_that_read_everything_reports_nothing_left_out(source_state: Path, tmp_path: Path) -> None:
    result = _export(source_state, tmp_path / "out.zip")

    assert result.unreadable == ()
    assert read_manifest(result.path).metadata["unreadable_count"] == 0


@pytest.mark.skipif(not PERMISSIONS_ENFORCED, reason="needs POSIX permissions that apply to the current user")
def test_a_file_and_a_directory_that_cannot_be_read_are_reported_and_the_archive_stays_valid(
    source_state: Path, tmp_path: Path
) -> None:
    locked_file = source_state / "wiki" / "locked.md"
    locked_file.write_text("cannot be opened")
    locked_dir = source_state / "wiki" / "private"
    locked_dir.mkdir()
    (locked_dir / "note.md").write_text("cannot be listed")
    locked_file.chmod(0)
    locked_dir.chmod(0)
    try:
        result = _export(source_state, tmp_path / "out.zip")
    finally:
        locked_file.chmod(0o600)
        locked_dir.chmod(0o700)

    assert result.unreadable == ("wiki/locked.md", "wiki/private")
    manifest = read_manifest(result.path)
    carried = {entry.path for entry in manifest.entries}
    assert "wiki/page.md" in carried
    assert not carried & {"wiki/locked.md", "wiki/private/note.md"}
    assert manifest.metadata["unreadable_count"] == 2  # the archive itself says what it lacks


def test_a_file_removed_while_the_export_runs_is_not_a_loss(
    source_state: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_scan = export_service.scan_state_dir

    def scan_then_remove(state_dir: Path):
        scan = real_scan(state_dir)
        (state_dir / "wiki" / "page.md").unlink()
        return scan

    monkeypatch.setattr(export_service, "scan_state_dir", scan_then_remove)

    result = _export(source_state, tmp_path / "out.zip")

    manifest = read_manifest(result.path)
    assert result.unreadable == ()
    assert manifest.metadata["unreadable_count"] == 0
    assert "wiki/page.md" not in {entry.path for entry in manifest.entries}
