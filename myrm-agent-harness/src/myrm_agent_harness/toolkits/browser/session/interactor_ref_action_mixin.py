"""Ref-based verb dispatch for the Interactor.

[INPUT]
- pool.config::HumanizeConfig (POS: interaction humanization config)
- session.humanize::INTERACTION_TIMEOUT_MS, click_delay, type_delay (POS: humanized delay helpers and the shared interaction timeout)
- session.interactor_click_mixin::ClickInteractMixin (POS: Bézier-mouse click trajectory + reachability guard)
- session.interactor_scroll_mixin::ScrollHumanizeMixin, _parse_scroll_params (POS: humanized wheel-input scrolling behaviors)

[OUTPUT]
- RefActionMixin: performs one of the 15 ref verbs on a resolved locator and describes the outcome

[POS]
Ref verb dispatch mixed into Interactor. Given a resolved locator, performs one of 15 verbs
(click/dblclick/type/fill/fill_credential/press/hover/focus/select/scroll/scroll_to_bottom/
upload_file/drag/check/uncheck) with the humanization stack of the rest of the interaction
(Gaussian delays, Bézier trajectory in CAREFUL mode) and returns the answer text. Action
validation, ref resolution, the wait after the action and the answers to a failed interaction
stay in Interactor.interact.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.browser.session.humanize import (
    INTERACTION_TIMEOUT_MS,
    click_delay,
    type_delay,
)
from myrm_agent_harness.toolkits.browser.session.interactor_scroll_mixin import (
    _parse_scroll_params,
)

if TYPE_CHECKING:
    from patchright.async_api import Locator, Page

    from myrm_agent_harness.toolkits.browser.pool.config import HumanizeConfig


class RefActionMixin:
    """Performs one ref verb on a resolved locator."""

    # Provided by Interactor and the other mixins; declared so the mixin type-checks on its own.
    _page: Page
    _humanize: HumanizeConfig

    if TYPE_CHECKING:

        async def _assert_not_password_field(self, locator: Locator, verb: str) -> None: ...
        async def _bezier_click(self, locator: Locator, ref: str, healed_msg: str) -> str: ...
        async def _bezier_move_to(self, locator: Locator) -> bool: ...
        async def _scroll_cursor_target(self, locator: Locator) -> tuple[float, float]: ...
        async def _scroll_move_cursor(self, x: float, y: float) -> None: ...
        async def _scroll_with_report(self, x: float, y: float, delta: int, suffix: str) -> str: ...
        async def _scroll_to_bottom_loop(self, locator: Locator, params: dict[str, int], healed_msg: str) -> str: ...

    async def _perform_ref_action(
        self,
        action: str,
        ref: str,
        text: str,
        locator: Locator,
        healed_msg: str,
    ) -> str:
        """Perform one ref verb on the resolved locator and describe the outcome.

        The driver's exception propagates when the verb fails; the caller answers the
        failures the agent can act on.
        """
        if action == "click":
            if self._humanize.enable_bezier_mouse:
                return await self._bezier_click(locator, ref, healed_msg)
            delay = click_delay(self._humanize)
            await locator.click(delay=delay, timeout=INTERACTION_TIMEOUT_MS)
            return f"Clicked {ref}{healed_msg}"

        elif action == "dblclick":
            delay = click_delay(self._humanize)
            await locator.dblclick(delay=delay, timeout=INTERACTION_TIMEOUT_MS)
            return f"Double-clicked {ref}{healed_msg}"

        elif action == "type":
            await self._assert_not_password_field(locator, "typing")

            delay_per_char = type_delay(self._humanize)
            typing_timeout = max(INTERACTION_TIMEOUT_MS, len(text) * delay_per_char + 5000)
            await locator.type(text, delay=delay_per_char, timeout=typing_timeout)
            return f"Typed '{text}' into {ref}{healed_msg}"

        elif action == "fill":
            await self._assert_not_password_field(locator, "filling")

            await locator.fill(text, timeout=INTERACTION_TIMEOUT_MS)
            return f"Filled {ref} with '{text}'{healed_msg}"

        elif action == "fill_credential":
            from myrm_agent_harness.core.security.credential_vault import (
                get_global_credential_vault,
            )

            vault = get_global_credential_vault()

            # Check if it's a TOTP request (e.g. label ends with -totp)
            is_totp = text.endswith("-totp")

            try:
                if is_totp:
                    secret_text = vault.get_totp_token(text)
                else:
                    secret_text = vault.get_password(text)
            except Exception as e:
                raise ValueError(f"Failed to retrieve credential for label '{text}': {e}") from e

            await locator.fill(secret_text, timeout=INTERACTION_TIMEOUT_MS)
            return f"Filled credential '{text}' into {ref}{healed_msg} [CREDENTIAL_FILLED]"

        elif action == "press":
            await locator.press(text, timeout=INTERACTION_TIMEOUT_MS)
            return f"Pressed '{text}' on {ref}{healed_msg}"

        elif action == "hover":
            if self._humanize.enable_bezier_mouse:
                if not await self._bezier_move_to(locator):
                    await locator.hover(timeout=INTERACTION_TIMEOUT_MS)
            else:
                await locator.hover(timeout=INTERACTION_TIMEOUT_MS)
            return f"Hovered over {ref}{healed_msg}"

        elif action == "focus":
            await locator.focus(timeout=INTERACTION_TIMEOUT_MS)
            return f"Focused {ref}{healed_msg}"

        elif action == "select":
            # Recorded multi-select steps join option values with "; " —
            # split them so every option is selected instead of trying to
            # match a single blob that no option equals.
            values: str | list[str] = [v.strip() for v in text.split(";")] if ";" in text else text
            await locator.select_option(values, timeout=INTERACTION_TIMEOUT_MS)
            return f"Selected '{text}' in {ref}{healed_msg}"

        elif action == "scroll":
            try:
                delta = int(text)
            except ValueError as exc:
                raise ValueError(f"Scroll requires numeric text (pixel delta), got: {text}") from exc

            target_x, target_y = await self._scroll_cursor_target(locator)
            await self._scroll_move_cursor(target_x, target_y)
            return await self._scroll_with_report(target_x, target_y, delta, healed_msg)

        elif action == "scroll_to_bottom":
            return await self._scroll_to_bottom_loop(locator, _parse_scroll_params(text), healed_msg)

        elif action == "upload_file":
            await locator.set_input_files(text, timeout=INTERACTION_TIMEOUT_MS)
            return f"Uploaded file to {ref}: {text}{healed_msg}"

        elif action == "drag":
            parts = text.split(",")
            if len(parts) != 2:
                raise ValueError(f"Drag requires 'x,y' text, got: {text}")

            try:
                x, y = int(parts[0]), int(parts[1])
            except ValueError as exc:
                raise ValueError(f"Drag requires numeric 'x,y', got: {text}") from exc

            await locator.drag_to(self._page.locator("body"), target_position={"x": x, "y": y})
            return f"Dragged {ref} to ({x}, {y}){healed_msg}"

        elif action == "check":
            await locator.check(timeout=INTERACTION_TIMEOUT_MS)
            return f"Checked {ref}{healed_msg}"

        elif action == "uncheck":
            await locator.uncheck(timeout=INTERACTION_TIMEOUT_MS)
            return f"Unchecked {ref}{healed_msg}"

        return f"Unknown action: {action}"
