"""Builders shared by the Slack channel tests: a configured channel and Slack Web API responses.

[INPUT]
- app.channels.providers.slack::SlackChannel (POS: Slack channel under test)

[OUTPUT]
- make_channel: a ``SlackChannel`` with bot and team ids set
- ok_json / err_json: Slack Web API response bodies (``ok: true`` / ``ok: false`` with an error code)

[POS]
Test support for the Slack provider test modules.
"""

from __future__ import annotations

import httpx

from app.channels.providers.slack import SlackChannel


def make_channel() -> SlackChannel:
    ch = SlackChannel(bot_token="xoxb-test", app_token="xapp-test")
    ch._bot_user_id = "U_BOT"
    ch._team_id = "T_TEAM"
    return ch


def ok_json(extra: dict[str, object] | None = None) -> httpx.Response:
    body: dict[str, object] = {"ok": True}
    if extra:
        body.update(extra)
    return httpx.Response(200, json=body)


def err_json(error: str = "some_error", headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(200, json={"ok": False, "error": error}, headers=headers or {})
