"""技能市场与技能管理工具。

[POS]
ToolSetupMixin 的一个工具族；由 mixin.py 组合。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import ToolSetupBaseMixin

if TYPE_CHECKING:

    pass

logger = logging.getLogger(__name__)


class SkillToolsMixin(ToolSetupBaseMixin):
    """技能市场与技能管理工具。"""

    @property
    def skill_manage_mounted(self) -> bool:
        """Whether skill_manage_tool is built into this agent.

        ``/learn`` forces the mount for a single run. Both triggers resolve here so
        the factory mount and the execution fingerprint can never disagree about
        whether a cached agent carries the tool.
        """
        return self.enable_skill_manage or self.force_skill_manage

    def _setup_skill_market_tool(self, tools: list[object], market_backend: object) -> None:
        """Turn1 mount skill_market_tool via server product layer (not get_meta_tools)."""
        from myrm_agent_harness.agent.meta_tools.skills.market import (
            create_skill_market_tool,
        )

        from app.core.skills.discovery.agent_market_install import (
            make_agent_session_install_from_url_fn,
            wrap_skill_market_backend_for_agent_session,
        )

        backend = wrap_skill_market_backend_for_agent_session(market_backend)
        install_url_fn = None
        if getattr(market_backend, "install_from_url", None) is not None:
            install_url_fn = make_agent_session_install_from_url_fn(market_backend)
        uninstall_fn = getattr(market_backend, "uninstall", None)
        tools.append(
            create_skill_market_tool(
                backend,
                install_from_url_fn=install_url_fn,
                uninstall_fn=uninstall_fn,
            )
        )
        logger.info("Loaded skill_market_tool [Turn1]")

    def _setup_skill_manage_tool(
        self,
        tools: list[object],
        write_backend: object,
        skill_backend: object,
        *,
        auxiliary_llm: object | None = None,
    ) -> None:
        """Turn1 mount skill_manage_tool with ScanningSkillWriteBackend wrapper."""
        from myrm_agent_harness.agent.meta_tools.skills.manage import (
            create_skill_manage_tool,
        )
        from myrm_agent_harness.backends.skills.scanning.scanning_write_backend import (
            ScanningSkillWriteBackend,
        )

        llm_auditor_instance = None
        if auxiliary_llm is not None:
            from myrm_agent_harness.backends.skills.scanning.llm_auditor import (
                SkillLLMAuditor,
            )

            llm_auditor_instance = SkillLLMAuditor(llm=auxiliary_llm)

        scanning_backend = ScanningSkillWriteBackend(
            inner=write_backend,
            llm_auditor=llm_auditor_instance,
        )
        from app.core.skills.creation.managed_skill_reader import ManagedSkillSnapshotReader
        from app.core.skills.creation.service import skill_creation_service
        from app.services.skills.mutation_batch_hook import ServerSkillManageBatchHook

        tools.append(
            create_skill_manage_tool(
                scanning_backend,
                skill_backend,
                batch_committed_hook=ServerSkillManageBatchHook(),
                snapshot_reader=ManagedSkillSnapshotReader(skill_creation_service),
            )
        )
        logger.info("Loaded skill_manage_tool [Turn1]")
