"""Zero-Risk Shadow Tester

Server层的影子测试引擎。纯粹的"执行+比对"引擎，不操作DB。
利用Harness层的isolated_mode在后台安全地测试候选版本。

数据流：ABTestManager → ShadowTester → 返回 ShadowTestResult → ABTestManager → DB
"""

import logging
import time
from dataclasses import dataclass

from myrm_agent_harness.agent.skills.optimization.event_emitter import EventEmitter
from myrm_agent_harness.agent.skills.optimization.protocols import SkillExecutionProvider
from myrm_agent_harness.agent.skills.optimization.result_comparator import (
    ComparisonDetail,
    ResultComparator,
    StructuredComparator,
)

logger = logging.getLogger(__name__)


@dataclass
class ShadowTestResult:
    """影子测试结果（纯数据，不含DB操作）"""

    skill_id: str
    baseline_version: int
    candidate_version: int
    inputs: dict[str, object]
    baseline_result: dict[str, object]
    candidate_result: dict[str, object]
    comparison: ComparisonDetail
    baseline_duration: float
    candidate_duration: float
    success: bool
    error: str | None = None


class ShadowTester:
    """零风险影子测试引擎

    职责边界：
    - ✅ 在隔离模式下执行候选版本
    - ✅ 使用注入的 ResultComparator 比对结果
    - ✅ 返回 ShadowTestResult（纯数据）
    - ❌ 不操作 DB（由 ABTestManager 统一处理）
    - ❌ 不更新统计数据
    """

    def __init__(
        self,
        execution_provider: SkillExecutionProvider,
        event_emitter: EventEmitter,
        comparator: ResultComparator | None = None,
    ):
        self.execution_provider = execution_provider
        self.event_emitter = event_emitter
        self.comparator: ResultComparator = comparator or StructuredComparator()

    async def run_shadow_test(
        self,
        skill_id: str,
        baseline_version: int,
        candidate_version: int,
        inputs: dict[str, object],
        baseline_result: dict[str, object],
        baseline_duration: float,
    ) -> ShadowTestResult:
        """执行影子测试并返回结果

        Returns:
            ShadowTestResult 包含比对结果和性能数据
        """
        logger.info(f"Starting shadow test for {skill_id} (v{baseline_version} vs v{candidate_version})")

        try:
            start_time = time.time()

            candidate_result = await self.execution_provider.execute_skill_version(
                skill_id=skill_id,
                version=candidate_version,
                inputs=inputs,
                isolated_mode=True,
            )

            candidate_duration = time.time() - start_time

            comparison = await self.comparator.compare(baseline_result, candidate_result)

            logger.info(
                f"Shadow test completed for {skill_id}: "
                f"similarity={comparison.similarity_score:.2f}, "
                f"match={comparison.is_match}, "
                f"BaselineTime={baseline_duration:.2f}s, "
                f"CandidateTime={candidate_duration:.2f}s"
            )

            await self.event_emitter.emit(
                "shadow_test_completed",
                {
                    "skill_id": skill_id,
                    "baseline_version": baseline_version,
                    "candidate_version": candidate_version,
                    "similarity_score": comparison.similarity_score,
                    "is_match": comparison.is_match,
                    "baseline_duration": baseline_duration,
                    "candidate_duration": candidate_duration,
                },
            )

            return ShadowTestResult(
                skill_id=skill_id,
                baseline_version=baseline_version,
                candidate_version=candidate_version,
                inputs=inputs,
                baseline_result=baseline_result,
                candidate_result=candidate_result,
                comparison=comparison,
                baseline_duration=baseline_duration,
                candidate_duration=candidate_duration,
                success=True,
            )

        except Exception as e:
            logger.error(f"Shadow test failed for {skill_id} v{candidate_version}: {e}")

            await self.event_emitter.emit(
                "shadow_test_failed",
                {
                    "skill_id": skill_id,
                    "candidate_version": candidate_version,
                    "error": str(e),
                },
            )

            return ShadowTestResult(
                skill_id=skill_id,
                baseline_version=baseline_version,
                candidate_version=candidate_version,
                inputs=inputs,
                baseline_result=baseline_result,
                candidate_result={},
                comparison=ComparisonDetail(
                    similarity_score=0.0,
                    is_match=False,
                    diff_summary=f"Shadow test execution failed: {e}",
                ),
                baseline_duration=baseline_duration,
                candidate_duration=0.0,
                success=False,
                error=str(e),
            )
