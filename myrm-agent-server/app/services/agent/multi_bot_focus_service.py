"""Service mediating multi-bot viewport focus tracking, anti-thrash compaction, and stream lifecycle (Item 42).

[INPUT]
- UpdateBotFocusRequest, EvaluateCompactionRequest, RecordCompactionRequest,
  CardHeartbeatRequest, PruneAbandonedStreamsRequest.

[OUTPUT]
- MultiBotFocusService managing thread-safe focus scores, compaction hysteresis,
  and dead stream card pruning.

[POS]
- Service layer for Multi-Bot Mention Focus & Anti-Thrash Compaction Guard.
"""

from __future__ import annotations

import logging
import threading

from myrm_agent_harness.agent.coordination.multi_bot_focus import (
    BotFocusSnapshot,
    CompactionEvaluation,
    CompactionPolicy,
    MultiBotFocusAndCompactionGuard,
    StreamCardHeartbeat,
    StreamCardState,
)

from app.schemas.multi_bot_focus import (
    BotFocusSnapshotDTO,
    CompactionEvaluationDTO,
    CompactionPolicyDTO,
    FocusedBotResponse,
    StreamCardHeartbeatDTO,
    StreamCardStateEnum,
)

logger = logging.getLogger(__name__)


def _snapshot_to_dto(snap: BotFocusSnapshot) -> BotFocusSnapshotDTO:
    return BotFocusSnapshotDTO(
        bot_id=snap.bot_id,
        is_viewport_active=snap.is_viewport_active,
        last_active_turn=snap.last_active_turn,
        focus_score=snap.focus_score,
        updated_at=snap.updated_at,
    )


def _policy_from_dto(dto: CompactionPolicyDTO | None) -> CompactionPolicy | None:
    if dto is None:
        return None
    return CompactionPolicy(
        trigger_threshold_ratio=dto.trigger_threshold_ratio,
        target_threshold_ratio=dto.target_threshold_ratio,
        cooldown_turns=dto.cooldown_turns,
        min_token_delta=dto.min_token_delta,
    )


def _eval_to_dto(evaluation: CompactionEvaluation) -> CompactionEvaluationDTO:
    return CompactionEvaluationDTO(
        should_compact=evaluation.should_compact,
        reason=evaluation.reason,
        current_tokens=evaluation.current_tokens,
        max_context_tokens=evaluation.max_context_tokens,
        cooldown_remaining=evaluation.cooldown_remaining,
        evaluated_at=evaluation.evaluated_at,
    )


def _card_to_dto(card: StreamCardHeartbeat) -> StreamCardHeartbeatDTO:
    return StreamCardHeartbeatDTO(
        card_id=card.card_id,
        session_id=card.session_id,
        bot_id=card.bot_id,
        state=StreamCardStateEnum(card.state.value),
        last_heartbeat_at=card.last_heartbeat_at,
    )


class MultiBotFocusService:
    """Thread-safe application service coordinating multi-bot focus and compaction."""

    def __init__(self) -> None:
        self._guard = MultiBotFocusAndCompactionGuard()
        self._lock = threading.Lock()

    def update_bot_focus(
        self,
        session_id: str,
        bot_id: str,
        is_viewport_active: bool,
        turn_index: int,
    ) -> BotFocusSnapshotDTO:
        with self._lock:
            snap = self._guard.update_bot_focus(
                session_id=session_id,
                bot_id=bot_id,
                is_viewport_active=is_viewport_active,
                turn_index=turn_index,
            )
            return _snapshot_to_dto(snap)

    def get_focused_bot(self, session_id: str) -> FocusedBotResponse:
        with self._lock:
            focused_id = self._guard.get_focused_bot(session_id)
            snapshots = self._guard.get_all_focus_snapshots(session_id)
            return FocusedBotResponse(
                session_id=session_id,
                focused_bot_id=focused_id,
                snapshots=[_snapshot_to_dto(s) for s in snapshots],
            )

    def evaluate_compaction(
        self,
        session_id: str,
        current_tokens: int,
        max_context_tokens: int,
        current_turn: int,
        policy_dto: CompactionPolicyDTO | None = None,
    ) -> CompactionEvaluationDTO:
        with self._lock:
            domain_policy = _policy_from_dto(policy_dto)
            result = self._guard.evaluate_compaction(
                session_id=session_id,
                current_tokens=current_tokens,
                max_context_tokens=max_context_tokens,
                current_turn=current_turn,
                policy=domain_policy,
            )
            return _eval_to_dto(result)

    def record_compaction_executed(
        self,
        session_id: str,
        executed_turn: int,
        tokens_after: int,
    ) -> None:
        with self._lock:
            self._guard.record_compaction_executed(
                session_id=session_id,
                executed_turn=executed_turn,
                tokens_after=tokens_after,
            )

    def record_card_heartbeat(
        self,
        card_id: str,
        session_id: str,
        bot_id: str,
        state: StreamCardStateEnum = StreamCardStateEnum.STREAMING,
    ) -> StreamCardHeartbeatDTO:
        with self._lock:
            domain_state = StreamCardState(state.value)
            card = self._guard.record_card_heartbeat(
                card_id=card_id,
                session_id=session_id,
                bot_id=bot_id,
                state=domain_state,
            )
            return _card_to_dto(card)

    def detect_and_prune_abandoned_streams(
        self,
        session_id: str,
        timeout_seconds: float = 30.0,
    ) -> list[str]:
        with self._lock:
            return self._guard.detect_and_prune_abandoned_streams(
                session_id=session_id,
                timeout_seconds=timeout_seconds,
            )

    def get_card(self, card_id: str) -> StreamCardHeartbeatDTO | None:
        with self._lock:
            card = self._guard.get_card(card_id)
            if card is None:
                return None
            return _card_to_dto(card)

    def mark_card_completed(self, card_id: str) -> bool:
        with self._lock:
            return self._guard.mark_card_completed(card_id)


_global_focus_service = MultiBotFocusService()


def get_multi_bot_focus_service() -> MultiBotFocusService:
    """Retrieve global singleton MultiBotFocusService instance."""
    return _global_focus_service
