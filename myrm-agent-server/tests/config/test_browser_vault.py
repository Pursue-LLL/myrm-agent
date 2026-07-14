"""浏览器 SessionVault 隔离管理测试

覆盖场景:
- BV1: 使用 settings.database.state_dir 而非硬编码 home 路径
- BV2: 单例模式 - 多次调用返回同一实例
- BV3: agent vault 按 agent_id 子目录隔离
- BV4: agent vault 缓存复用
- BV5: cleanup_all_agent_vaults 遍历所有子目录
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.core.security.browser_vault as vault_module


class TestGetGlobalSessionVault:
    def setup_method(self) -> None:
        vault_module._global_vault = None

    def teardown_method(self) -> None:
        vault_module._global_vault = None

    def test_uses_settings_state_dir(self, tmp_path: Path) -> None:
        """Vault paths must derive from settings.database.state_dir, not Path.home()."""
        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(tmp_path)

        mock_vault_cls = MagicMock()
        mock_vault_instance = MagicMock()
        mock_vault_cls.return_value = mock_vault_instance

        with (
            patch.object(vault_module, "SessionVault", mock_vault_cls),
            patch.object(vault_module, "FileVaultBackend") as mock_backend_cls,
            patch.object(vault_module, "load_or_create_key", return_value=b"fake-key"),
            patch("app.config.settings.settings", mock_settings),
        ):
            result = vault_module.get_global_session_vault()

        assert result is mock_vault_instance
        mock_backend_cls.assert_called_once_with(tmp_path / "session_vault")

    def test_singleton_returns_same_instance(self, tmp_path: Path) -> None:
        """Multiple calls must return the same SessionVault instance."""
        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(tmp_path)

        mock_vault_cls = MagicMock()
        mock_vault_instance = MagicMock()
        mock_vault_cls.return_value = mock_vault_instance

        with (
            patch.object(vault_module, "SessionVault", mock_vault_cls),
            patch.object(vault_module, "FileVaultBackend"),
            patch.object(vault_module, "load_or_create_key", return_value=b"fake-key"),
            patch("app.config.settings.settings", mock_settings),
        ):
            first = vault_module.get_global_session_vault()
            second = vault_module.get_global_session_vault()

        assert first is second
        assert mock_vault_cls.call_count == 1


class TestGetAgentSessionVault:
    def setup_method(self) -> None:
        vault_module._agent_vaults.clear()

    def teardown_method(self) -> None:
        vault_module._agent_vaults.clear()

    def test_agent_vault_uses_agent_subdirectory(self, tmp_path: Path) -> None:
        """Agent vault must use session_vault/{safe_agent_id} subdirectory."""
        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(tmp_path)

        mock_vault_cls = MagicMock()
        mock_vault_instance = MagicMock()
        mock_vault_cls.return_value = mock_vault_instance

        with (
            patch.object(vault_module, "SessionVault", mock_vault_cls),
            patch.object(vault_module, "FileVaultBackend") as mock_backend_cls,
            patch.object(vault_module, "load_or_create_key", return_value=b"fake-key"),
            patch("app.config.settings.settings", mock_settings),
        ):
            result = vault_module.get_agent_session_vault("agent_abc123")

        assert result is mock_vault_instance
        mock_backend_cls.assert_called_once_with(tmp_path / "session_vault" / "agent_abc123")

    def test_agent_vault_sanitizes_special_chars(self, tmp_path: Path) -> None:
        """Agent IDs with special chars must be sanitized for filesystem safety."""
        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(tmp_path)

        mock_vault_cls = MagicMock()
        mock_vault_cls.return_value = MagicMock()

        with (
            patch.object(vault_module, "SessionVault", mock_vault_cls),
            patch.object(vault_module, "FileVaultBackend") as mock_backend_cls,
            patch.object(vault_module, "load_or_create_key", return_value=b"fake-key"),
            patch("app.config.settings.settings", mock_settings),
        ):
            vault_module.get_agent_session_vault("my/agent..id")

        expected_dir = tmp_path / "session_vault" / "my_agent__id"
        mock_backend_cls.assert_called_once_with(expected_dir)

    def test_agent_vault_cached_on_second_call(self, tmp_path: Path) -> None:
        """Same agent_id must return cached vault instance."""
        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(tmp_path)

        mock_vault_cls = MagicMock()
        mock_vault_instance = MagicMock()
        mock_vault_cls.return_value = mock_vault_instance

        with (
            patch.object(vault_module, "SessionVault", mock_vault_cls),
            patch.object(vault_module, "FileVaultBackend"),
            patch.object(vault_module, "load_or_create_key", return_value=b"fake-key"),
            patch("app.config.settings.settings", mock_settings),
        ):
            first = vault_module.get_agent_session_vault("agent_x")
            second = vault_module.get_agent_session_vault("agent_x")

        assert first is second
        assert mock_vault_cls.call_count == 1

    def test_different_agents_get_different_vaults(self, tmp_path: Path) -> None:
        """Different agent_ids must produce separate vault instances."""
        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(tmp_path)

        call_count = 0
        instances: list[MagicMock] = []

        def make_vault(*_args: object, **_kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            inst = MagicMock(name=f"vault_{call_count}")
            instances.append(inst)
            return inst

        with (
            patch.object(vault_module, "SessionVault", side_effect=make_vault),
            patch.object(vault_module, "FileVaultBackend"),
            patch.object(vault_module, "load_or_create_key", return_value=b"fake-key"),
            patch("app.config.settings.settings", mock_settings),
        ):
            v1 = vault_module.get_agent_session_vault("agent_a")
            v2 = vault_module.get_agent_session_vault("agent_b")

        assert v1 is not v2
        assert call_count == 2


class TestCleanupAllAgentVaults:
    def setup_method(self) -> None:
        vault_module._agent_vaults.clear()

    def teardown_method(self) -> None:
        vault_module._agent_vaults.clear()

    @pytest.mark.asyncio
    async def test_cleanup_iterates_subdirectories(self, tmp_path: Path) -> None:
        """cleanup_all_agent_vaults must process all subdirectories."""
        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(tmp_path)

        vault_root = tmp_path / "session_vault"
        (vault_root / "agent_1").mkdir(parents=True)
        (vault_root / "agent_2").mkdir(parents=True)
        (vault_root / "some_file.enc").touch()

        mock_vault = MagicMock()
        mock_vault.cleanup_expired = AsyncMock(return_value=3)

        with (
            patch.object(vault_module, "SessionVault", return_value=mock_vault),
            patch.object(vault_module, "FileVaultBackend"),
            patch.object(vault_module, "load_or_create_key", return_value=b"fake-key"),
            patch("app.config.settings.settings", mock_settings),
        ):
            total = await vault_module.cleanup_all_agent_vaults()

        assert total == 6  # 3 per agent x 2 agents

    @pytest.mark.asyncio
    async def test_cleanup_returns_zero_when_no_vault_dir(self, tmp_path: Path) -> None:
        """Must return 0 when session_vault directory doesn't exist."""
        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(tmp_path)

        with patch("app.config.settings.settings", mock_settings):
            total = await vault_module.cleanup_all_agent_vaults()

        assert total == 0

    @pytest.mark.asyncio
    async def test_cleanup_uses_cached_agent_vault(self, tmp_path: Path) -> None:
        """Must reuse cached vault if agent_id already in _agent_vaults."""
        mock_settings = MagicMock()
        mock_settings.database.state_dir = str(tmp_path)

        vault_root = tmp_path / "session_vault"
        (vault_root / "agent_cached").mkdir(parents=True)

        cached_vault = MagicMock()
        cached_vault.cleanup_expired = AsyncMock(return_value=5)
        vault_module._agent_vaults["agent_cached"] = cached_vault

        with (
            patch.object(vault_module, "SessionVault") as mock_cls,
            patch.object(vault_module, "FileVaultBackend"),
            patch.object(vault_module, "load_or_create_key", return_value=b"fake-key"),
            patch("app.config.settings.settings", mock_settings),
        ):
            total = await vault_module.cleanup_all_agent_vaults()

        assert total == 5
        mock_cls.assert_not_called()
