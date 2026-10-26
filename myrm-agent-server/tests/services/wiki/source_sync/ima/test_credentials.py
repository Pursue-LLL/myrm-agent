"""Credential storage: write-only through the dedicated API, encrypted by the config service, never a public config key."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import get_args

import pytest

from app.schemas.config import ConfigKey
from app.services.config.encryption import is_sensitive_config
from app.services.wiki.source_sync.ima import credentials as credentials_module
from app.services.wiki.source_sync.ima.credentials import (
    CREDENTIALS_KEY,
    clear_credentials,
    load_credentials,
    mask_client_id,
    save_credentials,
)
from app.services.wiki.source_sync.ima.models import ImaCredentials


@dataclass
class FakeConfigService:
    store: dict[str, dict[str, object]] = field(default_factory=dict)

    async def get(self, key: str) -> SimpleNamespace | None:
        return SimpleNamespace(value=self.store[key]) if key in self.store else None

    async def set(self, key: str, value: dict[str, object], device_id: str) -> None:
        self.store[key] = value

    async def delete(self, key: str) -> bool:
        return self.store.pop(key, None) is not None


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch) -> FakeConfigService:
    fake = FakeConfigService()
    monkeypatch.setattr(credentials_module, "config_service", fake)
    return fake


def test_credentials_are_encrypted_at_rest_but_not_a_public_config_key() -> None:
    assert CREDENTIALS_KEY == "imaCredentials"
    assert is_sensitive_config(CREDENTIALS_KEY)
    assert CREDENTIALS_KEY not in get_args(ConfigKey)


async def test_round_trip_and_clear(config: FakeConfigService) -> None:
    assert await load_credentials() is None

    await save_credentials(ImaCredentials(client_id="cid", api_key="key"))
    assert await load_credentials() == ImaCredentials(client_id="cid", api_key="key")

    assert await clear_credentials() is True
    assert await load_credentials() is None


async def test_half_stored_credentials_count_as_not_connected(config: FakeConfigService) -> None:
    config.store[CREDENTIALS_KEY] = {"client_id": "cid", "api_key": " "}
    assert await load_credentials() is None


def test_client_id_is_masked_for_display() -> None:
    assert mask_client_id("abcdefghijkl") == "abcd…ijkl"
    assert mask_client_id("short") == "short"
