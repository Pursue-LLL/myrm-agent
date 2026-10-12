"""Live Correction Service wrapping harness pipeline for server endpoints.

[POS]
Server-side business service wrapping harness LiveCorrectionOrchestrator.
Strictly typed, zero Any, and imports exclusively from harness memory top-level exports.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from myrm_agent_harness.toolkits.memory import (
    CorrectionAckReceipt,
    CorrectionTargetLocalizer,
    LiveCorrectionMutationResult,
    LiveCorrectionOrchestrator,
    NaturalLanguageCorrectionDetector,
    TargetNodeCandidate,
)

logger = logging.getLogger(__name__)


class LiveCorrectionService:
    """Business service managing memory candidate pool and live feedback correction pipeline."""

    def __init__(self) -> None:
        self._candidates: Dict[str, TargetNodeCandidate] = {}
        self._detector = NaturalLanguageCorrectionDetector()
        self._localizer = CorrectionTargetLocalizer(match_threshold=0.3)
        self._orchestrator = LiveCorrectionOrchestrator(
            detector=self._detector,
            localizer=self._localizer,
        )
        self.seed_default_candidates()

    def seed_default_candidates(self) -> None:
        """Seed realistic memory candidates into the active memory pool for instant demonstration."""
        seeds: List[TargetNodeCandidate] = [
            TargetNodeCandidate(
                memory_id="mem_pref_beverage",
                content="用户早晨和下午喜欢饮用 美式咖啡（不加糖奶）",
                cube_id="user_preference",
                match_score=1.0,
                attributes={"category": "preference", "status": "active"},
            ),
            TargetNodeCandidate(
                memory_id="mem_fact_database",
                content="系统主业务存储架构采用 MySQL 8.0 主从副本集群",
                cube_id="architecture_facts",
                match_score=1.0,
                attributes={"category": "fact", "status": "active"},
            ),
            TargetNodeCandidate(
                memory_id="mem_rule_commit",
                content="Git 提交前允许直接在 main 分支提交代码并推送",
                cube_id="engineering_rules",
                match_score=1.0,
                attributes={"category": "rule", "status": "active"},
            ),
            TargetNodeCandidate(
                memory_id="mem_cred_api_token",
                content="测试环境第三方集成 API Key 凭证为 test_sec_abc12345",
                cube_id="ephemeral_keys",
                match_score=1.0,
                attributes={"category": "secret", "status": "deprecated"},
            ),
        ]
        for c in seeds:
            self._candidates[c.memory_id] = c

    def add_candidate(
        self,
        memory_id: str,
        content: str,
        cube_id: Optional[str] = None,
        attributes: Optional[Dict[str, str]] = None,
    ) -> TargetNodeCandidate:
        """Register or update a candidate memory item into the service pool."""
        candidate = TargetNodeCandidate(
            memory_id=memory_id,
            content=content,
            cube_id=cube_id,
            match_score=1.0,
            attributes=attributes or {},
        )
        self._candidates[memory_id] = candidate
        logger.info("Added candidate memory item '%s'", memory_id)
        return candidate

    def list_candidates(self) -> List[TargetNodeCandidate]:
        """Return all active candidate memory items in the pool."""
        return list(self._candidates.values())

    def get_candidate(self, memory_id: str) -> Optional[TargetNodeCandidate]:
        """Retrieve a specific candidate memory item by ID."""
        return self._candidates.get(memory_id)

    def process_utterance(
        self,
        utterance: str,
        candidates: Optional[List[TargetNodeCandidate]] = None,
    ) -> Optional[CorrectionAckReceipt]:
        """Process conversational utterance and execute atomic mutation if correction detected."""
        active_candidates = (
            candidates if candidates is not None else list(self._candidates.values())
        )
        receipt = self._orchestrator.process_utterance(
            utterance=utterance,
            candidates=active_candidates,
        )

        if receipt is not None and receipt.mutated_record is not None:
            mutation = receipt.mutated_record
            # Update internal candidate pool in-memory state
            if mutation.target_memory_id and mutation.target_memory_id in self._candidates:
                if mutation.new_content:
                    old_cand = self._candidates[mutation.target_memory_id]
                    updated = TargetNodeCandidate(
                        memory_id=mutation.new_memory_id or mutation.target_memory_id,
                        content=mutation.new_content,
                        cube_id=old_cand.cube_id,
                        match_score=1.0,
                        attributes={**old_cand.attributes, "superseded_from": mutation.target_memory_id},
                    )
                    self._candidates.pop(mutation.target_memory_id, None)
                    self._candidates[updated.memory_id] = updated
                else:
                    # Retraction
                    self._candidates.pop(mutation.target_memory_id, None)
            elif mutation.new_memory_id and mutation.new_content:
                # Novel creation
                novel = TargetNodeCandidate(
                    memory_id=mutation.new_memory_id,
                    content=mutation.new_content,
                    cube_id="dynamic_corrections",
                    match_score=1.0,
                    attributes={"source": "live_correction"},
                )
                self._candidates[novel.memory_id] = novel

        return receipt

    def get_history(self) -> List[LiveCorrectionMutationResult]:
        """Return history of all mutations executed by orchestrator mutator."""
        return self._orchestrator.mutator.history

    def clear_all(self) -> None:
        """Reset service candidates and history (for isolated test teardowns)."""
        self._candidates.clear()
        self._orchestrator.mutator._history.clear()


_SERVICE_INSTANCE: Optional[LiveCorrectionService] = None


def get_live_correction_service() -> LiveCorrectionService:
    """Return singleton instance of LiveCorrectionService."""
    global _SERVICE_INSTANCE
    if _SERVICE_INSTANCE is None:
        _SERVICE_INSTANCE = LiveCorrectionService()
    return _SERVICE_INSTANCE
