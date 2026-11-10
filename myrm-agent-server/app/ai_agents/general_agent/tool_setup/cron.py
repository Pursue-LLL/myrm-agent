"""[INPUT]
- app.ai_agents.general_agent.tool_setup.base::ToolSetupBaseMixin (POS: 各工具族 mixin 共同继承，避免重复声明宿主属性。)

[OUTPUT]
- CronToolsMixin: Cron 工具。

[POS]
ToolSetupMixin 的一个工具族；由 mixin.py 组合。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import ToolSetupBaseMixin

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.types import DeliveryConfig


logger = logging.getLogger(__name__)


class CronToolsMixin(ToolSetupBaseMixin):
    """Cron 工具。"""

    def _resolve_cron_default_delivery(self) -> DeliveryConfig | None:
        """Default IM delivery when creating cron jobs from a messaging channel."""
        from myrm_agent_harness.toolkits.cron.types import DeliveryConfig

        channel = getattr(self, "channel_name", "web_chat")
        if channel in ("web_chat", "cron", "subagent"):
            return None

        from myrm_agent_harness.agent.security.channel_presets import (
            ChannelType,
            resolve_channel_type,
        )

        if resolve_channel_type(channel) == ChannelType.WEB_CHAT:
            return None

        recipient = getattr(self, "memory_conversation_id", None) or getattr(self, "chat_id", None)
        if not recipient:
            return None
        return DeliveryConfig(channel=channel, target=str(recipient))

    async def _setup_cron_tools(self, tools: list[object]) -> None:
        """Set up scheduled task (cron) tools as Turn1 eager.

        Only called when ``enable_cron_eager=True`` (user opted in).
        """
        try:
            from myrm_agent_harness.toolkits import create_cron_tools

            from app.core.cron.adapters.delivery_resolver import resolve_cron_delivery
            from app.core.cron.adapters.setup import get_cron_manager
            from app.core.cron.blueprints import get_blueprints_for_tool_description
            from app.core.cron.blueprints.job_spec import fill_job_spec

            agent_locale = getattr(self, "locale", None) or "en"

            cron_tools = create_cron_tools(
                get_cron_manager(),
                current_model=self.model_cfg.model,
                chat_id=self.chat_id,
                agent_id=self.agent_id,
                blueprint_filler=lambda bp_id, values, tz: fill_job_spec(bp_id, values, locale=agent_locale, tz=tz),
                blueprint_catalog_provider=lambda: get_blueprints_for_tool_description(agent_locale),
                delivery_resolver=resolve_cron_delivery,
                default_delivery=self._resolve_cron_default_delivery(),
            )
            tools.extend(cron_tools)
            logger.info("Loaded %d cron tools [Turn1 eager]", len(cron_tools))
        except Exception as e:
            logger.warning(f"Cron tools load failed (degraded): {e}")
