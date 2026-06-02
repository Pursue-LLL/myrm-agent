"""Tests for competitor secret import with provider seeding."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.migration.competitor_secrets_importer import import_competitor_secrets


@pytest.mark.asyncio
async def test_import_secrets_seeds_providers_when_list_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / ".hermes"
    root.mkdir()
    (root / ".env").write_text("OPENAI_API_KEY=sk-test\n", encoding="utf-8")

    monkeypatch.setattr(
        "app.services.migration.competitor_secrets_importer.is_local_mode",
        lambda: True,
    )

    stored: dict[str, object] = {}

    async def fake_get(key: str) -> MagicMock | None:
        assert key == "providers"
        return None

    async def fake_set(
        key: str,
        value: dict[str, object],
        *,
        device_id: str,
        expected_version: int | None,
    ) -> None:
        assert key == "providers"
        assert device_id == "competitor-migration"
        stored["value"] = value

    monkeypatch.setattr(
        "app.services.migration.competitor_secrets_importer.config_service.get",
        fake_get,
    )
    monkeypatch.setattr(
        "app.services.migration.competitor_secrets_importer.config_service.set",
        fake_set,
    )

    result = await import_competitor_secrets(root)
    assert result["imported_keys"] == ["OPENAI_API_KEY"]
    providers = stored["value"]["providers"]
    assert isinstance(providers, list)
    assert len(providers) == 1
    assert providers[0]["id"] == "openai"
