"""The meeting-notes distillation call is covered by the persisted privacy settings."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from myrm_agent_harness.agent.middlewares.security.outbound_privacy_guard import set_process_privacy_policy
from myrm_agent_harness.toolkits.llms.adapters.chat_model.outbound_guard import set_outbound_message_guard

from app.core.security.privacy_policy_sync import sync_privacy_policy
from app.services.meeting_notes.service import distill_meeting_notes
from tests.support.privacy_wire import wire_llm

_PHONE = "13812345678"
_TRANSCRIPT = f"[00:12] 张三：会后请打我电话 {_PHONE}，邮箱 zhang@example.com，把预算表发我。"


@pytest.fixture(autouse=True)
def _clean_process_policy() -> Iterator[None]:
    set_process_privacy_policy(None)
    set_outbound_message_guard(None)
    yield
    set_process_privacy_policy(None)
    set_outbound_message_guard(None)


@pytest.mark.asyncio
@pytest.mark.parametrize(("settings", "leaks"), [({"privacyEnabled": True, "privacyS2Action": "redact"}, False), ({}, True)])
async def test_distillation_prompt_follows_the_published_settings(settings: dict[str, object], leaks: bool) -> None:
    sync_privacy_policy(settings)
    llm, sent = wire_llm('{"title": "预算会", "summary": "确认预算"}')

    await distill_meeting_notes(_TRANSCRIPT, llm)

    assert (_PHONE in "\n".join(sent)) is leaks
