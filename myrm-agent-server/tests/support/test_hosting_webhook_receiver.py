"""The receiver records what the real webhook provider uploads, so the hosting e2e tests assert on what a platform would get."""

from __future__ import annotations

import pytest

from app.services.hosting.packager import PublishFile
from app.services.hosting.providers.http_webhook import HttpWebhookProvider
from app.services.hosting.types import HostingTarget
from tests.support.hosting_webhook_receiver import PAGE_HOST, WebhookReceiver


@pytest.mark.asyncio
async def test_the_receiver_records_the_fields_and_files_the_webhook_provider_posts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.hosting.providers.http_webhook.validate_webhook_url", lambda url, *, allow_http=False: url.strip()
    )
    with WebhookReceiver() as receiver:
        target = HostingTarget("tgt", "Site", "http_webhook", {"webhook_url": receiver.url, "allow_http": "true"})
        result = await HttpWebhookProvider().publish(
            target=target,
            credentials={},
            artifact_id="file_1",
            artifact_name="index.html",
            files={"index.html": PublishFile("index.html", "<h1>Hi</h1>"), "style.css": PublishFile("style.css", "h1 {}")},
            existing_project_ref=None,
        )

    assert result.url == f"{PAGE_HOST}/file_1"
    (upload,) = receiver.uploads
    assert upload.fields["artifact_id"] == "file_1"
    assert upload.files == {"index.html": "<h1>Hi</h1>", "style.css": "h1 {}"}
