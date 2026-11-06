"""[INPUT]
- app.ai_agents.general_agent.tool_setup.base::ToolSetupBaseMixin (POS: 各工具族 mixin 共同继承，避免重复声明宿主属性。)

[OUTPUT]
- BrowserToolsMixin: 浏览器与验证码工具。

[POS]
ToolSetupMixin 的一个工具族；由 mixin.py 组合。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .base import ToolSetupBaseMixin

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from myrm_agent_harness.toolkits.browser.captcha.protocols import CaptchaSolver


logger = logging.getLogger(__name__)


class BrowserToolsMixin(ToolSetupBaseMixin):
    """浏览器与验证码工具。"""

    async def _setup_browser_tools(
        self,
        tools: list[object],
        effective_chat_id: str,
        vision_llm: "BaseChatModel" | None = None,
        memory_manager: object | None = None,
    ) -> None:
        """Set up browser automation tools and session."""
        try:
            from myrm_agent_harness.toolkits import create_browser_tools
            from myrm_agent_harness.toolkits.browser import (
                BrowserSession,
                DomainAllowlist,
            )
            from myrm_agent_harness.toolkits.browser.pool import (
                ContextType,
                get_global_browser_pool,
            )

            from app.config.browser import (
                get_browser_launch_options,
                get_browser_pool_config,
            )
            from app.config.deploy_mode import is_local_mode
            from app.core.security.browser_vault import (
                get_agent_session_vault,
                get_global_session_vault,
            )
            from app.platform_utils.workspace_root import get_workspace_root

            pool = get_global_browser_pool(
                config=get_browser_pool_config(),
                launch_options=get_browser_launch_options(),
            )
            if self.agent_id and self.agent_id != "default":
                self._session_vault = get_agent_session_vault(self.agent_id)
            else:
                self._session_vault = get_global_session_vault()

            domain_allowlist = None
            domain_blocklist = None
            # BrowserSession is created before BaseAgent init (self.agent is still None).
            # Resolve merged network policy the same way SecurityPolicyExtension does.
            from myrm_agent_harness.agent.security.channel_presets import (
                build_channel_security_config,
            )

            merged_security = build_channel_security_config(
                self.channel_name,
                self.security_config_raw,
                agent_security_raw=self.agent_security_raw,
                declared_capabilities=self.declared_capabilities,
                declared_allowed_roots=self.declared_allowed_roots,
                local_mode=is_local_mode(),
            )
            if merged_security.network_allowlist:
                domain_allowlist = DomainAllowlist.from_strings(merged_security.network_allowlist)
            if merged_security.network_blocklist:
                domain_blocklist = DomainAllowlist.from_strings(merged_security.network_blocklist)

            thread_id = self.approval_session_key or f"chat_{effective_chat_id}"

            # Determine context_key for browser session
            # 1. Custom Agents (have agent_id) should share browser state across chats
            # 2. Default/Temporary agents fallback to thread_id (chat session)
            if self.agent_id and self.agent_id != "default":
                browser_context_key = f"agent_{self.agent_id}"
            else:
                browser_context_key = thread_id

            from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
            from myrm_agent_harness.toolkits.browser.observability import (
                BrowserObservability,
                RecordingConfig,
            )

            observability: BrowserObservability | None = None
            recording_mode = getattr(self, "session_recording", None)
            if recording_mode and recording_mode != "off":
                from app.config.settings import get_settings

                recordings_dir = str(Path(get_settings().database.harness_dir) / "recordings")
                observability = BrowserObservability(
                    RecordingConfig(
                        enabled=True,
                        output_dir=recordings_dir,
                        save_on_failure=True,
                        save_on_success=(recording_mode == "always"),
                    )
                )

            from app.services.extension.bridge import get_extension_bridge

            # Keep extension mode usable across local/tauri/sandbox.
            # Connection health is still validated by the bridge at runtime.
            ext_bridge = get_extension_bridge()

            # The agent's chat workspace: the root file_read resolves vault pointers against.
            workspace_root = str(self.declared_allowed_roots[0] if self.declared_allowed_roots else get_workspace_root())
            browser_session = BrowserSession(
                pool,
                ContextType.AGENT,
                context_key=browser_context_key,
                session_vault=self._session_vault,
                observability=observability,
                domain_allowlist=domain_allowlist,
                domain_blocklist=domain_blocklist,
                captcha_solver=await self._build_captcha_solver(),
                content_vault=ArtifactVault(workspace_root),
                vision_llm=vision_llm,
                extension_bridge=ext_bridge,
                allow_private_networks=is_local_mode(),
                auto_restore_domains=getattr(self, "auto_restore_domains", []),
                engine_preference=None,
                launch_mode_preference=getattr(self, "browser_source", None),
                dialog_policy=getattr(self, "dialog_policy", None),
            )

            if memory_manager is not None:
                from myrm_agent_harness.toolkits.browser.session import (
                    SessionMemoryBridge,
                )

                bridge = SessionMemoryBridge(memory_manager)
                browser_session.set_session_lifecycle_hook(bridge)
                logger.info("SessionMemoryBridge wired: browser sessions → memory profile")

            logger.warning(f"BrowserSession created: context_key={browser_context_key} (thread_id={thread_id})")

            browser_tools = create_browser_tools(browser_session)
            # Browser tools are high frequency if enabled
            tools.extend(browser_tools)
            self._browser_session = browser_session
            logger.info(f"Loaded {len(browser_tools)} browser tools")
        except Exception as e:
            logger.warning(f"Browser tools load failed (degraded): {e}")

    async def _build_captcha_solver(self) -> CaptchaSolver:
        """Build the CAPTCHA solver based on user configuration.

        Returns FallbackSolver(ApiSolver, ManualSolver) if configured,
        otherwise plain ManualSolver (preserving existing behavior).
        """
        from myrm_agent_harness.toolkits.browser.captcha import (
            ApiSolver,
            FallbackSolver,
            ManualSolver,
        )

        capsolver_key = await self._get_capsolver_api_key()
        if capsolver_key:
            return FallbackSolver(ApiSolver(capsolver_key), ManualSolver())
        return ManualSolver()

    async def _get_capsolver_api_key(self) -> str | None:
        """Read CapSolver API key from user config (DB-stored, encrypted)."""
        try:
            from app.services.config.service import config_service

            record = await config_service.get("captchaSolverConfig")
            if record and isinstance(record.value, dict):
                if record.value.get("enabled") and record.value.get("api_key"):
                    return str(record.value["api_key"])
        except Exception:
            pass
        return None
