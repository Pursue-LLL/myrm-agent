"""Tests for competitor provider readiness helper used in dry-run lanes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.migration.source_secrets_importer import external_source_providers_configured


@pytest.mark.asyncio()
async def test_source_providers_configured_false_when_record_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.services.migration.source_secrets_importer.config_service.get",
        AsyncMock(return_value=None),
    )
    assert await external_source_providers_configured() is False


@pytest.mark.asyncio()
async def test_source_providers_configured_true_when_provider_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = MagicMock()
    record.value = {"providers": [{"id": "openai", "apiKeys": []}]}
    monkeypatch.setattr(
        "app.services.migration.source_secrets_importer.config_service.get",
        AsyncMock(return_value=record),
    )
    assert await external_source_providers_configured() is True
