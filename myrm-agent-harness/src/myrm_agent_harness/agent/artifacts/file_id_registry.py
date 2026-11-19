"""文件 ID 注册表

为本次运行写出的文件分配短 ID（如 @file_001），事件流用它把交付物卡片与文件对应起来。

设计要点：
- 短 ID 只在界面链路里使用：登记来自文件工具的观察者，反查来自工件事件（short_file_id）
- 文件工具与 bash 不解析短 ID：权限引擎按模型写下的路径判定，工具必须打开同一个路径
- 每次运行从 @file_001 重新编号，ID 不跨运行保留

使用方式：
1. 使用 ArtifactContextManager 初始化上下文
2. 文件写入后注册路径，得到短 ID
3. 事件流按路径反查短 ID

Example:
    ```python
    from myrm_agent_harness.agent.artifacts import ArtifactContextManager, get_artifact_context

    async with ArtifactContextManager():
        ctx = get_artifact_context()
        file_id = ctx.file_id_registry.register("/full/path/to/file.txt")
        # file_id = "@file_001"
    ```

[INPUT]
- (none)

[OUTPUT]
- FileIdRegistry: path → short-ID registry dataclass
- register_file: module-level register helper (returns None if context unset)
- lookup_short_file_id: resolve workspace path → @file_NNN when registered

[POS]
File ID registry. Numbers the files a run wrote with short @file_* ids for artifact events; never a path alias for tools.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# 文件 ID 前缀
FILE_ID_PREFIX = "@file_"


def _normalize_registry_path(full_path: str) -> str:
    try:
        return str(Path(full_path).resolve())
    except OSError:
        return full_path


@dataclass
class FileIdRegistry:
    """文件 ID 注册表

    维护完整路径到短 ID 的映射关系。
    """

    # 完整路径 -> 短 ID（同一路径只登记一次）
    path_to_id: dict[str, str] = field(default_factory=dict)

    # 下一个可用的 ID 序号
    next_id: int = 1

    def register(self, full_path: str) -> str:
        """注册文件并返回短 ID

        如果路径已注册，返回已有的 ID（去重）。

        Args:
            full_path: 文件的完整路径

        Returns:
            短 ID，如 @file_001
        """
        full_path = _normalize_registry_path(full_path)

        # 检查是否已注册
        if full_path in self.path_to_id:
            return self.path_to_id[full_path]

        # 生成新 ID
        file_id = f"{FILE_ID_PREFIX}{self.next_id:03d}"
        self.next_id += 1

        self.path_to_id[full_path] = file_id

        logger.info(f" 注册文件 ID: {file_id} -> {full_path}")
        return file_id


def lookup_short_file_id(full_path: str) -> str | None:
    """Return @file_NNN alias for a workspace path when registered."""
    registry = _get_registry()
    if registry is None:
        return None
    normalized = _normalize_registry_path(full_path)
    hit = registry.path_to_id.get(normalized)
    if hit is not None:
        return hit
    for path, file_id in registry.path_to_id.items():
        if _normalize_registry_path(path) == normalized:
            return file_id
    return None


def _get_registry() -> FileIdRegistry | None:
    """获取当前的文件 ID 注册表"""
    from .context import get_artifact_context

    ctx = get_artifact_context()
    if ctx is not None:
        return ctx.file_id_registry
    return None


def register_file(full_path: str) -> str | None:
    """注册文件并返回短 ID

    便捷函数，自动获取当前注册表。

    Args:
        full_path: 文件的完整路径

    Returns:
        短 ID，如果注册表未初始化则返回 None
    """
    registry = _get_registry()
    if registry is None:
        logger.debug("文件 ID 注册表未初始化，无法注册文件")
        return None
    return registry.register(full_path)


__all__ = [
    "FILE_ID_PREFIX",
    "FileIdRegistry",
    "lookup_short_file_id",
    "register_file",
]
