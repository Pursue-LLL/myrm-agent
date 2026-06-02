"""平台适配层

根据 DEPLOY_MODE 环境变量自动选择平台实现：
- local: 本地模式（桌面客户端 / CLI WebUI），SQLite, Qdrant 嵌入式, 本地存储
- sandbox: 沙箱模式（SQLite + Qdrant embedded 在持久化卷, 由控制平面管理）

使用方式（推荐 getter 函数，类型安全）：
    from app.platform_utils import get_database_engine, get_session_factory

也支持属性访问（延迟加载，但类型检查器无法推断类型）：
    from app.platform_utils import database_engine, session_factory

特点：
- 类型安全的 getter 函数（返回具体类型 / Protocol）
- 延迟加载（首次访问时才创建，后续 O(1)）
- 零 cast，Protocol 接口约束
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, cast

from app.config.deploy_mode import get_deploy_mode
from app.config.deploy_mode import is_local_mode as _is_local_mode
from app.platform_utils.deployment_capabilities import get_deployment_capabilities

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from myrm_agent_harness.runtime.quota.manager import SimpleStorageQuotaManager
    from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor
    from myrm_agent_harness.toolkits.storage.base import StorageProvider
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from app.core.artifacts.processor import BaseArtifactProcessor
    from app.platform_utils.execution import ExecutionStrategy
    from app.platform_utils.protocols import FileService

    database_engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    sandbox_executor_factory: Callable[..., CodeExecutor]
    storage_provider: StorageProvider
    file_service: FileService
    checkpointer: BaseCheckpointSaver[str]
    execution_strategy: ExecutionStrategy

# =============================================================================
# 部署模式（委托给 config/deploy_mode.py，单一来源）
# =============================================================================

DEPLOY_MODE = get_deploy_mode().value

# =============================================================================
# 类型化服务单例
# =============================================================================

_database_engine: "AsyncEngine | None" = None
_session_factory: "async_sessionmaker[AsyncSession] | None" = None
_sandbox_executor_factory: "Callable[..., CodeExecutor] | None" = None
_storage_provider: "StorageProvider | None" = None
_file_service: "FileService | None" = None
_checkpointer: "BaseCheckpointSaver[str] | None" = None

# =============================================================================
# 数据库相关
# =============================================================================


def get_database_engine() -> "AsyncEngine":
    """获取数据库引擎"""
    global _database_engine
    if _database_engine is None:
        from app.database.factory import create_engine

        _database_engine = create_engine()
    return _database_engine


def get_session_factory() -> "async_sessionmaker[AsyncSession]":
    """获取数据库会话工厂"""
    global _session_factory
    if _session_factory is None:
        from app.database.factory import create_session_factory

        _session_factory = create_session_factory(get_database_engine())
    return _session_factory


async def reset_database_engine() -> None:
    """重置数据库引擎和会话工厂（用于容灾降级）"""
    global _database_engine, _session_factory
    if _database_engine is not None:
        await _database_engine.dispose()
        _database_engine = None
    _session_factory = None


# =============================================================================
# 沙箱执行器
# =============================================================================


def get_sandbox_executor_factory() -> "Callable[..., CodeExecutor]":
    """获取沙箱执行器工厂"""
    global _sandbox_executor_factory
    if _sandbox_executor_factory is None:
        from myrm_agent_harness.toolkits.code_execution.factory import create_executor

        _sandbox_executor_factory = create_executor
    return _sandbox_executor_factory


# =============================================================================
# 存储提供商
# =============================================================================


def get_storage_provider() -> "StorageProvider":
    """获取存储提供商

    根据 DEPLOY_MODE 返回对应的存储后端：
    - 所有模式均统一使用本地存储（LocalStorageBackend），沙箱模式下指向持久化Volume
    """
    global _storage_provider
    if _storage_provider is None:
        from myrm_agent_harness.toolkits.storage.factory import (
            get_storage_provider as _fw_get,
        )

        _storage_provider = _fw_get()
    return _storage_provider


# =============================================================================
# 文件服务
# =============================================================================


def get_file_service() -> "FileService":
    """获取文件服务

    根据 DEPLOY_MODE 返回对应的文件服务：
    - 所有模式均统一使用本地文件服务（LocalFileService），沙箱即存储，无需上传云端
    """
    global _file_service
    if _file_service is None:
        from app.platform_utils.local.file_service import LocalFileService

        _file_service = cast("FileService", LocalFileService())
    assert _file_service is not None
    return _file_service


# =============================================================================
# LangGraph Checkpointer
# =============================================================================


def set_checkpointer(checkpointer: "BaseCheckpointSaver[str]") -> None:
    """设置全局 checkpointer（用于应用启动时注入）

    Args:
        checkpointer: 预初始化的 checkpointer 实例
    """
    global _checkpointer
    _checkpointer = checkpointer


def _reset_checkpointer_for_testing() -> None:
    """重置全局 checkpointer 状态（仅用于测试）"""
    global _checkpointer
    _checkpointer = None


def get_checkpointer() -> "BaseCheckpointSaver[str]":
    """获取 LangGraph checkpointer

    正常情况下，checkpointer 由 `app/server/lifespan.py` 在启动阶段通过 `set_checkpointer()` 注入。
    此函数提供简单的延迟 fallback，确保即使启动时未初始化也不会崩溃。

    Returns:
        BaseCheckpointSaver: LangGraph checkpointer 实例
    """
    global _checkpointer
    if _checkpointer is None:
        import logging

        from langgraph.checkpoint.memory import MemorySaver

        logger = logging.getLogger(__name__)
        _checkpointer = MemorySaver()
        logger.warning("🔖 Checkpointer: MemorySaver (lazy fallback)")
        logger.warning(
            "   Note: Checkpointer should be initialized in app/server/lifespan startup"
        )

    return _checkpointer


# =============================================================================
# 配额管理器
# =============================================================================

_quota_manager: "SimpleStorageQuotaManager | None" = None


async def get_quota_manager() -> "SimpleStorageQuotaManager":
    """Get storage quota manager instance.

    Returns:
        SimpleStorageQuotaManager: Storage quota manager instance
    """
    global _quota_manager
    if _quota_manager is None:
        from myrm_agent_harness.runtime.quota.manager import SimpleStorageQuotaManager

        _quota_manager = SimpleStorageQuotaManager()

    return _quota_manager


# =============================================================================
# 工件处理器
# =============================================================================


def is_local_mode() -> bool:
    """是否是本地模式"""
    return _is_local_mode()


def get_artifact_processor(
    user_id: str,
    chat_id: str,
    api_prefix: str = "/api/v1",
) -> "BaseArtifactProcessor":
    """获取工件处理器

    根据部署模式自动选择：
    - 所有模式均统一使用本地工件处理器（LocalArtifactProcessor），仅记录路径，不上传云端
    """
    from app.core.artifacts import LocalArtifactProcessor

    return LocalArtifactProcessor(
        chat_id=chat_id,
        api_prefix=api_prefix,
    )


# =============================================================================
# 延迟加载（使用 __getattr__ 实现真正的按需加载）
# =============================================================================


def get_execution_strategy() -> "ExecutionStrategy":
    """Get the agent execution strategy (always local).

    The server always executes agents in-process. In sandbox mode, the control
    plane (a separate service) handles sandbox creation and lifecycle.

    Returns:
        LocalExecutionStrategy instance
    """
    from app.platform_utils.execution import get_execution_strategy as _get

    return _get()


def __getattr__(name: str) -> object:
    """模块级延迟加载（PEP 562）"""
    if name == "database_engine":
        return get_database_engine()
    elif name == "session_factory":
        return get_session_factory()
    elif name == "sandbox_executor_factory":
        return get_sandbox_executor_factory()
    elif name == "storage_provider":
        return get_storage_provider()
    elif name == "file_service":
        return get_file_service()
    elif name == "checkpointer":
        return get_checkpointer()
    elif name == "execution_strategy":
        return get_execution_strategy()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# =============================================================================
# 导出列表
# =============================================================================

__all__ = [
    "DEPLOY_MODE",
    "is_local_mode",
    "database_engine",
    "session_factory",
    "sandbox_executor_factory",
    "storage_provider",
    "file_service",
    "checkpointer",
    "get_artifact_processor",
    "get_database_engine",
    "get_session_factory",
    "reset_database_engine",
    "get_sandbox_executor_factory",
    "get_storage_provider",
    "get_file_service",
    "get_checkpointer",
    "set_checkpointer",
    "_reset_checkpointer_for_testing",
    "get_quota_manager",
    "get_execution_strategy",
    "get_deployment_capabilities",
]
