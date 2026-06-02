"""Global SessionVault singleton for browser session persistence.

[INPUT]
- myrm_agent_harness.toolkits.browser::SessionVault (POS: 加密 session 存储)
- myrm_agent_harness.toolkits.browser.backends::FileVaultBackend (POS: 文件后端)
- app.config.settings::DatabaseSettings (POS: 数据库配置，提供 state_dir)

[OUTPUT]
- get_global_session_vault: 获取全局 SessionVault 单例

[POS]
SessionVault 全局单例管理。确保进程内所有代码使用同一个 SessionVault 实例，
实现缓存共享和状态一致性。类似 GlobalBrowserPool 的单例设计。
"""

import logging
from pathlib import Path

from myrm_agent_harness.toolkits.browser import SessionVault
from myrm_agent_harness.toolkits.browser.backends.file_backend import FileVaultBackend, load_or_create_key

logger = logging.getLogger(__name__)

_global_vault: SessionVault | None = None


def get_global_session_vault() -> SessionVault:
    """获取全局 SessionVault 单例（懒加载）。

    进程内所有代码共享同一个 SessionVault 实例，确保：
    1. LRU 缓存全局共享
    2. 内存占用最小化（单个缓存实例）
    3. 状态一致性（无缓存不同步问题）

    Returns:
        SessionVault 全局实例
    """
    global _global_vault

    if _global_vault is None:
        from app.config.settings import settings

        state_dir = Path(settings.database.state_dir)
        vault_dir = state_dir / "session_vault"
        key_path = state_dir / "vault.key"
        encryption_key = load_or_create_key(key_path)
        backend = FileVaultBackend(vault_dir)

        _global_vault = SessionVault(
            backend,
            encryption_key,
            cache_ttl=300,
            cache_max_size=100,
            cache_max_memory_mb=50,
        )

        logger.info("Global SessionVault initialized (vault_dir=%s)", vault_dir)

    return _global_vault
