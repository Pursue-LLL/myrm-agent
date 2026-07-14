"""SessionVault instance management for browser session persistence.

[INPUT]
- myrm_agent_harness.toolkits.browser::SessionVault (POS: 加密 session 存储)
- myrm_agent_harness.toolkits.browser.backends::FileVaultBackend (POS: 文件后端)
- app.config.settings::DatabaseSettings (POS: 数据库配置，提供 state_dir)

[OUTPUT]
- get_global_session_vault: 获取全局 SessionVault 单例（用于非 agent 场景）
- get_agent_session_vault: 获取 agent 专属 SessionVault（按 agent_id 物理隔离）
- cleanup_all_agent_vaults: 清理所有 agent vault 中的过期 session

[POS]
SessionVault 实例管理。全局 vault 用于 web_fetch 等非 agent 场景；
agent vault 用于多智能体场景，按 agent_id 子目录物理隔离，
防止不同智能体登录同一网站时 session 互相覆盖。
"""

import logging
import re
from pathlib import Path

from myrm_agent_harness.toolkits.browser import SessionVault
from myrm_agent_harness.toolkits.browser.backends.file_backend import FileVaultBackend, load_or_create_key

logger = logging.getLogger(__name__)

_global_vault: SessionVault | None = None
_agent_vaults: dict[str, SessionVault] = {}

_SAFE_DIR_RE = re.compile(r"[^a-zA-Z0-9_\-]")


def _safe_dir_name(agent_id: str) -> str:
    """Sanitize agent_id into a filesystem-safe directory name."""
    return _SAFE_DIR_RE.sub("_", agent_id)[:200]


def _get_state_dir() -> Path:
    from app.config.settings import settings

    return Path(settings.database.state_dir)


def _get_encryption_key() -> bytes:
    key_path = _get_state_dir() / "vault.key"
    return load_or_create_key(key_path)


def get_global_session_vault() -> SessionVault:
    """获取全局 SessionVault 单例（用于 web_fetch、warmup 等非 agent 场景）。

    Returns:
        SessionVault 全局实例
    """
    global _global_vault

    if _global_vault is None:
        state_dir = _get_state_dir()
        vault_dir = state_dir / "session_vault"
        encryption_key = _get_encryption_key()
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


def get_agent_session_vault(agent_id: str) -> SessionVault:
    """获取 agent 专属 SessionVault（按 agent_id 子目录物理隔离）。

    每个非默认智能体拥有独立的 session 存储目录，防止多智能体
    登录同一网站时 session 互相覆盖。实例按 agent_id 缓存复用。

    Args:
        agent_id: 智能体唯一标识

    Returns:
        该 agent 专属的 SessionVault 实例
    """
    if agent_id in _agent_vaults:
        return _agent_vaults[agent_id]

    state_dir = _get_state_dir()
    vault_dir = state_dir / "session_vault" / _safe_dir_name(agent_id)
    encryption_key = _get_encryption_key()
    backend = FileVaultBackend(vault_dir)

    vault = SessionVault(
        backend,
        encryption_key,
        cache_ttl=300,
        cache_max_size=50,
        cache_max_memory_mb=20,
    )

    _agent_vaults[agent_id] = vault
    logger.info("Agent SessionVault initialized (agent_id=%s, vault_dir=%s)", agent_id, vault_dir)
    return vault


async def cleanup_all_agent_vaults() -> int:
    """清理所有 agent vault 子目录中的过期 session。

    扫描 session_vault/ 下的所有子目录，为每个子目录创建临时 vault
    执行过期清理。已缓存的 agent vault 直接复用。

    Returns:
        总共清理的过期 session 数量
    """
    state_dir = _get_state_dir()
    vault_root = state_dir / "session_vault"

    if not vault_root.exists():
        return 0

    total_removed = 0
    encryption_key = _get_encryption_key()

    for sub_dir in vault_root.iterdir():
        if not sub_dir.is_dir():
            continue

        agent_id = sub_dir.name
        if agent_id in _agent_vaults:
            vault = _agent_vaults[agent_id]
        else:
            backend = FileVaultBackend(sub_dir)
            vault = SessionVault(backend, encryption_key, cache_max_size=0)

        try:
            removed = await vault.cleanup_expired()
            total_removed += removed
        except Exception as exc:
            logger.warning("Failed to cleanup expired sessions for agent %s: %s", agent_id, exc)

    return total_removed
