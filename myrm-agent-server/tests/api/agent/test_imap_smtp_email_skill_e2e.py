"""The agent reads a mail on a real IMAP/SMTP server through the imap-smtp-email skill and answers it (Lane-C).

A real model, the whole agent-stream path with the skill staged by the seed sync and added to the agent's profile, its
credentials injected the way the settings page stores them, the script run by the agent's own bash tool, and GreenMail as the mail server. Nothing on the
path is faked: the model has to find the skill, run the right commands and report what the mailbox really holds.

[INPUT]
- POST /api/v1/agents/agent-stream with the LITE model of ``.env.test`` (POS: the whole server path, a real provider call)
- tests/support/greenmail_mailbox.py: the real mail server, its trust bundle and the mailbox readers
- The user skill config (POS: what the skill settings page saves: enabled skills and the skill's environment variables)
- POST /api/agents (POS: the agent profile whose skills decide what the agent can use)
- POST /skills/{id}/enable and /permissions/grant (POS: the skills page: enabling asks for the permissions the skill declares)

[OUTPUT]
- Fails when the agent does not run the skill's script, does not report the subject and the figure of the mail it found,
  sends no reply, sends more than one, sends one that is not threaded on the mail it answers, that has no Date, or that
  has a Message-ID that is not on the sender's domain.

[POS]
Lane-C test of the prebuilt skill ``imap-smtp-email``; the unit tests next to it pin the script's commands against doubles,
this one pins that a model can use them against a server it does not control. The password is a password-named setting:
it reaches the skill's commands (and only those) as a per-command credential, so a run that cannot log in fails here.
"""

from __future__ import annotations

import email.message
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills import router as skills_router
from app.core.skills import prebuilt_sync
from app.core.skills.store.service import skills_service
from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection
from tests.support.greenmail_mailbox import SMTP_TLS_HOST_PORT, Mailbox, deliver, messages_of, running_mailbox
from tests.support.minimal_app import API_PREFIX
from tests.support.real_model_workspace_turns import new_chat, perform_agent_stream

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(480, method="thread")]

_SKILL_ID = "imap-smtp-email"
_PASSWORD_ENV = "EMAIL_IMAP_PASSWORD"
_SENDER_DOMAIN = "mail.example.test"
_SUBJECT_TOKEN = "QX-4471"
_FIGURE_TOKEN = "FIG-90817"
_REPLY_TOKEN = "ZEBRA-7731"
_PROMPT = (
    "Use the imap-smtp-email skill on my mailbox. Find the newest message from bob@localhost, tell me its exact subject "
    "and the Q3 figure written in its body, then reply to that message with the body "
    f"'Received, thanks - {_REPLY_TOKEN}'. Run the commands yourself and do not ask me anything."
)


@pytest.fixture
def skills_page(app: FastAPI) -> None:
    """The routes behind the skills page, which the app of the agent tests does not mount."""
    app.include_router(skills_router, prefix=f"{API_PREFIX}/skills")


def _enable_skill(client: TestClient) -> None:
    """What the user does on the skills page: enabling asks for the permissions the skill declares, then switches it on once granted."""
    api = f"{API_PREFIX}/skills/{_SKILL_ID}"
    asked = client.post(f"{api}/enable").json()
    assert asked["pending_approval"] is True and not asked["enabled"], f"enabling did not ask for permissions: {asked}"
    granted = client.post(f"{api}/permissions/grant", json={"permissions": asked["required_permissions"]})
    assert granted.status_code == 200, granted.text
    enabled = client.post(f"{api}/enable").json()
    assert enabled["enabled"] is True, f"the skill is still off after the grant: {enabled}"


async def _install_skill(client: TestClient, mailbox: Mailbox, monkeypatch: pytest.MonkeyPatch) -> None:
    """What the user does before asking: the skill is installed and enabled, and its settings hold the mailbox login."""
    monkeypatch.setattr(prebuilt_sync, "_synced", False)
    synced = await prebuilt_sync.sync_prebuilt_seeds(skills_service.storage)
    await skills_service.user_config.ensure_prebuilt_enabled_after_sync(list(synced.skill_ids))
    _enable_skill(client)
    config = await skills_service.user_config.get_config()
    config.skill_env_vars[_SKILL_ID] = {
        "EMAIL_IMAP_HOST": mailbox.host,
        "EMAIL_IMAP_PORT": str(mailbox.imap_port),
        "EMAIL_IMAP_USER": "alice@localhost",
        _PASSWORD_ENV: "pw",
        "EMAIL_SMTP_HOST": mailbox.host,
        "EMAIL_SMTP_PORT": str(SMTP_TLS_HOST_PORT),
        "EMAIL_FROM_ADDRESS": f"Alice <alice@{_SENDER_DOMAIN}>",
    }
    await skills_service.user_config.save_config(config)


def _create_agent(client: TestClient) -> str:
    """A skill reaches an agent only through the skills of its profile, so the user adds it there."""
    created = client.post("/api/agents", json={"name": "Mailbox assistant", "skill_ids": [_SKILL_ID]})
    assert created.status_code == 200, created.text
    agent_id = created.json()["data"]["id"]
    assert isinstance(agent_id, str)
    return agent_id


def _incoming() -> email.message.EmailMessage:
    message = email.message.EmailMessage()
    message["From"] = "Bob Builder <bob@localhost>"
    message["To"] = "alice@localhost"
    message["Subject"] = f"Quarterly numbers {_SUBJECT_TOKEN}"
    message["Message-ID"] = "<incoming-4471@localhost>"
    message.set_content(f"Hi Alice,\nthe Q3 figure is {_FIGURE_TOKEN}.\n")
    return message


@pytest.mark.usefixtures("skills_page")
async def test_the_agent_reads_and_answers_a_mail_on_a_real_server(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with running_mailbox(tmp_path) as mailbox:
        monkeypatch.setenv("SSL_CERT_FILE", str(mailbox.ca_bundle))
        await _install_skill(client, mailbox, monkeypatch)
        deliver(mailbox, _incoming())

        _, collected, tool_calls = perform_agent_stream(
            client, _PROMPT, new_chat(client), model_selection=get_lite_model_selection(), agent_id=_create_agent(client)
        )

        check_e2e_errors(collected)
        said = "".join(str(event.get("data", "")) for event in collected if event.get("type") == "message").upper()
        replies = messages_of(mailbox, "bob@localhost")

    assert tool_calls >= 2, f"the agent ran {tool_calls} tool calls; it has to list the inbox and send the reply at least"
    assert _SUBJECT_TOKEN in said and _FIGURE_TOKEN in said, f"the answer does not carry what the mailbox holds: {said[:400]}"
    assert len(replies) == 1, f"bob received {len(replies)} messages, expected the one reply"
    reply = replies[0]
    body = reply.get_body(preferencelist=("plain",))
    assert body is not None and _REPLY_TOKEN in body.get_content()
    assert reply["Subject"] == f"Re: Quarterly numbers {_SUBJECT_TOKEN}"
    assert reply["In-Reply-To"] == "<incoming-4471@localhost>"
    assert reply["Date"], "a reply with no Date header"
    assert str(reply["Message-ID"]).endswith(f"@{_SENDER_DOMAIN}>"), "the Message-ID is not on the sender's domain"
