"""What the share log records of an artifact link's life: created from the dialog, entry served, then refused."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest

from app.core.security.share.share_hmac import token_log_id
from app.core.security.share.share_unlock import unlock_cookie_name
from app.services.hosting.packager import PublishFile

pytestmark = pytest.mark.usefixtures("chats_share_workspace")

_EVENTS_LOGGER = "app.services.audit.share_events"
_FILES = {"index.html": PublishFile(path="index.html", content="<html></html>", encoding="utf-8")}


def _create(share_client, html_artifact, **options: object) -> str:
    with patch(
        "app.services.artifacts.share.share_bundle.resolve_artifact_deploy_files",
        new_callable=AsyncMock,
        return_value=(html_artifact, _FILES),
    ):
        response = share_client.post(
            f"/{html_artifact.id}/share-preview",
            json={"ttl_days": 7, "artifact_type": "html", **options},
        )
    assert response.status_code == 200
    return response.json()["token"]


def _share_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.name == _EVENTS_LOGGER]


@pytest.mark.asyncio
async def test_the_share_log_records_each_step_of_a_links_life(share_client, html_artifact, caplog) -> None:
    with caplog.at_level(logging.INFO, logger=_EVENTS_LOGGER):
        token = _create(share_client, html_artifact)
        assert share_client.get(f"/public/artifact-share/{token}", follow_redirects=False).status_code == 200
        record_id = share_client.get("/shares").json()[0]["id"]
        assert share_client.delete(f"/shares/{record_id}").status_code == 204
        assert share_client.get(f"/public/artifact-share/{token}", follow_redirects=False).status_code == 404

    link = token_log_id(token)
    assert _share_lines(caplog) == [
        f"share_created kind=artifact-share source=dialog token={link}",
        f"share_access kind=artifact-share result=granted token={link}",
        f"share_access kind=artifact-share result=denied reason=revoked token={link}",
    ]


@pytest.mark.asyncio
async def test_each_wrong_password_is_logged_as_denied_and_the_unlocked_page_once_as_granted(
    share_client, html_artifact, caplog
) -> None:
    token = _create(share_client, html_artifact, password="s3cret")
    cookie_name = unlock_cookie_name("artifact_share_unlock", token)
    with caplog.at_level(logging.INFO, logger=_EVENTS_LOGGER):
        for guess in ("wrong", "also-wrong"):
            share_client.post(f"/public/artifact-share/{token}", data={"p": guess})
        unlocked = share_client.post(f"/public/artifact-share/{token}", data={"p": "s3cret"}, follow_redirects=False)
        assert unlocked.status_code == 303
        # The cookie path is the production /api/v1/... prefix while the test router mounts under /public/artifact-share.
        share_client.get(
            f"/public/artifact-share/{token}",
            headers={"Cookie": f"{cookie_name}={share_client.cookies.get(cookie_name)}"},
            follow_redirects=False,
        )

    link = token_log_id(token)
    assert _share_lines(caplog) == [
        f"share_access kind=artifact-share result=denied reason=wrong_password token={link}",
        f"share_access kind=artifact-share result=denied reason=wrong_password token={link}",
        f"share_access kind=artifact-share result=granted token={link}",
    ]


@pytest.mark.asyncio
async def test_a_link_that_is_not_one_of_ours_leaves_no_share_line(share_client, caplog) -> None:
    with caplog.at_level(logging.INFO, logger=_EVENTS_LOGGER):
        assert share_client.get("/public/artifact-share/not-a-share-token", follow_redirects=False).status_code == 404

    assert _share_lines(caplog) == []
