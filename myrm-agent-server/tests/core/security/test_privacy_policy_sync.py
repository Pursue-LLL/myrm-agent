"""The persisted privacy settings reach every model call of the process, not only the agent runs."""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage
from myrm_agent_harness.agent.middlewares.security.outbound_privacy_guard import (
    resolve_privacy_policy,
    set_process_privacy_policy,
)
from myrm_agent_harness.toolkits.llms.adapters.chat_model.outbound_guard import set_outbound_message_guard

from app.core.security.privacy_policy_sync import apply_privacy_policy_from_db, sync_privacy_policy
from tests.support.privacy_wire import wire_llm

_PHONE = "13812345678"
_TEXT = f"帮我给客户回电话，手机 {_PHONE}，邮箱 zhang@example.com"
_ON = {"privacyEnabled": True, "privacyS2Action": "redact"}


@pytest.fixture(autouse=True)
def _clean_process_policy() -> Iterator[None]:
    set_process_privacy_policy(None)
    set_outbound_message_guard(None)
    yield
    set_process_privacy_policy(None)
    set_outbound_message_guard(None)


async def _wire_text_for(text: str) -> str:
    model, sent = wire_llm()
    await model.ainvoke([HumanMessage(content=text)])
    return sent[-1]


class TestSyncPrivacyPolicy:
    @pytest.mark.asyncio
    async def test_enabled_settings_mask_a_model_call_that_has_no_agent_run(self) -> None:
        sync_privacy_policy(_ON)

        assert _PHONE not in await _wire_text_for(_TEXT)

    @pytest.mark.asyncio
    async def test_disabled_settings_send_the_text_unchanged(self) -> None:
        sync_privacy_policy({"privacyEnabled": False})

        assert _PHONE in await _wire_text_for(_TEXT)

    @pytest.mark.asyncio
    async def test_turning_protection_off_takes_effect_immediately(self) -> None:
        sync_privacy_policy(_ON)
        sync_privacy_policy({**_ON, "privacyEnabled": False})

        assert _PHONE in await _wire_text_for(_TEXT)

    def test_missing_settings_leave_no_policy(self) -> None:
        sync_privacy_policy(_ON)
        sync_privacy_policy(None)

        assert resolve_privacy_policy().enabled is False

    def test_custom_rules_saved_with_the_settings_are_part_of_the_published_policy(self) -> None:
        sync_privacy_policy({**_ON, "privacyCustomKeywordsS3": ["Project Falcon"], "privacyCustomPatternsS2": [r"EMP-\d{6}"]})

        policy = resolve_privacy_policy()
        assert policy.custom_keywords_s3 == ("Project Falcon",)
        assert policy.custom_patterns_s2 == (r"EMP-\d{6}",)


class TestApplyPrivacyPolicyFromDb:
    @pytest.mark.asyncio
    async def test_startup_loads_the_saved_settings(self) -> None:
        record = SimpleNamespace(value=_ON)
        with patch("app.services.config.service.config_service.get", new=AsyncMock(return_value=record)):
            await apply_privacy_policy_from_db()

        assert resolve_privacy_policy().enabled is True
        assert _PHONE not in await _wire_text_for(_TEXT)

    @pytest.mark.asyncio
    async def test_startup_without_saved_settings_leaves_privacy_off(self) -> None:
        with patch("app.services.config.service.config_service.get", new=AsyncMock(return_value=None)):
            await apply_privacy_policy_from_db()

        assert resolve_privacy_policy().enabled is False
