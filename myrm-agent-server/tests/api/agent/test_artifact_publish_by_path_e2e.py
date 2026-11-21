"""Real-model E2E: the model publishes a workspace file by its path and the platform receives the file as it is on disk.

[INPUT]
- POST /api/v1/agents/agent-stream with the BASIC model (POS: the whole server path, real provider calls, the real artifact_publish tool)
- tests.support.hosting_webhook_receiver (POS: the platform the user publishes to, on loopback)

[OUTPUT]
- test_a_page_written_in_one_turn_is_published_in_the_next: the path the model wrote is all it needs; the platform gets that file's bytes
- test_publishing_again_after_an_edit_updates_the_same_page: one file stays one artifact, and the republication carries the edit
- test_two_pages_with_the_same_file_name_each_publish_their_own_files: pages in two folders ship with their own stylesheet
- test_a_page_the_user_did_not_ask_to_publish_stays_unpublished: writing and editing a file never publishes it

[POS]
Server pytest-only, marker ``e2e`` (``-m e2e``). Proves what the unit tests cannot: that a model finds artifact_publish, passes the path it
wrote, and that the page the user is given is the page on disk.
"""

from __future__ import annotations

from collections.abc import Iterator
from importlib import import_module

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors
from tests.support.hosting_webhook_receiver import PAGE_HOST, WebhookReceiver
from tests.support.real_model_workspace_turns import harness_workspace, new_chat, perform_agent_stream
from tests.support.test_secrets import resolve_test_env

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.timeout(900),
    pytest.mark.skipif(not resolve_test_env("BASIC_API_KEY"), reason="E2E test requires BASIC_API_KEY environment variable"),
]

CREATE_PAGE = (
    "Create a tiny one-page website for a fictional bakery named Maple Crumb as the file bakery/index.html. "
    "Keep the file under 15 lines. Only create the file."
)
EDIT_TITLE = "Change the page title in bakery/index.html to 'Maple Crumb Bakery and Cafe' by editing the file."
PUBLISH_PAGE = "Now publish it to my hosting and give me the live link. Do not open the link."
CREATE_TWO_PAGES = (
    "Create two tiny one-page websites for fictional shops as two separate files: site-a/index.html for a bakery named "
    "Maple Crumb and site-b/index.html for a florist named Fern and Petal. Give each its own style.css next to it, "
    "linked from the page. Keep every file under 10 lines. Only create the files."
)
PUBLISH_TWO_PAGES = "Publish both pages to my hosting and give me the two live links. Do not open the links."


@pytest.fixture(autouse=True)
def _mock_upsert_processor_artifact() -> None:
    """Artifacts are registered for real here; the shared stand-in for the upsert is switched off."""


@pytest.fixture(autouse=True)
def approve_every_pending_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """A model that publishes two pages at once asks for two approvals; the helper's single decision would reject both as a count mismatch."""
    monkeypatch.setattr(
        "tests.support.real_model_workspace_turns.build_approval_resume_value", lambda **_: {"decision": "approve"}
    )


@pytest.fixture
def receiver(monkeypatch: pytest.MonkeyPatch) -> Iterator[WebhookReceiver]:
    # The SSRF guard refuses loopback webhooks; the platform of this test is the receiver on loopback.
    monkeypatch.setattr(
        "app.services.hosting.providers.http_webhook.validate_webhook_url", lambda url, *, allow_http=False: url.strip()
    )
    with WebhookReceiver() as running:
        yield running


@pytest.fixture
def publishing_client(app: FastAPI, client: TestClient, receiver: WebhookReceiver) -> TestClient:
    """A client whose user has the receiver as the default hosting target, as after adding a webhook in the settings."""
    app.include_router(import_module("app.api.files.hosting_api").router, prefix="/api/v1/files/artifacts")
    created = client.post(
        "/api/v1/files/artifacts/hosting/targets",
        json={
            "name": "My site",
            "provider_type": "http_webhook",
            "config": {"webhook_url": receiver.url, "allow_http": "true"},
            "is_default": True,
        },
    )
    assert created.status_code == 200, created.text
    return client


def _turn(client: TestClient, chat_id: str, prompt: str) -> str:
    answer, collected, _ = perform_agent_stream(client, prompt, chat_id)
    check_e2e_errors(collected)
    return answer


def _workspace_file(client: TestClient, chat_id: str, relative_path: str) -> str:
    assert client.portal is not None
    workspace = client.portal.call(harness_workspace, chat_id)
    return (workspace / relative_path).read_text(encoding="utf-8")


def test_a_page_written_in_one_turn_is_published_in_the_next(publishing_client: TestClient, receiver: WebhookReceiver) -> None:
    chat_id = new_chat(publishing_client)
    _turn(publishing_client, chat_id, CREATE_PAGE)

    answer = _turn(publishing_client, chat_id, PUBLISH_PAGE)

    assert receiver.uploads, "the model never published the page"
    assert receiver.uploads[-1].files["index.html"] == _workspace_file(publishing_client, chat_id, "bakery/index.html")
    assert PAGE_HOST in answer, "the user is not given the live link"


def test_publishing_again_after_an_edit_updates_the_same_page(publishing_client: TestClient, receiver: WebhookReceiver) -> None:
    chat_id = new_chat(publishing_client)
    _turn(publishing_client, chat_id, CREATE_PAGE)
    _turn(publishing_client, chat_id, PUBLISH_PAGE)

    _turn(
        publishing_client,
        chat_id,
        f"{EDIT_TITLE} Then publish it again to my hosting and give me the live link. Do not open the link.",
    )

    page = _workspace_file(publishing_client, chat_id, "bakery/index.html")
    assert "Maple Crumb Bakery and Cafe" in page
    assert len(receiver.uploads) >= 2
    assert receiver.uploads[-1].files["index.html"] == page, "the republication does not carry the edit"
    assert len({upload.fields["artifact_id"] for upload in receiver.uploads}) == 1, "one file must stay one artifact"


def test_two_pages_with_the_same_file_name_each_publish_their_own_files(
    publishing_client: TestClient, receiver: WebhookReceiver
) -> None:
    chat_id = new_chat(publishing_client)
    _turn(publishing_client, chat_id, CREATE_TWO_PAGES)

    _turn(publishing_client, chat_id, PUBLISH_TWO_PAGES)

    published = {upload.files["index.html"]: upload for upload in receiver.uploads}
    for folder in ("site-a", "site-b"):
        page = _workspace_file(publishing_client, chat_id, f"{folder}/index.html")
        assert page in published, f"{folder}/index.html was not published"
        assert published[page].files.get("style.css") == _workspace_file(publishing_client, chat_id, f"{folder}/style.css")


def test_a_page_the_user_did_not_ask_to_publish_stays_unpublished(
    publishing_client: TestClient, receiver: WebhookReceiver
) -> None:
    chat_id = new_chat(publishing_client)
    _turn(publishing_client, chat_id, CREATE_PAGE)

    _turn(publishing_client, chat_id, f"{EDIT_TITLE} Only edit the file.")

    assert receiver.uploads == []
