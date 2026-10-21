"""Tests for the lifecycle of temporary outbound attachment files."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.channels.core.outbound_media import discard_ephemeral_media
from app.channels.types import MediaAttachment, MediaType, OutboundMessage


def _temp_file(suffix: str = ".png") -> Path:
    with tempfile.NamedTemporaryFile(suffix=suffix, prefix="outbound_media_test_", delete=False) as tmp:
        tmp.write(b"data")
    return Path(tmp.name)


def _attachment(path: Path | str | None, *, ephemeral: bool) -> MediaAttachment:
    return MediaAttachment(media_type=MediaType.IMAGE, path=None if path is None else str(path), ephemeral=ephemeral)


class TestDiscardEphemeralMedia:
    def test_deletes_ephemeral_temp_file(self) -> None:
        path = _temp_file()

        discard_ephemeral_media([_attachment(path, ephemeral=True)])

        assert not path.exists()

    def test_keeps_files_that_are_not_flagged_ephemeral(self, tmp_path: Path) -> None:
        workspace_file = tmp_path / "report.pdf"
        workspace_file.write_bytes(b"%PDF")

        discard_ephemeral_media([_attachment(workspace_file, ephemeral=False)])

        assert workspace_file.exists()

    def test_keeps_paths_a_failure_record_still_references(self) -> None:
        needed, spent = _temp_file(), _temp_file()

        discard_ephemeral_media(
            [_attachment(needed, ephemeral=True), _attachment(spent, ephemeral=True)],
            keep_paths={str(needed)},
        )

        assert needed.exists()
        assert not spent.exists()
        needed.unlink()

    def test_never_deletes_outside_the_temp_directory(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        temp_root = tmp_path / "temp-root"
        temp_root.mkdir()
        monkeypatch.setattr(tempfile, "tempdir", str(temp_root))
        user_file = tmp_path / "workspace" / "precious.csv"
        user_file.parent.mkdir()
        user_file.write_text("keep me")

        discard_ephemeral_media([_attachment(user_file, ephemeral=True)])

        assert user_file.read_text() == "keep me"

    def test_missing_file_and_url_only_attachments_are_ignored(self) -> None:
        gone = Path(tempfile.gettempdir()) / "outbound_media_test_already_gone.png"
        url_only = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/a.png", ephemeral=True)

        discard_ephemeral_media([_attachment(gone, ephemeral=True), url_only, _attachment(None, ephemeral=True)])


class TestEphemeralSerialization:
    def test_flag_survives_the_durable_round_trip(self) -> None:
        msg = OutboundMessage(
            channel="telegram",
            recipient_id="c1",
            content="shot",
            user_id="u1",
            media=(_attachment("/tmp/a.png", ephemeral=True), _attachment("/tmp/b.png", ephemeral=False)),
        )

        restored = OutboundMessage.from_dict(msg.to_dict())

        assert [m.ephemeral for m in restored.media] == [True, False]

    def test_missing_flag_means_the_file_is_not_owned_by_the_bus(self) -> None:
        record = {"channel": "telegram", "recipient_id": "c1", "content": "x", "user_id": "u1"}
        record["media"] = [{"media_type": "image", "path": "/tmp/a.png"}]

        assert OutboundMessage.from_dict(record).media[0].ephemeral is False
