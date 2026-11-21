"""Share events: one log line per link created and per entry opened, naming a link only by its short token id."""

from __future__ import annotations

import logging

import pytest

from app.core.security.share.share_hmac import token_log_id
from app.core.security.share.share_links import ShareKind
from app.core.security.share.share_status_page import ShareLinkState
from app.services.artifacts.share.share_token import create_artifact_share_token
from app.services.audit.share_events import ShareDenial, ShareSource, report_share_access, report_share_created

_LOGGER = "app.services.audit.share_events"


@pytest.fixture
def token() -> str:
    return create_artifact_share_token("artifact-1", "version-1", ttl_seconds=3600)[0]


def _lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == _LOGGER]


@pytest.mark.parametrize(
    ("kind", "source", "expected"),
    [
        (ShareKind.ARTIFACT, ShareSource.DIALOG, "kind=artifact-share source=dialog"),
        (ShareKind.CHAT, ShareSource.DIALOG, "kind=chat-share source=dialog"),
        (ShareKind.ARTIFACT, ShareSource.IM, "kind=artifact-share source=im"),
    ],
)
def test_a_created_link_is_one_line_naming_kind_and_source(
    caplog: pytest.LogCaptureFixture, token: str, kind: ShareKind, source: ShareSource, expected: str
) -> None:
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        report_share_created(kind, source, token)

    assert _lines(caplog) == [f"share_created {expected} token={token_log_id(token)}"]


def test_an_opened_link_is_one_granted_line(caplog: pytest.LogCaptureFixture, token: str) -> None:
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        report_share_access(ShareKind.CHAT, token)

    assert _lines(caplog) == [f"share_access kind=chat-share result=granted token={token_log_id(token)}"]


@pytest.mark.parametrize(
    ("denied", "reason"),
    [
        (ShareLinkState.REVOKED, "revoked"),
        (ShareLinkState.EXPIRED, "expired"),
        (ShareLinkState.CONTENT_UNAVAILABLE, "content_unavailable"),
        (ShareLinkState.FILE_UNAVAILABLE, "file_unavailable"),
        (ShareLinkState.CONVERSATION_UNAVAILABLE, "conversation_unavailable"),
        ("wrong_password", "wrong_password"),
    ],
)
def test_a_refused_link_is_one_denied_line_with_the_reason(
    caplog: pytest.LogCaptureFixture, token: str, denied: ShareDenial, reason: str
) -> None:
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        report_share_access(ShareKind.ARTIFACT, token, denied=denied)

    assert _lines(caplog) == [f"share_access kind=artifact-share result=denied reason={reason} token={token_log_id(token)}"]


def test_a_link_is_named_by_its_short_id_never_by_the_token(caplog: pytest.LogCaptureFixture, token: str) -> None:
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        report_share_created(ShareKind.ARTIFACT, ShareSource.IM, token)
        report_share_access(ShareKind.ARTIFACT, token)
        report_share_access(ShareKind.ARTIFACT, token, denied=ShareLinkState.REVOKED)

    assert len(_lines(caplog)) == 3
    assert token not in caplog.text
    assert token.split(".")[0] not in caplog.text


@pytest.mark.parametrize("scanned", ["", "not-a-token", "a.b", "../../etc/passwd"])
def test_a_refusal_of_text_that_is_not_one_of_our_tokens_is_not_logged(caplog: pytest.LogCaptureFixture, scanned: str) -> None:
    with caplog.at_level(logging.INFO, logger=_LOGGER):
        report_share_access(ShareKind.ARTIFACT, scanned, denied=ShareLinkState.EXPIRED)

    assert _lines(caplog) == []
