"""The channel ledger keeps what was said and never a credential.

Covers ``ChannelDataPlaneService`` masking of inbound and outbound text with the harness redactor, which the ledger,
the group context buffer and the evidence playback share. A case lists the part of a secret that must not survive:
the redactor may keep a short head and tail of a long value, but never its body.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.api import redact_sensitive_text

from app.channels.routing.channel_data_plane import ChannelDataPlaneService
from app.channels.types import InboundMessage

_PEM_BODY = "MIIEowIBAAKCAQEAu1SU1LfVLPHCozMxH2Mo4lgOEePzNm0tRgeLezV6ffAt0gun"

# (message text, the body of its secret that must never reach the ledger)
_LEAKING_SECRETS: tuple[tuple[str, str], ...] = (
    ("Here is the test key: sk-live-1234567890abcdef12345678", "1234567890abcdef"),
    ("use postgres://admin:S3cr3tPassw0rd@db.internal:5432/app for prod", "S3cr3tPassw0rd"),
    ("my key is AKIAIOSFODNN7EXAMPLE ok", "SFODNN7EXA"),
    ("token ghp_a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8", "B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6"),
    (f"-----BEGIN RSA PRIVATE KEY-----\n{_PEM_BODY}\n-----END RSA PRIVATE KEY-----", _PEM_BODY),
)
_SECRET_IDS = ("sk-key", "db-url-password", "aws-key-id", "github-token", "pem-block")


@pytest.mark.asyncio
@pytest.mark.parametrize(("text", "secret"), _LEAKING_SECRETS, ids=_SECRET_IDS)
async def test_record_inbound_masks_credentials(text: str, secret: str) -> None:
    msg = InboundMessage(
        channel="feishu",
        sender_id="user_x",
        sender_name="Bob",
        chat_id="chat_secret",
        content=text,
        message_id="msg_redact_test",
    )

    with patch("app.channels.routing.channel_data_plane.get_session") as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = AsyncMock()

        entry = await ChannelDataPlaneService.record_inbound(msg, is_trigger=True)

    assert entry is not None
    assert entry.is_trigger is True
    assert entry.is_self is False
    assert secret not in entry.content


@pytest.mark.asyncio
async def test_record_inbound_keeps_ordinary_text_verbatim() -> None:
    """Words that merely look like credential names are not credentials; observed context must stay readable."""
    text = "the key point: 42, auth: pending, token budget is fine"
    msg = InboundMessage(channel="feishu", sender_id="user_x", chat_id="chat_plain", content=text)

    with patch("app.channels.routing.channel_data_plane.get_session") as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = AsyncMock()

        entry = await ChannelDataPlaneService.record_inbound(msg, is_trigger=False)

    assert entry is not None
    assert entry.content == text


@pytest.mark.asyncio
async def test_record_outbound_masks_credentials() -> None:
    text, secret = _LEAKING_SECRETS[3]
    with patch("app.channels.routing.channel_data_plane.get_session") as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = AsyncMock()

        entry = await ChannelDataPlaneService.record_outbound(channel="slack", chat_id="group_1", content=text)

    assert entry is not None
    assert secret not in entry.content


@pytest.mark.parametrize(("text", "secret"), _LEAKING_SECRETS, ids=_SECRET_IDS)
def test_masking_a_stored_row_again_changes_nothing(text: str, secret: str) -> None:
    """The evidence playback masks ledger text a second time, so the redactor must be stable on its own output."""
    once = redact_sensitive_text(text)

    assert secret not in once
    assert redact_sensitive_text(once) == once
