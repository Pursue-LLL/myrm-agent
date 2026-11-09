"""Tests for the local vault unlock endpoint."""

import asyncio
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.security import vault
from app.core.security.master_key import MasterKeyProvider


def test_empty_password_is_rejected() -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(vault.unlock_vault(vault.VaultUnlockRequest(password="")))

    assert exc.value.status_code == 400


def test_unlock_returns_success() -> None:
    with patch.object(MasterKeyProvider, "unlock_vault", return_value="derived-key"):
        response = asyncio.run(vault.unlock_vault(vault.VaultUnlockRequest(password="secret")))

    assert response.status == "success"
    assert response.message


def test_unlock_failure_maps_to_500() -> None:
    with patch.object(MasterKeyProvider, "unlock_vault", side_effect=RuntimeError("kdf failed")):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(vault.unlock_vault(vault.VaultUnlockRequest(password="secret")))

    assert exc.value.status_code == 500
