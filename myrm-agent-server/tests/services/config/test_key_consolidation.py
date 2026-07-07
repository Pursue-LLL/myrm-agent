"""Tests for providers config key consolidation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.config.key_consolidation import consolidate_split_providers_keys


@pytest.mark.asyncio
async def test_consolidates_split_keys_into_providers() -> None:
    providers_record = type("Record", (), {"value": {"providers": []}})()
    dmc_record = type("Record", (), {"value": {"baseModel": {"model": "gpt-4"}}})()
    cmi_record = type("Record", (), {"value": {"openai/gpt-4": {"displayName": "GPT-4"}}})()

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
    empty_record = type("Record", (), {"value": {}})()
    providers_record = type("Record", (), {"value": {"providers": []}})()

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
    providers_record = type("Record", (), {"value": {"defaultModelConfig": {"baseModel": {}}}})()
    dmc_record = type("Record", (), {"value": {"baseModel": {}}})()

    with patch("app.services.config.key_consolidation.config_service") as mock_service:
        mock_service.get = AsyncMock(side_effect=[dmc_record, None, providers_record])
        mock_service.set = AsyncMock()
        mock_service.delete = AsyncMock(return_value=False)

        stats = await consolidate_split_providers_keys()

    assert stats["merged"] == 0
    assert stats["deleted"] == 0
    mock_service.set.assert_not_called()
