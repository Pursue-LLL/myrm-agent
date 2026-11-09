"""Error-path tests for the vault credential routes and their 423 mapping."""

import asyncio

import pytest
from fastapi import HTTPException

from app.api.security import vault_credentials
from app.api.security.vault_errors import vault_locked_error
from app.core.security.master_key import VaultLockedError, VaultState


class _BrokenService:
    async def list_credentials(self) -> object:
        raise RuntimeError("db down")

    async def get_credential(self, label: str) -> object:
        raise RuntimeError("db down")

    async def save_credential(self, **kwargs: object) -> object:
        raise RuntimeError("db down")

    async def delete_credential(self, label: str) -> object:
        raise RuntimeError("db down")


def test_vault_locked_error_uses_423() -> None:
    exc = vault_locked_error(VaultLockedError("locked", state=VaultState.LOCKED))

    assert isinstance(exc, HTTPException)
    assert exc.status_code == 423
    assert exc.detail == "locked"


def test_service_builder_maps_locked_vault_to_423(monkeypatch: pytest.MonkeyPatch) -> None:
    async def locked(grace_sec: float = 2.0) -> str:
        raise VaultLockedError("still resolving", state=VaultState.RESOLVING)

    monkeypatch.setattr("app.core.security.master_key.MasterKeyProvider.ensure_master_key", locked)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(vault_credentials._vault_service())

    assert exc.value.status_code == 423


def test_list_propagates_a_locked_vault_as_423(monkeypatch: pytest.MonkeyPatch) -> None:
    async def locked() -> _BrokenService:
        raise HTTPException(status_code=423, detail="vault locked")

    monkeypatch.setattr(vault_credentials, "_vault_service", locked)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(vault_credentials.list_credentials())

    assert exc.value.status_code == 423


def test_list_maps_backend_failure_to_500(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken() -> _BrokenService:
        return _BrokenService()

    monkeypatch.setattr(vault_credentials, "_vault_service", broken)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(vault_credentials.list_credentials())

    assert exc.value.status_code == 500


def test_create_maps_backend_failure_to_500(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken() -> _BrokenService:
        return _BrokenService()

    monkeypatch.setattr(vault_credentials, "_vault_service", broken)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(vault_credentials.create_credential(vault_credentials.VaultCredentialCreate(label="x", password="y")))

    assert exc.value.status_code == 500


def test_update_maps_backend_failure_to_500(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken() -> _BrokenService:
        return _BrokenService()

    monkeypatch.setattr(vault_credentials, "_vault_service", broken)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(vault_credentials.update_credential("x", vault_credentials.VaultCredentialUpdate(password="y")))

    assert exc.value.status_code == 500


def test_delete_maps_backend_failure_to_500(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken() -> _BrokenService:
        return _BrokenService()

    monkeypatch.setattr(vault_credentials, "_vault_service", broken)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(vault_credentials.delete_credential("x"))

    assert exc.value.status_code == 500
