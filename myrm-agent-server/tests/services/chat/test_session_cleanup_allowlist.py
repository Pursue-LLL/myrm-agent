"""Tests ensuring chat session cleanup purges session allowlist grants and resets denial counters.

Guarantees zero privilege permanence across focus_flush_session, permanent delete,
and trash cleanup without leaking session-scoped entries in memory.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.approval.helpers import (
    _get_state,
    record_denial,
)
from myrm_agent_harness.agent.security.approval_flow import (
    AllowlistEntry,
    get_allowlist,
)

from app.services.chat.chat_crud import _ChatCrudMixin


@pytest.mark.asyncio
async def test_cleanup_checkpointer_purges_session_allowlist_and_denial_counter() -> None:
    """_cleanup_checkpointer must purge session-scoped allowlist grants and reset denial counters."""
    user_id = "sandbox"
    target_chat = "chat_test_purge_101"
    other_chat = "chat_test_preserve_202"

    al = get_allowlist()

    # 1. Add session-scoped entries for target and other chat
    entry_target = AllowlistEntry(
        permission="shell_exec",
        tool_name="bash_test",
        session_id=target_chat,
    )
    entry_other = AllowlistEntry(
        permission="shell_exec",
        tool_name="bash_test",
        session_id=other_chat,
    )
    await al.add(user_id, entry_target)
    await al.add(user_id, entry_other)

    # 2. Record denials for target chat
    record_denial("bash_test", session_key=target_chat)
    record_denial("bash_test", session_key=target_chat)
    assert _get_state(target_chat).consecutive == 2
    assert _get_state(target_chat).total == 2

    # Verify both are initially granted
    assert al.check(user_id, "shell_exec", "bash_test", session_id=target_chat) is True
    assert al.check(user_id, "shell_exec", "bash_test", session_id=other_chat) is True

    # 3. Execute cleanup for target chat
    mock_cp = AsyncMock()
    mock_cp.adelete_thread = AsyncMock()

    with patch("app.platform_utils.get_checkpointer", return_value=mock_cp):
        await _ChatCrudMixin._cleanup_checkpointer(target_chat)

    # 4. Verify target chat grants are purged, other chat remains intact
    assert al.check(user_id, "shell_exec", "bash_test", session_id=target_chat) is False
    assert al.check(user_id, "shell_exec", "bash_test", session_id=other_chat) is True

    # 5. Verify denial counter for target chat is reset to 0
    assert _get_state(target_chat).consecutive == 0
    assert _get_state(target_chat).total == 0

    # Cleanup other chat
    await al.clear_session(user_id, other_chat)
