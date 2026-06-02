"""Federated Insight Extractor

Server层的联邦式优化洞察提取器。
利用沙箱内的本地 LLM，定期分析执行日志，提取“抽象的优化经验”（不上报代码），
写入本地 Outbox。完美解决隐私与群体进化的矛盾。
"""

import asyncio
import logging

from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.agent.skills.optimization.event_emitter import EventEmitter
from myrm_agent_harness.agent.skills.optimization.protocols import SkillExecutionProvider

logger = logging.getLogger(__name__)


class FederatedInsightExtractor:
    """联邦式优化洞察提取器

    在沙箱空闲时（如夜间），批量分析执行日志，
    利用本地 LLM 提取“抽象优化策略”（保护隐私），写入本地 Outbox。
    """

    def __init__(
        self,
        execution_provider: SkillExecutionProvider,
        llm: BaseChatModel,
        event_emitter: EventEmitter,
        extraction_interval_hours: int = 24,  # 默认每天提取一次
    ):
        self.execution_provider = execution_provider
        self.llm = llm
        self.event_emitter = event_emitter
        self.extraction_interval_hours = extraction_interval_hours
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """启动提取后台任务"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._extraction_loop())
        logger.info("FederatedInsightExtractor started")

    async def stop(self) -> None:
        """停止提取后台任务"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("FederatedInsightExtractor stopped")

    async def _extraction_loop(self) -> None:
        """提取循环"""
        while self._running:
            try:
                # 假设在夜间执行
                await self._extract_insights()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in FederatedInsightExtractor loop: {e}")

            await asyncio.sleep(self.extraction_interval_hours * 3600)

    async def _extract_insights(self) -> None:
        """提取所有活跃Skill的优化洞察"""
        logger.info("FederatedInsightExtractor: Extracting insights...")

        # 获取所有有执行记录的skill
        skill_ids = await self.execution_provider.get_all_skill_ids()

        for skill_id in skill_ids:
            try:
                # 获取最近的执行样本
                samples = await self.execution_provider.get_skill_executions(
                    skill_id=skill_id,
                    days=1,
                )

                if not samples:
                    continue

                # 提取失败的样本
                failed_samples = [s for s in samples if not s.success]
                if not failed_samples:
                    continue

                # 提取抽象经验
                insight = await self._analyze_failures_with_llm(skill_id, failed_samples)

                if insight:
                    # 写入 Outbox (这里简化为发送事件，实际应写入本地数据库以保证不丢失)
                    logger.info(f"Extracted insight for {skill_id}: {insight}")
                    await self.event_emitter.emit(
                        "insight_extracted",
                        {
                            "skill_id": skill_id,
                            "insight": insight,
                            "timestamp": asyncio.get_event_loop().time(),
                        },
                    )
            except Exception as e:
                logger.error(f"Failed to extract insight for {skill_id}: {e}")

    async def _analyze_failures_with_llm(self, skill_id: str, failed_samples: list[dict[str, object]]) -> str | None:
        """利用本地 LLM 分析失败样本，提取抽象经验

        返回的经验不应包含具体的代码、Prompt 或用户数据，
        只应包含“策略”（如：“处理 PDF 时，如果包含复杂表格，应先使用 OCR”）。
        """
        # 实际业务中，这里会调用 LLM API
        # prompt = "Analyze the following execution failures and extract a general optimization strategy. Do not include any specific code or user data."
        # response = await self.llm.generate(prompt, failed_samples)
        # return response.text

        # 这里模拟 LLM 的响应
        if "pdf" in skill_id.lower():
            return "When processing PDFs with complex tables, consider using OCR as a fallback."
        elif "search" in skill_id.lower():
            return "Web search skills should implement exponential backoff for rate-limited APIs."
        else:
            return "Ensure proper input validation before executing the main logic."
