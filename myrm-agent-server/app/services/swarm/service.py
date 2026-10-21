"""[INPUT]
- Harness swarm: SwarmCoordinationEngine, SwarmModeConfig, SwarmSubagentTask, RecalledRuleItem, OwnerRiskItem

[OUTPUT]
- SwarmExecutionService: Singleton application service managing swarm execution, recalled rules and owner risk verifications

[POS]
Server service layer for Swarm Coordination, Memory Recall HUD & Owner Risk Checklist (Item 42 P0).
Strictly under 160 lines. Zero `Any`.
"""

from __future__ import annotations

import threading

from myrm_agent_harness.toolkits.swarm import (
    OwnerRiskItem,
    RecalledRuleItem,
    SwarmCoordinationEngine,
    SwarmModeConfig,
    SwarmSubagentTask,
)


class SwarmExecutionService:
    """Thread-safe application service coordinating swarm execution, memory rule recalls and owner risk verification."""

    _instance: SwarmExecutionService | None = None
    _singleton_lock = threading.Lock()

    def __init__(self) -> None:
        self._engine = SwarmCoordinationEngine()

    @classmethod
    def get_instance(cls) -> SwarmExecutionService:
        """Returns the process-wide singleton instance."""
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get_swarm_config(self, session_id: str) -> SwarmModeConfig:
        return self._engine.get_config(session_id)

    def set_swarm_config(self, session_id: str, enabled: bool, concurrency_quota: int = 5) -> SwarmModeConfig:
        return self._engine.set_config(session_id, enabled=enabled, concurrency_quota=concurrency_quota)

    def assign_subagent_tasks(self, session_id: str, tasks: list[SwarmSubagentTask]) -> list[SwarmSubagentTask]:
        return self._engine.assign_tasks(session_id, tasks)

    def get_subagent_tasks(self, session_id: str) -> list[SwarmSubagentTask]:
        return self._engine.get_tasks(session_id)

    def record_recalled_rules(self, session_id: str, rules: list[RecalledRuleItem]) -> list[RecalledRuleItem]:
        return self._engine.record_recalled_rules(session_id, rules)

    def get_recalled_rules(self, session_id: str) -> tuple[list[RecalledRuleItem], str]:
        rules = self._engine.get_recalled_rules(session_id)
        prompt = self._engine.compile_active_rules_prompt(session_id)
        return rules, prompt

    def toggle_rule_active(self, session_id: str, rule_id: str, is_active: bool) -> RecalledRuleItem | None:
        return self._engine.toggle_rule_active(session_id, rule_id, is_active)

    def register_owner_risks(self, session_id: str, risks: list[OwnerRiskItem]) -> list[OwnerRiskItem]:
        return self._engine.register_risks(session_id, risks)

    def get_owner_risks(self, session_id: str) -> list[OwnerRiskItem]:
        return self._engine.get_risks(session_id)

    def set_risk_confirmation(
        self, session_id: str, risk_id: str, is_confirmed: bool, confirmed_by: str = ""
    ) -> OwnerRiskItem | None:
        return self._engine.set_risk_confirmation(session_id, risk_id, is_confirmed, confirmed_by)
