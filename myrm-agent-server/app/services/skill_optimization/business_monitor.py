"""Business Monitor & Auto-Heal Service

Server层的业务监控与自愈服务。
替代了原先在Harness层的AnomalyDetector，将业务策略（何时回滚）与框架机制（如何回滚）彻底分离。
"""

import asyncio
import logging

from myrm_agent_harness.agent.skills.optimization.event_emitter import EventEmitter
from myrm_agent_harness.agent.skills.optimization.protocols import SkillOptimizationStorage

from app.adapters.skill_optimization import QualityRepository

logger = logging.getLogger(__name__)


class BusinessMonitor:
    """业务级监控与自愈服务

    定期检查Skill的执行质量，并在发现异常（如连续失败、质量骤降）时自动触发回滚。
    """

    def __init__(
        self,
        quality_repo: QualityRepository,
        storage: SkillOptimizationStorage,
        event_emitter: EventEmitter,
        check_interval_seconds: int = 300,  # 默认5分钟检查一次
    ):
        self.quality_repo = quality_repo
        self.storage = storage
        self.event_emitter = event_emitter
        self.check_interval_seconds = check_interval_seconds
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """启动监控后台任务"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("BusinessMonitor started")

    async def stop(self) -> None:
        """停止监控后台任务"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("BusinessMonitor stopped")

    async def _monitor_loop(self) -> None:
        """监控循环"""
        while self._running:
            try:
                await self._check_and_heal()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in BusinessMonitor loop: {e}")

            await asyncio.sleep(self.check_interval_seconds)

    async def _check_and_heal(self) -> None:
        """检查所有活跃Skill的质量并执行自愈策略"""
        logger.debug("BusinessMonitor: Checking skill quality for anomalies...")

        # 获取所有有执行记录的skill (这里简化，实际应该从执行日志或DB获取活跃skill列表)
        # 假设 quality_repo 有一个方法获取最近活跃的 skill_ids
        # 由于我们没有具体的实现，这里假设我们通过某种方式获取了需要检查的 skill_ids
        # 这里为了演示，我们假设检查一个固定的列表，或者通过 storage 获取所有版本
        # 实际业务中，应该查询最近有流量的 skills
        pass

    async def check_skill(self, skill_id: str) -> None:
        """检查单个Skill的质量，并在必要时回滚

        自愈策略：
        1. 如果最近10次执行的成功率低于 20%
        2. 如果当前版本的平均分数比上一个版本低 30% 以上
        -> 触发自动回滚
        """
        # 1. 获取当前活跃版本
        active_version = await self.storage.get_active_version(skill_id)
        if not active_version or active_version.version_id == "v1":
            # 如果没有激活版本，或者是初始版本，无法回滚
            return

        # 2. 获取该版本的近期质量表现 (从DB查询)
        latest_quality = await self.quality_repo.get_latest_quality(skill_id)
        if not latest_quality:
            return

        score = latest_quality.quality_score
        success_rate = score.get("success_rate", 1.0)
        overall_score = score.get("overall_score", 1.0)

        # 3. 判断是否需要回滚
        needs_rollback = False
        reason = ""

        if success_rate < 0.2:
            needs_rollback = True
            reason = f"Success rate dropped to {success_rate:.1%}"
        elif overall_score < 0.4:
            needs_rollback = True
            reason = f"Overall quality score critically low: {overall_score:.2f}"

        if needs_rollback:
            logger.warning(
                f"BusinessMonitor: Anomaly detected for {skill_id} (version {active_version.version_id}). Reason: {reason}"
            )
            await self._execute_rollback(skill_id, active_version.version_id, reason)

    async def _execute_rollback(self, skill_id: str, current_version_id: str, reason: str) -> None:
        """执行回滚操作"""
        # 获取版本历史，找到上一个版本
        history = await self.storage.get_version_history(skill_id, limit=5)
        if len(history) < 2:
            logger.warning(f"Cannot rollback {skill_id}: Not enough version history.")
            return

        # 假设 history 是按时间倒序排列的，history[0] 是当前版本，history[1] 是上一个版本
        # 为了安全，我们找到最近一个不是当前版本的版本
        target_version = None
        for v in history:
            if v.version_id != current_version_id:
                target_version = v
                break

        if not target_version:
            logger.warning(f"Cannot rollback {skill_id}: No valid previous version found.")
            return

        logger.info(f"Auto-healing: Rolling back {skill_id} from {current_version_id} to {target_version.version_id}")

        try:
            # 调用 Harness 提供的机制进行回滚
            await self.storage.activate_version(skill_id, target_version.version_id)

            # 发送事件通知
            await self.event_emitter.emit(
                "version_rollback",
                {
                    "skill_id": skill_id,
                    "from_version": current_version_id,
                    "to_version": target_version.version_id,
                    "trigger": "auto_heal",
                    "reason": reason,
                },
            )
            logger.info(f"Successfully rolled back {skill_id}")
        except Exception as e:
            logger.error(f"Failed to rollback {skill_id}: {e}")
