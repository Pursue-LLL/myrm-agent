"""Multi-tier memory scheduler: policy-based write dispatch and tamper-checked envelope import.

[INPUT]
- myrm_agent_harness.toolkits.memory.types::BaseMemory (POS: Memory type system foundation)
- myrm_agent_harness.toolkits.memory.cube::MemCubeEnvelope (POS: 统一记忆容器契约层。为异构记忆提供标准元数据头、防篡改签名与跨端传输标准。)
- myrm_agent_harness.toolkits.memory.cube::StoragePolicy (POS: 统一记忆容器契约层。为异构记忆提供标准元数据头、防篡改签名与跨端传输标准。)

[OUTPUT]
- MultiTierMemoryScheduler: 多层记忆调度引擎，按存储策略分发写入，并在导入信封时执行防篡改校验

[POS]
多层记忆调度层。按 StoragePolicy 决定写入走 MemoryManager 还是跳过，负责信封的防篡改恢复落库。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory.cube import (
    LifecycleTier,
    MemCubeEnvelope,
    StoragePolicy,
    infer_tier_and_policy,
    unwrap_envelope,
)
from myrm_agent_harness.toolkits.memory.types import BaseMemory

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

logger = logging.getLogger(__name__)


class MultiTierMemoryScheduler:
    """Unified scheduler coordinating L1/L2/L3 memories and dispatching storage targets."""

    def __init__(self, memory_manager: MemoryManager | None = None) -> None:
        self._manager = memory_manager

    @property
    def manager(self) -> MemoryManager | None:
        return self._manager

    async def dispatch_store(
        self,
        memory: BaseMemory,
        tier: LifecycleTier | None = None,
        policy: StoragePolicy | None = None,
    ) -> bool:
        """Write a memory according to its storage policy; return whether it was handled.

        EPHEMERAL memories are never persisted. RELATIONAL and VECTOR memories are written
        through ``MemoryManager.store``. Any other policy (GRAPH has no write target) is not
        dispatched.
        """
        resolved_tier, resolved_policy = infer_tier_and_policy(memory)
        tier = tier or resolved_tier
        policy = policy or resolved_policy

        if self._manager is None:
            logger.debug("[SCHEDULER] No memory manager attached, dispatch skipped")
            return False

        if policy == StoragePolicy.EPHEMERAL:
            logger.debug("[SCHEDULER] Ephemeral memory %s skipped from disk storage", memory.id)
            return True

        if policy in (StoragePolicy.RELATIONAL, StoragePolicy.VECTOR):
            try:
                await self._manager.store(memory)
            except Exception as err:
                logger.warning("[SCHEDULER] %s dispatch failed for %s: %s", policy.value, memory.id, err)
                return False
            logger.debug("[SCHEDULER] Dispatched %s via %s policy", memory.id, policy.value)
            return True

        logger.warning("[SCHEDULER] No write target for %s policy, %s not dispatched", policy.value, memory.id)
        return False

    async def import_envelopes(
        self,
        envelopes: Sequence[MemCubeEnvelope[dict[str, object]] | dict[str, object]],
        verify_hashes: bool = True,
    ) -> tuple[int, int]:
        """Restore envelopes back into the appropriate storage tiers.

        Returns:
            tuple of (success_count, failure_or_tampered_count)
        """
        success = 0
        failed = 0

        for raw_env in envelopes:
            env: MemCubeEnvelope[dict[str, object]] = (
                raw_env
                if isinstance(raw_env, MemCubeEnvelope)
                else MemCubeEnvelope[dict[str, object]].model_validate(raw_env)
            )
            if verify_hashes and not env.verify_audit_hash():
                raise ValueError(f"Tamper detected: MemCube audit hash mismatch for {env.header.cube_id}")

            try:
                entity = unwrap_envelope(env)
                dispatched = await self.dispatch_store(
                    memory=entity,
                    tier=env.header.lifecycle_tier,
                    policy=env.header.storage_policy,
                )
                if dispatched:
                    success += 1
                else:
                    failed += 1
            except Exception as err:
                logger.warning("[SCHEDULER] Failed to restore cube %s: %s", env.header.cube_id, err)
                failed += 1

        logger.info("[SCHEDULER] Restored envelopes: %d succeeded, %d failed", success, failed)
        return success, failed
