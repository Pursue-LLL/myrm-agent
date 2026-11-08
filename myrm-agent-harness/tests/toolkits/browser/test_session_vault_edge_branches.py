"""SessionVault edge branches: oversized cache entry, save/list/cleanup failures and singleflight waiter recovery."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.browser.session_vault import SessionVault
from myrm_agent_harness.toolkits.browser.session_vault.backends import FileVaultBackend
from myrm_agent_harness.toolkits.browser.session_vault.exceptions import EncryptionError
from myrm_agent_harness.toolkits.browser.session_vault.types import (
    SessionEntry,
    SessionSummary,
    VaultMetrics,
)


@pytest.fixture
def vault_key() -> bytes:
    return os.urandom(32)


class TestSessionVaultEdgeBranches:
    async def test_cache_put_skips_oversized_entry(self, tmp_path: Path, vault_key: bytes) -> None:
        vault = SessionVault(FileVaultBackend(tmp_path), vault_key, cache_max_memory_mb=1)
        with patch.object(SessionVault, "_estimate_entry_size", return_value=10**7):
            await vault.save("big.com", {"cookies": [{"name": "x"}]})
        assert "big.com" not in vault._cache

    async def test_cache_put_updates_existing_entry(self, tmp_path: Path, vault_key: bytes) -> None:
        vault = SessionVault(FileVaultBackend(tmp_path), vault_key)
        await vault.save("example.com", {"cookies": [{"name": "a"}]})
        first_size = vault._cache["example.com"][2]
        await vault.save("example.com", {"cookies": [{"name": "a"}, {"name": "b"}]})
        assert vault._cache["example.com"][0].storage_state == {"cookies": [{"name": "a"}, {"name": "b"}]}
        assert vault._cache["example.com"][2] != first_size

    async def test_save_serialization_failure(self, tmp_path: Path, vault_key: bytes) -> None:
        vault = SessionVault(FileVaultBackend(tmp_path), vault_key)
        with pytest.raises(ValueError):
            await vault.save("example.com", {"unserializable": object()})

    async def test_save_backend_failure(self, tmp_path: Path, vault_key: bytes) -> None:
        backend = FileVaultBackend(tmp_path)
        vault = SessionVault(backend, vault_key)
        with (
            patch.object(backend, "write", side_effect=OSError("disk full")),
            pytest.raises(OSError),
        ):
            await vault.save("example.com", {"cookies": []})

    async def test_encrypt_failure(self, tmp_path: Path, vault_key: bytes) -> None:
        vault = SessionVault(FileVaultBackend(tmp_path), vault_key)
        with (
            patch.object(type(vault._get_cipher()), "encrypt", side_effect=Exception("cipher boom")),
            pytest.raises(EncryptionError),
        ):
            await vault.save("example.com", {"cookies": []})

    async def test_list_summaries_returns_metadata(self, tmp_path: Path, vault_key: bytes) -> None:
        backend = FileVaultBackend(tmp_path)
        vault = SessionVault(backend, vault_key)
        await vault.save(
            "example.com",
            {"cookies": [{"name": "sid"}], "origins": [{"localStorage": [["k", "v"]]}]},
        )
        summaries = await vault.list_summaries()
        assert len(summaries) == 1
        assert summaries[0].domain == "example.com"
        assert summaries[0].cookie_count == 1
        assert summaries[0].local_storage_count == 1

    async def test_list_summaries_skips_corrupted(self, tmp_path: Path, vault_key: bytes) -> None:
        backend = FileVaultBackend(tmp_path)
        vault = SessionVault(backend, vault_key)
        await vault.save("good.com", {"cookies": []})
        corrupt = tmp_path / "bad.com.enc"
        corrupt.write_bytes(b"\x00\x01not-encrypted")
        summaries = await vault.list_summaries()
        assert [s.domain for s in summaries] == ["good.com"]

    async def test_cleanup_expired_removed_count(self, tmp_path: Path, vault_key: bytes) -> None:
        backend = FileVaultBackend(tmp_path)
        vault = SessionVault(backend, vault_key)
        await vault.save("expired.com", {"cookies": []}, ttl_days=-1)
        await vault.save("alive.com", {"cookies": []}, ttl_days=30)
        removed = await vault.cleanup_expired()
        assert removed == 1
        assert "alive.com" in await backend.list_all()

    async def test_load_singleflight_waiter_recovers(self, tmp_path: Path, vault_key: bytes) -> None:
        vault = SessionVault(FileVaultBackend(tmp_path), vault_key)
        # Pre-seed an in-flight future that already failed: the next load() acts
        # as the waiter, catches the exception, and falls through to retry.
        future: asyncio.Future[object] = asyncio.Future()
        future.set_exception(RuntimeError("backend boom"))
        vault._inflight["example.com"] = future
        assert await vault.load("example.com") is None

    def test_session_summary_is_expired(self) -> None:
        assert SessionSummary("a.com", 0.0, 1.0, 0, 0).is_expired is True
        assert SessionSummary("a.com", 0.0, None, 0, 0).is_expired is False

    def test_vault_metrics_derived(self) -> None:
        metrics = VaultMetrics(
            cache_hits=5,
            cache_misses=3,
            encryption_count=2,
            encryption_total_ms=10.0,
            decryption_count=4,
            decryption_total_ms=20.0,
        )
        assert metrics.cache_hit_rate == pytest.approx(0.625)
        assert metrics.avg_encryption_ms == 5.0
        assert metrics.avg_decryption_ms == 5.0
        empty = VaultMetrics()
        assert empty.cache_hit_rate == 0.0
        assert empty.avg_encryption_ms == 0.0
        assert empty.avg_decryption_ms == 0.0

    def test_estimate_entry_size_fallback(self, tmp_path: Path, vault_key: bytes) -> None:
        vault = SessionVault(FileVaultBackend(tmp_path), vault_key)
        entry = SessionEntry("a.com", object(), 0.0, None)
        assert vault._estimate_entry_size(entry) == 2048

    async def test_cache_evict_one_evicts_oldest(self, tmp_path: Path, vault_key: bytes) -> None:
        vault = SessionVault(FileVaultBackend(tmp_path), vault_key)
        await vault.save("a.com", {"cookies": [{"name": "x"}]})
        await vault.save("b.com", {"cookies": [{"name": "y"}]})
        vault._cache_evict_one()
        assert "a.com" not in vault._cache
        assert "b.com" in vault._cache
        assert vault._metrics.cache_evictions == 1

    async def test_list_summaries_empty(self, tmp_path: Path, vault_key: bytes) -> None:
        vault = SessionVault(FileVaultBackend(tmp_path), vault_key)
        assert await vault.list_summaries() == []

    async def test_list_summaries_skips_missing_file(self, tmp_path: Path, vault_key: bytes) -> None:
        backend = FileVaultBackend(tmp_path)
        vault = SessionVault(backend, vault_key)
        await vault.save("good.com", {"cookies": []})
        with patch.object(backend, "list_all", return_value=["good.com", "ghost.com"]):
            summaries = await vault.list_summaries()
        assert [s.domain for s in summaries] == ["good.com"]

    async def test_cleanup_expired_with_domains(self, tmp_path: Path, vault_key: bytes) -> None:
        backend = FileVaultBackend(tmp_path)
        vault = SessionVault(backend, vault_key)
        await vault.save("expired.com", {"cookies": []}, ttl_days=-1)
        await vault.save("alive.com", {"cookies": []})
        assert await vault.cleanup_expired() == 1
        assert "alive.com" in await backend.list_all()

    async def test_cleanup_expired_empty(self, tmp_path: Path, vault_key: bytes) -> None:
        vault = SessionVault(FileVaultBackend(tmp_path), vault_key)
        assert await vault.cleanup_expired() == 0

    def test_cache_evict_one_empty_cache(self, tmp_path: Path, vault_key: bytes) -> None:
        vault = SessionVault(FileVaultBackend(tmp_path), vault_key)
        vault._cache_evict_one()  # no-op on empty cache
