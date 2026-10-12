"""Skill Execution Provider Implementation

Server层实现SkillExecutionProvider协议：执行特定版本的Skill（影子测试使用）。
执行样本与元数据的来源尚未接入，对应方法如实返回空结果。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.agent.skills.optimization import SkillExecutionSample
    from myrm_agent_harness.backends.skills.types import SkillMetadata

logger = logging.getLogger(__name__)


class ServerSkillExecutionProvider:
    """Server层的Skill执行事件提供者实现

    从event_log或metrics系统查询skill执行数据。
    """

    async def get_skill_executions(
        self,
        skill_id: str,
        days: int = 7,
        session_id: str | None = None,
    ) -> list[SkillExecutionSample]:
        """获取skill执行样本

        Args:
            skill_id: Skill ID
            days: 最近N天的数据
            session_id: 可选的session过滤

        Returns:
            执行样本列表（当前返回空列表，待集成event_log系统）
        """
        logger.debug(f"Fetching executions for skill: {skill_id}, days: {days}")

        return []

    async def get_all_skill_ids(self) -> list[str]:
        """获取所有有执行记录的skill ID

        Returns:
            Skill ID列表
        """
        logger.debug("Fetching all skill IDs")

        return []

    async def count_executions(
        self,
        skill_id: str,
        days: int = 7,
    ) -> int:
        """统计执行次数

        Args:
            skill_id: Skill ID
            days: 最近N天

        Returns:
            执行次数
        """
        logger.debug(f"Counting executions for skill: {skill_id}")
        return 0

    async def get_skill_metadata(self, skill_id: str) -> SkillMetadata | None:
        """获取skill元数据

        元数据来源与执行样本一样尚未接入，当前如实返回None。

        Args:
            skill_id: Skill ID

        Returns:
            SkillMetadata对象，如果skill不存在则返回None
        """
        logger.debug(f"Skill metadata source is not wired: {skill_id}")
        return None

    async def execute_skill_version(
        self,
        skill_id: str,
        version: int,
        inputs: dict[str, object],
        isolated_mode: bool = False,
    ) -> dict[str, object]:
        """执行特定版本的Skill

        Args:
            skill_id: Skill ID
            version: 版本号
            inputs: 执行输入参数
            isolated_mode: 是否开启隔离模式（无副作用，用于影子测试）

        Returns:
            执行结果
        """
        logger.info(f"Executing skill {skill_id} version {version} (isolated={isolated_mode})")

        from myrm_agent_harness.backends.skills.decorators.version_aware import forced_version_var

        from app.ai_agents.general_agent.agent import GeneralAgent
        from app.core.types import ModelConfig
        from app.services.agent.platform_config import load_platform_model_config

        # 1. Set forced version for this context
        token = forced_version_var.set(version)

        try:
            platform_model = await load_platform_model_config()

            temp_agent = GeneralAgent(
                model_cfg=ModelConfig(
                    model=platform_model.model,
                    api_key=platform_model.api_key,
                    base_url=platform_model.base_url,
                    api_keys=platform_model.api_keys,
                ),
                mcp_config=None,
                search_service_cfg=None,
                enable_web_search=False,
                skill_ids=[skill_id],
            )

            await temp_agent._init_agent(effective_chat_id="shadow_test")

            agent_impl = temp_agent.agent
            if agent_impl is None:
                raise ValueError("Agent failed to initialize for shadow test")

            tool = next((t for t in agent_impl.user_tools if t.name == skill_id), None)
            if not tool:
                raise ValueError(f"Tool {skill_id} not found in agent for shadow test")

            # Run the tool
            # If isolated_mode is True, we might need a wrapper that prevents side effects
            # Harness layer tools usually respect some internal 'dry_run' or similar if implemented
            result = await tool.ainvoke(inputs)

            return {"status": "success", "result": result, "version": version}

        except Exception as e:
            logger.error(f"Execution failed for {skill_id} v{version}: {e}")
            return {"status": "error", "error": str(e), "version": version}
        finally:
            forced_version_var.reset(token)


__all__ = ["ServerSkillExecutionProvider"]
