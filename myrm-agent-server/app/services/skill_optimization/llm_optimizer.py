"""LLM Optimizer with Retry Logic"""

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from myrm_agent_harness.agent.skills.optimization import OptimizationConfig

logger = logging.getLogger(__name__)


class LLMOptimizer:
    """LLM优化器（带重试逻辑）"""

    def __init__(self, llm: "BaseChatModel", config: "OptimizationConfig"):
        self.llm = llm
        self.config = config

    async def optimize_skill_with_retry(
        self,
        skill_content: str,
        quality_metrics: str,
    ) -> str:
        """带重试的LLM优化

        Args:
            skill_content: 原始skill内容
            quality_metrics: 质量指标文本

        Returns:
            str: 优化后的skill内容
        """
        max_retries = self.config.performance.llm_max_retries
        retry_delay = self.config.performance.llm_retry_delay

        for attempt in range(max_retries):
            try:
                return await self._call_llm(skill_content, quality_metrics)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = retry_delay * (2**attempt)
                logger.warning(f"LLM call failed (attempt {attempt + 1}/{max_retries}), retry in {wait_time}s: {e}")
                await asyncio.sleep(wait_time)

        raise RuntimeError("LLM optimization failed after all retries")

    async def _call_llm(self, skill_content: str, quality_metrics: str) -> str:
        """调用LLM进行优化"""
        prompt = f"""Optimize this skill based on quality metrics:

{skill_content}

Quality Metrics:
{quality_metrics}

Return the complete optimized SKILL.md content."""

        response = await self.llm.ainvoke(prompt)
        content = response.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content)
