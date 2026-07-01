"""A/B Test Manager

影子测试闭环的中枢控制器。统一管理：
1. 采样率决策（分歧100%保留 / 一致20%采样）
2. 托管队列（asyncio.Queue + worker pool + 重试 + 优雅关机）
3. 统一数据流（ShadowTester返回结果 → Manager存储到DB）
4. Auto-Promote（达标自动转正 + 通知）
"""

import asyncio
import logging
import random
from typing import TypedDict

from myrm_agent_harness.agent.streaming.broadcast.types import ToolCallEventData

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus
from app.services.skill_optimization.shadow_tester import ShadowTester, ShadowTestResult

logger = logging.getLogger(__name__)


class ShadowTaskData(TypedDict):
    """影子测试任务数据（队列消息格式）"""

    skill_id: str
    test_id: str
    baseline_version: int
    candidate_version: int
    inputs: dict[str, object]
    baseline_result: dict[str, object]
    baseline_duration: float
    sample_size: int
    target_sample_size: int


_DEFAULT_MAX_WORKERS = 3
_DEFAULT_MAX_QUEUE_SIZE = 100
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_SHADOW_TIMEOUT = 120.0
_DEFAULT_CONSISTENT_SAMPLE_RATE = 0.2
_DEFAULT_MAX_SAMPLES_PER_TEST = 200
_DEFAULT_AUTO_PROMOTE_THRESHOLD = 0.95
_DEFAULT_MAX_LATENCY_RATIO = 1.2


class ABTestManager:
    """A/B测试管理器

    托管队列 + 统一数据流 + 采样率 + Auto-Promote
    """

    def __init__(
        self,
        storage: SQLAlchemyStorage,
        shadow_tester: ShadowTester,
        max_workers: int = _DEFAULT_MAX_WORKERS,
        max_queue_size: int = _DEFAULT_MAX_QUEUE_SIZE,
        max_retries: int = _DEFAULT_MAX_RETRIES,
        shadow_timeout: float = _DEFAULT_SHADOW_TIMEOUT,
        consistent_sample_rate: float = _DEFAULT_CONSISTENT_SAMPLE_RATE,
        max_samples_per_test: int = _DEFAULT_MAX_SAMPLES_PER_TEST,
        auto_promote_enabled: bool = True,
        auto_promote_threshold: float = _DEFAULT_AUTO_PROMOTE_THRESHOLD,
        max_latency_ratio: float = _DEFAULT_MAX_LATENCY_RATIO,
    ):
        self.storage = storage
        self.shadow_tester = shadow_tester

        self._max_workers = max_workers
        self._max_retries = max_retries
        self._shadow_timeout = shadow_timeout
        self._consistent_sample_rate = consistent_sample_rate
        self._max_samples_per_test = max_samples_per_test
        self._auto_promote_enabled = auto_promote_enabled
        self._auto_promote_threshold = auto_promote_threshold
        self._max_latency_ratio = max_latency_ratio

        self._queue: asyncio.Queue[ShadowTaskData] = asyncio.Queue(maxsize=max_queue_size)
        self._workers: list[asyncio.Task[None]] = []
        self._running = False
        self._consistent_counts: dict[str, int] = {}

    async def start(self) -> None:
        """启动 worker pool"""
        if self._running:
            return
        self._running = True
        for i in range(self._max_workers):
            task = asyncio.create_task(self._worker(i), name=f"shadow-worker-{i}")
            self._workers.append(task)
        logger.info(f"ABTestManager started with {self._max_workers} workers")

    async def shutdown(self) -> None:
        """优雅关机：等待队列清空后停止"""
        if not self._running:
            return
        self._running = False
        logger.info("ABTestManager shutting down, waiting for queue to drain...")
        await self._queue.join()
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("ABTestManager shutdown complete")

    async def handle_tool_completion(self, event: ToolCallEventData) -> None:
        """处理工具执行结束事件"""
        if event.status != "completed":
            return

        skill_id = event.tool_name
        if not skill_id or event.version is None:
            return

        try:
            async with self.storage._get_session() as session:
                from app.adapters.skill_optimization.ab_test_repo import ABTestRepository

                ab_repo = ABTestRepository(session)
                running_tests = await ab_repo.get_running_tests()
                matching_test = next((t for t in running_tests if t.skill_id == skill_id), None)

                if not matching_test:
                    return

                is_candidate_run = event.version == matching_test.candidate_version
                shadow_version = matching_test.baseline_version if is_candidate_run else matching_test.candidate_version

                task_data: ShadowTaskData = {
                    "skill_id": skill_id,
                    "test_id": matching_test.id,
                    "baseline_version": event.version if not is_candidate_run else shadow_version,
                    "candidate_version": event.version if is_candidate_run else shadow_version,
                    "inputs": event.args or {},
                    "baseline_result": ({"status": "success", "result": event.result} if not is_candidate_run else {}),
                    "baseline_duration": event.duration_ms / 1000.0 if event.duration_ms else 0.0,
                    "sample_size": matching_test.sample_size,
                    "target_sample_size": self._max_samples_per_test,
                }

                try:
                    self._queue.put_nowait(task_data)
                    logger.info(f"Queued shadow test for {skill_id}: v{event.version} vs v{shadow_version}")
                except asyncio.QueueFull:
                    logger.warning(f"Shadow test queue full, dropping test for {skill_id}")

        except Exception as e:
            logger.error(f"Failed to handle tool completion for A/B testing: {e}")

    async def promote_version(self, skill_id: str, version: int) -> bool:
        """提升某个版本为Master版本"""
        try:
            async with self.storage._get_session() as session:
                from app.adapters.skill_optimization.ab_test_repo import ABTestRepository
                from app.adapters.skill_optimization.snapshot_repo import SnapshotRepository

                ab_repo = ABTestRepository(session)
                snapshot_repo = SnapshotRepository(session)

                skill_version = await snapshot_repo.get_version(skill_id, version)
                if skill_version is None:
                    raise ValueError(f"Version {version} not found for skill {skill_id}")

                running_tests = await ab_repo.get_running_tests()
                for test in running_tests:
                    if test.skill_id == skill_id:
                        winner = "candidate" if version == test.candidate_version else "baseline"
                        status = "CANDIDATE_WIN" if winner == "candidate" else "BASELINE_WIN"
                        await ab_repo.update_status(test_id=test.id, status=status, winner=winner)

                await session.commit()

            from app.services.skill_optimization.skill_version_sync import activate_version_with_disk_sync

            await activate_version_with_disk_sync(self.storage, skill_id, version)

            self._consistent_counts.pop(skill_id, None)
            logger.info(f"Version v{version} promoted to Master for skill {skill_id}")

            try:
                get_event_bus().publish(AppEvent(event_type=AppEventType.SKILL_AB_TEST_UPDATED))
            except Exception as e:
                logger.debug(f"Failed to emit AB test update event: {e}")

            return True
        except Exception as e:
            logger.error(f"Failed to promote version {version} for {skill_id}: {e}")
            return False

    async def _worker(self, worker_id: int) -> None:
        """Worker: 从队列消费并执行影子测试"""
        while self._running:
            try:
                task_data = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except (asyncio.TimeoutError, TimeoutError):
                continue
            except asyncio.CancelledError:
                break

            try:
                await self._execute_with_retry(task_data, worker_id)
            except Exception as e:
                logger.error(f"Worker-{worker_id} unhandled error: {e}")
            finally:
                self._queue.task_done()

    async def _execute_with_retry(self, task_data: ShadowTaskData, worker_id: int) -> None:
        """带重试的影子测试执行"""
        skill_id = task_data["skill_id"]

        for attempt in range(self._max_retries):
            try:
                result = await asyncio.wait_for(
                    self.shadow_tester.run_shadow_test(
                        skill_id=skill_id,
                        baseline_version=task_data["baseline_version"],
                        candidate_version=task_data["candidate_version"],
                        inputs=task_data["inputs"],
                        baseline_result=task_data["baseline_result"],
                        baseline_duration=task_data["baseline_duration"],
                    ),
                    timeout=self._shadow_timeout,
                )

                if self._should_store_sample(result, task_data["test_id"]):
                    await self._store_result(result, task_data["test_id"])
                else:
                    await self._update_stats_without_sample(result, task_data["test_id"])

                await self._check_auto_promote(task_data)
                return

            except (asyncio.TimeoutError, TimeoutError):
                logger.warning(
                    f"Worker-{worker_id} shadow test timeout for {skill_id} (attempt {attempt + 1}/{self._max_retries})"
                )
            except Exception as e:
                logger.error(
                    f"Worker-{worker_id} shadow test error for {skill_id} (attempt {attempt + 1}/{self._max_retries}): {e}"
                )

            if attempt < self._max_retries - 1:
                delay = min(2**attempt + random.uniform(0, 1), 10.0)
                await asyncio.sleep(delay)

        logger.error(f"Shadow test for {skill_id} failed after {self._max_retries} retries")

    def _should_store_sample(self, result: ShadowTestResult, test_id: str) -> bool:
        """采样率决策：分歧100%保留，一致样本按比例采样"""
        if not result.comparison.is_match:
            return True

        count_key = test_id
        self._consistent_counts.setdefault(count_key, 0)
        self._consistent_counts[count_key] += 1

        if self._consistent_counts[count_key] <= 20:
            return True

        return random.random() < self._consistent_sample_rate

    async def _store_result(self, result: ShadowTestResult, test_id: str) -> None:
        """统一存储影子测试结果到DB"""
        try:
            async with self.storage._get_session() as session:
                from app.adapters.skill_optimization.ab_test_repo import ABTestRepository

                ab_repo = ABTestRepository(session)

                await ab_repo.atomic_increment_sample_size(test_id)

                test = await ab_repo.get_by_id(test_id)
                if test:
                    score = test.candidate_score or {"success_rate": 0.0, "avg_latency": 0.0}
                    total = test.sample_size
                    if total > 0:
                        old_lat = score.get("avg_latency", 0.0)
                        score["avg_latency"] = (old_lat * (total - 1) + result.candidate_duration) / total

                        match_val = 1.0 if result.comparison.is_match else 0.0
                        old_rate = score.get("success_rate", 0.0)
                        score["success_rate"] = (old_rate * (total - 1) + match_val) / total

                    await ab_repo.update_status(test_id=test_id, status="RUNNING", candidate_score=score)

                await ab_repo.add_shadow_sample(
                    test_id=test_id,
                    skill_id=result.skill_id,
                    inputs=result.inputs,
                    baseline_output=result.baseline_result,
                    candidate_output=result.candidate_result,
                    is_match=result.comparison.is_match,
                    similarity_score=result.comparison.similarity_score,
                    baseline_latency_ms=result.baseline_duration * 1000.0,
                    candidate_latency_ms=result.candidate_duration * 1000.0,
                    diff_summary=result.comparison.diff_summary,
                )

                await ab_repo.cap_samples_per_test(test_id, self._max_samples_per_test)

                # Emit AB test updated event
                try:
                    get_event_bus().publish(AppEvent(event_type=AppEventType.SKILL_AB_TEST_UPDATED))
                except Exception as e:
                    logger.debug(f"Failed to emit AB test update event: {e}")

        except Exception as e:
            logger.error(f"Failed to store shadow test result: {e}")

    async def _update_stats_without_sample(self, result: ShadowTestResult, test_id: str) -> None:
        """更新统计数据但不存储样本（未采样的一致样本）"""
        try:
            async with self.storage._get_session() as session:
                from app.adapters.skill_optimization.ab_test_repo import ABTestRepository

                ab_repo = ABTestRepository(session)
                await ab_repo.atomic_increment_sample_size(test_id)

                test = await ab_repo.get_by_id(test_id)
                if test:
                    score = test.candidate_score or {"success_rate": 0.0, "avg_latency": 0.0}
                    total = test.sample_size
                    if total > 0:
                        old_lat = score.get("avg_latency", 0.0)
                        score["avg_latency"] = (old_lat * (total - 1) + result.candidate_duration) / total

                        match_val = 1.0 if result.comparison.is_match else 0.0
                        old_rate = score.get("success_rate", 0.0)
                        score["success_rate"] = (old_rate * (total - 1) + match_val) / total

                    await ab_repo.update_status(test_id=test_id, status="RUNNING", candidate_score=score)

                try:
                    get_event_bus().publish(AppEvent(event_type=AppEventType.SKILL_AB_TEST_UPDATED))
                except Exception as e:
                    logger.debug(f"Failed to emit AB test update event: {e}")
        except Exception as e:
            logger.error(f"Failed to update stats: {e}")

    async def _check_auto_promote(self, task_data: ShadowTaskData) -> None:
        """检查Auto-Promote条件"""
        if not self._auto_promote_enabled:
            return

        test_id = task_data["test_id"]
        target = task_data.get("target_sample_size", self._max_samples_per_test)

        try:
            async with self.storage._get_session() as session:
                from app.adapters.skill_optimization.ab_test_repo import ABTestRepository

                ab_repo = ABTestRepository(session)
                test = await ab_repo.get_by_id(test_id)

                if not test or test.status != "RUNNING":
                    return

                if test.sample_size < target:
                    return

                score = test.candidate_score or {}
                success_rate = score.get("success_rate", 0.0)
                avg_latency = score.get("avg_latency", 0.0)

                if success_rate < self._auto_promote_threshold:
                    logger.info(
                        f"Auto-promote skipped for {test.skill_id}: "
                        f"success_rate={success_rate:.2%} < {self._auto_promote_threshold:.2%}"
                    )
                    return

                baseline_latency = task_data.get("baseline_duration", 0.0)
                if baseline_latency > 0 and avg_latency > baseline_latency * self._max_latency_ratio:
                    logger.info(
                        f"Auto-promote skipped for {test.skill_id}: "
                        f"latency regression {avg_latency:.2f}s > {baseline_latency * self._max_latency_ratio:.2f}s"
                    )
                    return

                logger.info(
                    f"Auto-promoting {test.skill_id} v{test.candidate_version}: "
                    f"samples={test.sample_size}, success_rate={success_rate:.2%}"
                )
                await self.promote_version(test.skill_id, test.candidate_version)

                await self.shadow_tester.event_emitter.emit(
                    "auto_promote",
                    {
                        "skill_id": test.skill_id,
                        "version": test.candidate_version,
                        "success_rate": success_rate,
                        "sample_size": test.sample_size,
                    },
                )

        except Exception as e:
            logger.error(f"Auto-promote check failed: {e}")
