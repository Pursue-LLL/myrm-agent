"""Outbound sensitive-file gate: key and credential files never leave the machine through an IM channel.

Attachments reach the bus from the deliverable scanner, tool artifacts and agent replies; none of those
producers checks what a file is, and IM chats (unlike the WebUI) have no confirmation step.
"""

from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path

import pytest

from app.channels.core.outbound_attachment_guard import withhold_sensitive_attachments
from app.channels.core.outbound_prepare import prepare_outbound
from app.channels.i18n import channel_t, get_locale_from_metadata
from app.channels.types import ChannelCapabilities, MediaAttachment, MediaType, OutboundMessage
from tests.channels.core.outbound_testkit import ProbeChannel, make_msg, running_bus

_ZIP_MAGIC = b"PK\x03\x04"


def _attach(tmp_path: Path, name: str, data: bytes = b"data") -> MediaAttachment:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return MediaAttachment(media_type=MediaType.DOCUMENT, path=str(path))


def _note(name: str, msg: OutboundMessage | None = None) -> str:
    return str(channel_t(get_locale_from_metadata(msg.metadata if msg else None), "attachment_withheld_note", name=name))


def _names(msg: OutboundMessage) -> list[str]:
    return [m.display_name for m in msg.media]


def test_credential_files_are_withheld_and_the_rest_is_delivered(tmp_path: Path) -> None:
    """The deliverable scanner picks up every file the agent touched in the workspace, secrets included."""
    media = (
        _attach(tmp_path, ".env", b"API_KEY=sk-live-123"),
        _attach(tmp_path, "config.json", b"{}"),
        _attach(tmp_path, "secrets.json", b"{}"),
        _attach(tmp_path, "server.key", b"-----BEGIN PRIVATE KEY-----\nMIIE"),
        _attach(tmp_path, "deck.key", _ZIP_MAGIC + b"keynote"),
        _attach(tmp_path, "notes.txt", b"meeting notes"),
    )

    result = withhold_sensitive_attachments(make_msg("Here are the files", media=media))

    assert _names(result) == ["deck.key", "notes.txt"]
    assert result.content.startswith("Here are the files\n\n")
    assert all(_note(name) in result.content for name in (".env", "config.json", "secrets.json", "server.key"))
    assert _note("deck.key") not in result.content
    assert _note("notes.txt") not in result.content


def test_symlink_cannot_disguise_a_credential_file(tmp_path: Path) -> None:
    target = tmp_path / "ssh" / "id_rsa"
    target.parent.mkdir()
    target.write_bytes(b"private")
    link = tmp_path / "report.txt"
    link.symlink_to(target)

    result = withhold_sensitive_attachments(make_msg("", media=(MediaAttachment(media_type=MediaType.DOCUMENT, path=str(link)),)))

    assert result.media == ()
    assert result.content == _note("report.txt")


@pytest.mark.parametrize("name", ["ID_RSA", "Key.PEM", "credentials.JSON"])
def test_matching_ignores_case(tmp_path: Path, name: str) -> None:
    assert withhold_sensitive_attachments(make_msg("x", media=(_attach(tmp_path, name),))).media == ()


def test_unreadable_dot_key_file_is_withheld(tmp_path: Path) -> None:
    """A ``.key`` file is only released once it proves to be a Keynote bundle; when that cannot be proven it stays home."""
    missing = MediaAttachment(media_type=MediaType.DOCUMENT, path=str(tmp_path / "gone.key"))

    assert withhold_sensitive_attachments(make_msg("x", media=(missing,))).media == ()


def test_system_made_and_remote_attachments_are_not_inspected(tmp_path: Path) -> None:
    temp_shot = MediaAttachment(media_type=MediaType.IMAGE, path=str(tmp_path / "secrets.json"), ephemeral=True)
    remote = MediaAttachment(media_type=MediaType.DOCUMENT, url="https://example.test/.env")
    msg = make_msg("x", media=(temp_shot, remote))

    assert withhold_sensitive_attachments(msg) is msg


def test_message_without_sensitive_attachments_is_returned_untouched(tmp_path: Path) -> None:
    for msg in (make_msg("plain"), make_msg("with file", media=(_attach(tmp_path, "notes.txt"),))):
        assert withhold_sensitive_attachments(msg) is msg


@pytest.mark.parametrize("locale", ["en", "zh", "ja"])
def test_note_is_localized_for_the_recipient(tmp_path: Path, locale: str) -> None:
    msg = dataclasses.replace(make_msg("x", media=(_attach(tmp_path, "server.pem"),)), metadata={"locale": locale})

    result = withhold_sensitive_attachments(msg)

    assert result.content == f"x\n\n{_note('server.pem', msg)}"
    assert "attachment_withheld_note" not in result.content


def test_note_is_translated_in_every_catalog() -> None:
    notes = {loc: str(channel_t(loc, "attachment_withheld_note", name="a.pem")) for loc in ("en", "zh-CN", "zh-TW", "ja")}

    assert len(set(notes.values())) == 4
    assert all("a.pem" in note and "attachment_withheld_note" not in note for note in notes.values())


def test_only_attachments_become_just_the_note(tmp_path: Path) -> None:
    result = withhold_sensitive_attachments(make_msg("", media=(_attach(tmp_path, ".env"), _attach(tmp_path, "id_rsa"))))

    assert result.media == ()
    assert result.content == f"{_note('.env')}\n{_note('id_rsa')}"


def test_withheld_attachment_is_not_reported_as_unsupported(tmp_path: Path) -> None:
    """The gate runs before the capability downgrade, so a recipient is told the real reason."""
    msg = make_msg("hi", media=(_attach(tmp_path, ".env"), _attach(tmp_path, "notes.txt")))

    result = prepare_outbound(msg, ChannelCapabilities(), channel_name="probe")

    assert result.media == ()
    assert _note(".env") in result.content
    assert str(channel_t("en", "attachment_omitted_note", name=".env")) not in result.content
    assert str(channel_t("en", "attachment_omitted_note", name="notes.txt")) in result.content


async def test_direct_send_never_hands_credentials_to_the_provider(tmp_path: Path) -> None:
    channel = ProbeChannel()

    async with running_bus(None, channel) as bus:
        await bus.send_now(make_msg("files", media=(_attach(tmp_path, ".env"), _attach(tmp_path, "notes.txt"))))

    assert _names(channel.sent[0]) == ["notes.txt"]
    assert _note(".env") in channel.sent[0].content


async def test_queued_send_never_hands_credentials_to_the_provider(tmp_path: Path) -> None:
    channel = ProbeChannel()

    async with running_bus(tmp_path / "outbox", channel) as bus:
        await bus.publish_outbound(make_msg("files", media=(_attach(tmp_path, "id_rsa"), _attach(tmp_path, "notes.txt"))))
        await asyncio.sleep(0.3)

    assert _names(channel.sent[0]) == ["notes.txt"]
    assert _note("id_rsa") in channel.sent[0].content
