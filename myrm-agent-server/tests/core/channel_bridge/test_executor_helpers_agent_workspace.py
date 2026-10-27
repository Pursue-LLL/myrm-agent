"""One answer to "which directory can a channel agent read back?"."""

from __future__ import annotations

import logging
from uuid import uuid4

import pytest

from app.core.channel_bridge.executor_helpers.agent_workspace import agent_workspace
from app.services.agent.params.workspace_resolve import default_chat_workspace_path


def test_the_workspace_is_the_chats_jit_directory() -> None:
    chat_id = str(uuid4())

    assert agent_workspace(chat_id) == default_chat_workspace_path(chat_id)


@pytest.mark.parametrize("chat_id", ["../escape", "a/b", "..", "x\\y"])
def test_an_id_that_cannot_name_a_directory_has_no_workspace(chat_id: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="app.core.channel_bridge.executor_helpers.agent_workspace"):
        assert agent_workspace(chat_id) is None

    assert "cannot name a workspace directory" in caplog.text
