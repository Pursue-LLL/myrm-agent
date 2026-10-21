"""[INPUT] SubagentConfigMigrationRequest, WatermarkHeartbeatRequest.
[OUTPUT] SubagentScalingService managing configuration zero-disruption upgrade and 80% watermark heartbeats.
[POS] Service layer for Subagent Concurrency & Tool Budget Adaptive Scaling (Item 31).
"""

from __future__ import annotations

import logging
import threading
from typing import cast

from myrm_agent_harness.agent.sub_agents.budget_scaling import (
    ConfigUpgradeMigrator,
    SubagentWatermarkGuard,
)

from app.schemas.subagent_scaling import (
    ConfigScalar,
    SubagentConfigMigrationRequest,
    SubagentConfigMigrationResponse,
    WatermarkAlertItem,
    WatermarkAlertListResponse,
    WatermarkHeartbeatRequest,
    WatermarkHeartbeatResponse,
)

logger = logging.getLogger(__name__)


class SubagentScalingService:
    """Session-isolated coordinator for subagent budget scaling and watermark heartbeats."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._watermark_guard = SubagentWatermarkGuard()
        self._alerts: dict[str, list[WatermarkAlertItem]] = {}

    def migrate_configuration(
        self,
        req: SubagentConfigMigrationRequest,
    ) -> SubagentConfigMigrationResponse:
        """Evaluate and smoothly upgrade subagent quotas without disrupting user configs."""
        raw_dict: dict[str, object] = dict(req.extra_config)
        if req.concurrency_limit is not None:
            raw_dict["concurrency_limit"] = req.concurrency_limit
        if req.max_turns is not None:
            raw_dict["max_turns"] = req.max_turns
        if req.max_children_per_agent is not None:
            raw_dict["max_children_per_agent"] = req.max_children_per_agent
        if req.max_descendants_per_run is not None:
            raw_dict["max_descendants_per_run"] = req.max_descendants_per_run

        migrated_dict, result = ConfigUpgradeMigrator.migrate_config_dict(raw_dict)

        final_config: dict[str, ConfigScalar] = {
            k: cast(ConfigScalar, v) for k, v in migrated_dict.items()
        }

        logger.info(
            "Subagent config migration evaluated: migrated=%s, concurrency=%s->%s, turns=%s->%s",
            result.migrated,
            result.old_concurrency,
            result.new_concurrency,
            result.old_max_turns,
            result.new_max_turns,
        )

        return SubagentConfigMigrationResponse(
            migrated=result.migrated,
            old_concurrency=result.old_concurrency,
            new_concurrency=result.new_concurrency,
            old_max_turns=result.old_max_turns,
            new_max_turns=result.new_max_turns,
            concurrency_migrated=result.concurrency_migrated,
            max_turns_migrated=result.max_turns_migrated,
            reasons=list(result.reasons),
            final_config=final_config,
            timestamp=result.timestamp,
        )

    def process_heartbeat(
        self,
        req: WatermarkHeartbeatRequest,
    ) -> WatermarkHeartbeatResponse:
        """Process turn heartbeat and emit a pre-warning alert if the 80% watermark is crossed."""
        usage_ratio = round(req.current_turn / req.max_turns, 4)
        turns_remaining = max(0, req.max_turns - req.current_turn)

        alert = self._watermark_guard.record_turn_and_check(
            task_id=req.subagent_id,
            current_turn=req.current_turn,
            max_turns=req.max_turns,
        )

        is_triggered = alert is not None
        alert_msg = alert.warning_message if alert else None

        if is_triggered and alert is not None:
            with self._lock:
                if req.session_id not in self._alerts:
                    self._alerts[req.session_id] = []

                item = WatermarkAlertItem(
                    session_id=req.session_id,
                    subagent_id=req.subagent_id,
                    subagent_name=req.subagent_name,
                    current_turn=req.current_turn,
                    max_turns=req.max_turns,
                    usage_ratio=usage_ratio,
                    turns_remaining=turns_remaining,
                    warning_message=alert.warning_message,
                )
                self._alerts[req.session_id].append(item)

            logger.warning(
                "Watermark alert triggered for session %s, subagent %s (%s): %s",
                req.session_id,
                req.subagent_id,
                req.subagent_name,
                alert.warning_message,
            )

        return WatermarkHeartbeatResponse(
            session_id=req.session_id,
            subagent_id=req.subagent_id,
            current_turn=req.current_turn,
            max_turns=req.max_turns,
            usage_ratio=usage_ratio,
            turns_remaining=turns_remaining,
            is_alert_triggered=is_triggered,
            alert_message=alert_msg,
        )

    def get_alerts(self, session_id: str) -> WatermarkAlertListResponse:
        """Retrieve recorded watermark alerts for a specific session."""
        with self._lock:
            alerts = list(self._alerts.get(session_id, []))
        return WatermarkAlertListResponse(
            session_id=session_id,
            alerts=alerts,
            count=len(alerts),
        )

    def dismiss_alert(self, session_id: str, subagent_id: str) -> bool:
        """Dismiss an active watermark alert in the supervision list."""
        with self._lock:
            alerts = self._alerts.get(session_id, [])
            updated = False
            for idx, a in enumerate(alerts):
                if a.subagent_id == subagent_id and a.status == "active":
                    alerts[idx] = WatermarkAlertItem(
                        session_id=a.session_id,
                        subagent_id=a.subagent_id,
                        subagent_name=a.subagent_name,
                        current_turn=a.current_turn,
                        max_turns=a.max_turns,
                        usage_ratio=a.usage_ratio,
                        turns_remaining=a.turns_remaining,
                        status="dismissed",
                        warning_message=a.warning_message,
                        timestamp=a.timestamp,
                    )
                    updated = True
            return updated

    def expand_budget(
        self,
        session_id: str,
        subagent_id: str,
    ) -> bool:
        """Mark alert as expanded and reset guard so further execution can proceed safely."""
        with self._lock:
            self._watermark_guard.clear_task(subagent_id)
            alerts = self._alerts.get(session_id, [])
            updated = False
            for idx, a in enumerate(alerts):
                if a.subagent_id == subagent_id and a.status != "expanded":
                    alerts[idx] = WatermarkAlertItem(
                        session_id=a.session_id,
                        subagent_id=a.subagent_id,
                        subagent_name=a.subagent_name,
                        current_turn=a.current_turn,
                        max_turns=a.max_turns,
                        usage_ratio=a.usage_ratio,
                        turns_remaining=a.turns_remaining,
                        status="expanded",
                        warning_message=a.warning_message,
                        timestamp=a.timestamp,
                    )
                    updated = True
            return updated

    def cleanup_session(self, session_id: str) -> bool:
        """Clean up alerts and guard memory when a parent session terminates."""
        with self._lock:
            if session_id in self._alerts:
                for alert in self._alerts[session_id]:
                    self._watermark_guard.clear_task(alert.subagent_id)
                del self._alerts[session_id]
                logger.info("Cleaned up subagent scaling state for session %s", session_id)
                return True
        return False


_instance: SubagentScalingService | None = None


def get_subagent_scaling_service() -> SubagentScalingService:
    """Singleton getter for SubagentScalingService."""
    global _instance
    if _instance is None:
        _instance = SubagentScalingService()
    return _instance
