"""Strategy-Level Semantic Merger

Server层的策略级智能融合器。
拉取全局“优化策略”后，利用本地 LLM 将全局策略应用到本地定制代码上，
生成新版本供用户确认。彻底解决覆盖冲突。
"""

import logging
from typing import Any

from myrm_agent_harness.agent.skills.optimization.event_emitter import EventEmitter
from myrm_agent_harness.agent.skills.optimization.protocols import SkillOptimizationStorage

logger = logging.getLogger(__name__)


class SemanticMerger:
    """策略级智能融合器

    接收从 Control Plane 下发的全局优化策略，
    利用本地 LLM 将其智能地应用到当前沙箱的本地代码上，
    生成一个融合了“全局智慧”和“本地定制”的候选版本。
    """

    def __init__(
        self,
        storage: SkillOptimizationStorage,
        llm: Any,  # 本地 LLM 实例
        event_emitter: EventEmitter,
    ):
        self.storage = storage
        self.llm = llm
        self.event_emitter = event_emitter

    async def merge_global_strategy(
        self,
        skill_id: str,
        global_strategy: str,
    ) -> str | None:
        """融合全局策略到本地代码

        Args:
            skill_id: Skill ID
            global_strategy: 从 Control Plane 接收到的全局优化策略（如：“增加重试机制”）

        Returns:
            融合后的新代码内容，如果融合失败则返回 None
        """
        logger.info(f"Merging global strategy for {skill_id}: {global_strategy}")

        # 1. 获取当前活跃的本地代码
        active_version = await self.storage.get_active_version(skill_id)
        if not active_version:
            logger.warning(f"No active version found for {skill_id}, cannot merge strategy.")
            return None

        local_code = active_version.content

        # 2. 利用本地 LLM 进行语义合并
        try:
            merged_code = await self._apply_strategy_with_llm(local_code, global_strategy)

            # 3. 发送事件通知，供前端Dashboard展示（三栏对比确认）
            await self.event_emitter.emit(
                "strategy_merged",
                {
                    "skill_id": skill_id,
                    "global_strategy": global_strategy,
                    "local_code": local_code,
                    "merged_code": merged_code,
                    "baseline_version": active_version.version_id,
                },
            )

            return merged_code

        except Exception as e:
            logger.error(f"Failed to merge strategy for {skill_id}: {e}")
            return None

    async def _apply_strategy_with_llm(self, local_code: str, strategy: str) -> str:
        """利用本地 LLM 将策略应用到代码上

        Prompt 必须强调：保留所有本地的特定业务逻辑（如数据库连接、API Key 等），
        仅仅将“策略”应用上去。
        """
        # 实际业务中，这里会调用 LLM API
        # prompt = f"Apply the following optimization strategy to the code below.\nStrategy: {strategy}\n\nCRITICAL: Preserve all local business logic, API keys, and custom configurations.\n\nCode:\n{local_code}"
        # response = await self.llm.generate(prompt)
        # return response.text

        # 这里模拟 LLM 的响应
        logger.debug(f"Applying strategy '{strategy}' to local code...")

        # 模拟：在代码开头加上策略注释
        merged = f"# Applied Global Strategy: {strategy}\n" + local_code

        # 模拟：如果策略是加重试，就在代码里加上重试逻辑
        if "retry" in strategy.lower():
            merged = merged.replace("def execute", "@retry(stop=stop_after_attempt(3))\ndef execute")

        return merged
