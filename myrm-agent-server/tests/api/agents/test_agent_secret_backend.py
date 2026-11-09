"""Tests for the agent secret backend factory and its vault-locked mapping."""

import asyncio

import pytest
from fastapi import HTTPException

from app.api.agents import agent_extras
from app.core.security.master_key import VaultLockedError, VaultState


def test_secret_backend_passes_the_master_key(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()

    async def key(grace_sec: float = 0) -> str:
        return "master-key"

    monkeypatch.setattr(agent_extras.MasterKeyProvider, "ensure_master_key", key)
    monkeypatch.setattr(agent_extras, "DatabaseSecretBackend", lambda master_key: sentinel)

    assert asyncio.run(agent_extras._secret_backend()) is sentinel


def test_secret_backend_maps_a_locked_vault_to_423(monkeypatch: pytest.MonkeyPatch) -> None:
    async def locked(grace_sec: float = 0) -> str:
        raise VaultLockedError("vault locked", state=VaultState.LOCKED)

    monkeypatch.setattr(agent_extras.MasterKeyProvider, "ensure_master_key", locked)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(agent_extras._secret_backend())

    assert exc.value.status_code == 423
    assert exc.value.detail == "vault locked"
