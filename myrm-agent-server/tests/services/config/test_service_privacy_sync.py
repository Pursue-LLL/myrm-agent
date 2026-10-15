"""Saving or removing the personal settings re-publishes the privacy policy, whichever path wrote them."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.security.outbound_privacy_guard import (
    resolve_privacy_policy,
    set_process_privacy_policy,
)
from myrm_agent_harness.toolkits.llms.adapters.chat_model.outbound_guard import set_outbound_message_guard
from sqlalchemy.engine import CursorResult

from app.services.config.service import config_service


@pytest.fixture(autouse=True)
def _clean_process_policy() -> Iterator[None]:
    set_process_privacy_policy(None)
    set_outbound_message_guard(None)
    yield
    set_process_privacy_policy(None)
    set_outbound_message_guard(None)


def _session_factory(existing: MagicMock | None) -> MagicMock:
    session = AsyncMock()
    result = MagicMock(spec=CursorResult)
    result.scalar_one_or_none.return_value = existing
    result.rowcount = 1
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory


def _existing() -> MagicMock:
    existing = MagicMock()
    existing.version = "1000_0"
    existing.config_value = {}
    existing.is_encrypted = False
    return existing


async def _save(key: str, value: dict[str, object], existing: MagicMock | None) -> None:
    with (
        patch("app.services.config.service.get_session_factory", return_value=_session_factory(existing)),
        patch("app.services.config.service._build_config_record", return_value=MagicMock()),
    ):
        await config_service.set(config_key=key, value=value, device_id="device-a")


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [_existing, lambda: None], ids=["update", "create"])
async def test_saving_personal_settings_publishes_the_policy(existing: object) -> None:
    await _save("personalSettings", {"privacyEnabled": True, "privacyS2Action": "redact"}, existing())  # type: ignore[operator]

    assert resolve_privacy_policy().enabled is True


@pytest.mark.asyncio
async def test_saving_settings_with_privacy_off_clears_the_policy() -> None:
    await _save("personalSettings", {"privacyEnabled": True}, _existing())
    await _save("personalSettings", {"privacyEnabled": False}, _existing())

    assert resolve_privacy_policy().enabled is False


@pytest.mark.asyncio
async def test_saving_another_config_leaves_the_policy_alone() -> None:
    await _save("personalSettings", {"privacyEnabled": True}, _existing())
    await _save("providers", {"providers": []}, _existing())

    assert resolve_privacy_policy().enabled is True


@pytest.mark.asyncio
async def test_deleting_personal_settings_clears_the_policy() -> None:
    await _save("personalSettings", {"privacyEnabled": True}, _existing())

    with patch("app.services.config.service.get_session_factory", return_value=_session_factory(_existing())):
        assert await config_service.delete("personalSettings") is True

    assert resolve_privacy_policy().enabled is False
