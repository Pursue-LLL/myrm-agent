"""SkillEvolutionEngine batch evolution mixin.

[POS]
Concurrent evolve_multiple_concurrent entry for SkillEvolutionEngine.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionProposal,
    EvolutionRequest,
    EvolutionType,
)

logger = logging.getLogger(__name__)


class SkillEvolutionEngineBatchMixin:
    """The engine class supplies the semaphore and the evolution methods this mixin dispatches to."""

    _semaphore: asyncio.Semaphore

    if TYPE_CHECKING:

        async def fix_skill(
            self,
            skill_id: str,
            error_message: str,
            task_context: str | None = None,
            session_id: str | None = None,
        ) -> EvolutionProposal | None: ...

        async def derive_skill_simple(self, skill_id: str, user_feedback: str) -> EvolutionProposal | None: ...

        async def optimize_description(self, skill_id: str) -> EvolutionProposal | None: ...

    async def evolve_multiple_concurrent(self, requests: list[EvolutionRequest]) -> list[EvolutionProposal | None]:
        """Evolve multiple skills concurrently with rate limiting."""
        if not requests:
            return []

        async def _evolve_with_limit(req: EvolutionRequest) -> EvolutionProposal | None:
            async with self._semaphore:
                if req.evolution_type == EvolutionType.FIX:
                    return await self.fix_skill(req.skill_id or "", req.reason)
                elif req.evolution_type == EvolutionType.DERIVED:
                    return await self.derive_skill_simple(req.skill_id or "", req.user_feedback)
                elif req.evolution_type == EvolutionType.OPTIMIZE_DESCRIPTION:
                    return await self.optimize_description(req.skill_id or "")
                return None

        results = await asyncio.gather(*[_evolve_with_limit(req) for req in requests], return_exceptions=True)

        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Concurrent evolution request {i} failed: {result}")
                final_results.append(None)
            else:
                final_results.append(result)

        return final_results
