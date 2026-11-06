"""桌面控制工具。

[POS]
ToolSetupMixin 的一个工具族；由 mixin.py 组合。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import ToolSetupBaseMixin

if TYPE_CHECKING:

    pass

from app.ai_agents.general_agent.tool_setup.common import _select_image_constraints

logger = logging.getLogger(__name__)


class ComputerToolsMixin(ToolSetupBaseMixin):
    """桌面控制工具。"""

    def _setup_computer_use_tools(self, tools: list[object]) -> None:
        """Set up system-wide computer use tools (screenshot + action)."""
        try:
            from myrm_agent_harness.toolkits.computer_use import (
                create_desktop_session,
                create_desktop_tools,
            )
            from myrm_agent_harness.toolkits.computer_use.types import (
                ComputerUseConfig,
                ExecutionMode,
            )

            from app.ai_agents.desktop_control.gate import DesktopControlGate
            from app.config.computer_use_deploy import is_computer_use_deploy_supported
            from app.config.deploy_mode import is_local_mode, is_sandbox

            constraints = _select_image_constraints(self.model_cfg.model)
            workspace_root = self.declared_allowed_roots[0] if getattr(self, "declared_allowed_roots", ()) else None
            auto_grant = is_sandbox() and is_computer_use_deploy_supported() and not is_local_mode()
            execution_mode = ExecutionMode.background_strict if is_local_mode() else ExecutionMode.background_best_effort
            run_trust_keys = tuple(getattr(self, "desktop_preapproved_trust_keys", ()) or ())
            run_fail_fast = bool(getattr(self, "desktop_unattended_fail_fast", False))
            agent_task_id = str(getattr(self, "session_id", None) or getattr(self, "task_id", None) or "").strip()
            gate = DesktopControlGate(
                workspace_root=workspace_root,
                auto_grant=auto_grant,
                preapproved_trust_keys=run_trust_keys,
                unattended_fail_fast=run_fail_fast,
                task_id=agent_task_id,
            )
            config_kwargs: dict[str, object] = {"execution_mode": execution_mode}
            if constraints:
                config_kwargs["image_constraints"] = constraints
            config = ComputerUseConfig(**config_kwargs)
            session = create_desktop_session(config=config, permission_callback=gate)
            from app.services.locked_use.unattended import attach_desktop_session

            if attach_desktop_session(session):
                logger.info("Desktop session attached to the privacy curtain (capture exclusion + on-demand unlock)")
            computer_tools = create_desktop_tools(session)
            tools.extend(computer_tools)
            self._desktop_session = session
            logger.warning(
                "Loaded %d desktop control tools (model=%s, mode=%s, max_edge=%dpx) [Turn1]",
                len(computer_tools),
                self.model_cfg.model,
                execution_mode.value,
                session._config.image_constraints.max_edge_px,
            )
        except Exception as e:
            logger.warning("Computer use tools load failed (degraded): %s", e)
