"""Element and coordinate interaction APIs of BrowserSession.

[INPUT]
- session_host::SessionHost (POS: typed contract of the host attributes; provides the components, the takeover wait and the inspector view)
- tools.semantic_dom_hitl::enforce_semantic_interaction_guard (POS: single HITL approval path for high-risk ARIA refs)
- utils.selectors::PASSWORD_FIELD_SELECTOR (POS: password fields masked in the baseline screenshot)

[OUTPUT]
- BrowserSessionInteractionMixin: interact (ref-based) and interact_at (coordinate-based), each with optional visual verification

[POS]
Interaction step of BrowserSession: waits out a user takeover, gates high-risk refs through the shared approval path,
delegates to the Interactor, hands a click that may have raised a CAPTCHA to the coordinator, then runs the optional
vision verification and republishes the inspector view. Listed after the page mixin and before the download mixin.
"""

from __future__ import annotations

import logging

from .session_host import SessionHost

logger = logging.getLogger(__name__)


class BrowserSessionInteractionMixin(SessionHost):
    async def interact(self, action: str, ref: str, text: str = "", verify_goal: str | None = None) -> str:
        """Ref-based element interaction (15 action types) with optional visual verification."""
        await self._ensure_not_user_takeover()
        await self._ensure_components()
        interactor = self._require_interactor()
        page = self._tab_controller.get_active_page()

        from myrm_agent_harness.toolkits.browser.tools.semantic_dom_hitl import (
            enforce_semantic_interaction_guard,
        )

        ref_info = self.get_ref_info(ref)
        caller_tool = self._hitl_caller_tool or "browser_interact_tool"
        blocked = await enforce_semantic_interaction_guard(
            session=self,
            tool_name=caller_tool,
            action=action,
            ref=ref,
            ref_info=ref_info,
            text=text,
        )
        if blocked is not None:
            return blocked

        baseline_screenshot = None
        if verify_goal:
            try:
                from myrm_agent_harness.toolkits.browser.utils.selectors import PASSWORD_FIELD_SELECTOR

                password_locator = page.locator(PASSWORD_FIELD_SELECTOR)
                baseline_screenshot = await page.screenshot(type="png", full_page=False, mask=[password_locator])
            except Exception as e:
                logger.warning("Failed to take baseline screenshot for verification: %s", e)

        result = await interactor.interact(action, ref, text)
        self._tab_controller.clear_text_snapshot()

        if action in ("click", "dblclick") and self._captcha_coordinator is not None:
            captcha_result = await self._handle_captcha_if_detected()
            if captcha_result is not None:
                result = f"{result}\n{captcha_result.message}"

        if verify_goal and baseline_screenshot:
            await self.notify_progress(f"Verifying action goal: '{verify_goal}'...")
            _success, verify_msg = await self._vision_verifier.verify_action(
                page=page,
                baseline_screenshot=baseline_screenshot,
                verify_goal=verify_goal,
            )
            result = f"{result}\n\n{verify_msg}"
            # We append the failure to the result so the LLM can reflect on it.
            # The tool call itself doesn't raise an exception, it just reports the failure.

        await self._publish_inspector_view()
        return result

    async def interact_at(
        self,
        action: str,
        x: float,
        y: float,
        text: str = "",
        target_x: float | None = None,
        target_y: float | None = None,
        verify_goal: str | None = None,
    ) -> str:
        """Coordinate-based interaction for canvas/rich-editor pages.

        Bypasses ref resolution — operates directly at viewport (x, y).
        Supports optional visual verification identical to ref-based interact().
        """
        await self._ensure_not_user_takeover()
        await self._ensure_components()
        interactor = self._require_interactor()
        page = self._tab_controller.get_active_page()

        baseline_screenshot = None
        if verify_goal:
            try:
                from myrm_agent_harness.toolkits.browser.utils.selectors import PASSWORD_FIELD_SELECTOR

                password_locator = page.locator(PASSWORD_FIELD_SELECTOR)
                baseline_screenshot = await page.screenshot(type="png", full_page=False, mask=[password_locator])
            except Exception as e:
                logger.warning("Failed to take baseline screenshot for coord verification: %s", e)

        result = await interactor.interact_at(action, x, y, text, target_x, target_y)
        self._tab_controller.clear_text_snapshot()

        if verify_goal and baseline_screenshot:
            await self.notify_progress(f"Verifying action goal: '{verify_goal}'...")
            _success, verify_msg = await self._vision_verifier.verify_action(
                page=page,
                baseline_screenshot=baseline_screenshot,
                verify_goal=verify_goal,
            )
            result = f"{result}\n\n{verify_msg}"

        await self._publish_inspector_view()
        return result
