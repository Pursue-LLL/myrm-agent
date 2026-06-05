"""
@input: 依赖 myrm_agent_harness.backends.skills.state_manager 的「技能状态管理器」
@output: 对外提供全局 SkillStateManager 单例（get/init）
@pos: 技能实例状态管理 —— 管理多实例技能的持久化状态

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""

from __future__ import annotations

import logging

from myrm_agent_harness.backends.skills.state_manager import SkillStateManager

logger = logging.getLogger(__name__)

_state_manager: SkillStateManager | None = None


def init_state_manager(base_dir: str = ".myrm/skills") -> None:
    """Initialize the global state manager instance.

    Should be called during application startup.

    Args:
        base_dir: Base directory for skill instance data
    """
    global _state_manager
    _state_manager = SkillStateManager(base_dir=base_dir)
    logger.info(f"Initialized SkillStateManager with base_dir={base_dir}")


def get_state_manager() -> SkillStateManager:
    """Get the global state manager instance.

    Returns:
        SkillStateManager instance

    Raises:
        RuntimeError: If state manager not initialized
    """
    if _state_manager is None:
        raise RuntimeError("SkillStateManager not initialized. Call init_state_manager() during application startup.")
    return _state_manager
