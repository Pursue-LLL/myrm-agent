"""浏览器 SessionVault 全局单例测试

覆盖场景:
- BV1: 使用 settings.database.state_dir 而非硬编码 home 路径
- BV2: 单例模式 - 多次调用返回同一实例
- BV3: vault_dir 和 key_path 创建在 state_dir 下
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

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
