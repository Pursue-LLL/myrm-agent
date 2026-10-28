"""Tests for providers config key consolidation."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.config.key_consolidation import consolidate_split_providers_keys


def _record(value: dict[str, object], *, unreadable: bool = False) -> SimpleNamespace:
    return SimpleNamespace(value=value, unreadable=unreadable)


@pytest.mark.asyncio
async def test_consolidates_split_keys_into_providers() -> None:
    providers_record = _record({"providers": []})
    dmc_record = _record({"baseModel": {"model": "gpt-4"}})
    cmi_record = _record({"openai/gpt-4": {"displayName": "GPT-4"}})

    with patch("app.services.config.key_consolidation.config_service") as mock_service:
        mock_service.get = AsyncMock(side_effect=[providers_record, dmc_record, cmi_record])
        mock_service.set = AsyncMock()
        mock_service.delete = AsyncMock(return_value=True)

        stats = await consolidate_split_providers_keys()

    assert stats["merged"] == 1
    assert stats["deleted"] == 2
    mock_service.set.assert_awaited_once()
    set_payload = mock_service.set.await_args.kwargs["value"]
    assert "defaultModelConfig" in set_payload
    assert "customModelInfo" in set_payload


@pytest.mark.asyncio
async def test_skips_when_no_split_keys() -> None:
    with patch("app.services.config.key_consolidation.config_service") as mock_service:
        mock_service.get = AsyncMock(return_value=None)

        stats = await consolidate_split_providers_keys()

    assert stats["skipped"] == 1
    mock_service.set.assert_not_called()


@pytest.mark.asyncio
async def test_deletes_empty_split_key_without_merge() -> None:
    empty_record = _record({})
    providers_record = _record({"providers": []})

    with patch("app.services.config.key_consolidation.config_service") as mock_service:
        mock_service.get = AsyncMock(side_effect=[empty_record, None, providers_record])
        mock_service.set = AsyncMock()
        mock_service.delete = AsyncMock(return_value=True)

        stats = await consolidate_split_providers_keys()

    assert stats["merged"] == 0
    assert stats["deleted"] == 1
    mock_service.set.assert_not_called()


@pytest.mark.asyncio
async def test_noop_when_providers_already_contains_split_values() -> None:
    providers_record = _record({"defaultModelConfig": {"baseModel": {}}})
    dmc_record = _record({"baseModel": {}})

    with patch("app.services.config.key_consolidation.config_service") as mock_service:
        mock_service.get = AsyncMock(side_effect=[dmc_record, None, providers_record])
        mock_service.set = AsyncMock()
        mock_service.delete = AsyncMock(return_value=False)

        stats = await consolidate_split_providers_keys()

    assert stats["merged"] == 0
    assert stats["deleted"] == 0
    mock_service.set.assert_not_called()


@pytest.mark.asyncio
async def test_leaves_split_keys_alone_while_providers_cannot_be_read() -> None:
    dmc_record = _record({"baseModel": {"model": "gpt-4"}})
    unreadable_providers = _record({}, unreadable=True)

    with patch("app.services.config.key_consolidation.config_service") as mock_service:
        mock_service.get = AsyncMock(side_effect=[dmc_record, None, unreadable_providers])
        mock_service.set = AsyncMock()
        mock_service.delete = AsyncMock(return_value=True)

        stats = await consolidate_split_providers_keys()

    assert stats == {"merged": 0, "deleted": 0, "skipped": 1}
    mock_service.set.assert_not_called()
    mock_service.delete.assert_not_called()
