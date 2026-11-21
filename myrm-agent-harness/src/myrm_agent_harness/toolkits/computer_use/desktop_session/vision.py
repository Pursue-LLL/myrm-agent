"""desktop_vision: the screenshot and coordinate fallback of the desktop session.

[INPUT]
- host::DesktopSessionHost (POS: typed session state, approval revalidation, guard screenshots)
- perception.ax_dispatch::inspect_backend, run_ax_call (POS: foreground app probe, awaited off the event loop on macOS)
- iphone_mirror::is_iphone_mirror_app, probe_iphone_mirror_state (POS: connect-prompt gate, awaited off the event loop on macOS)
- semantic_gate, safety (POS: coordinate landing gate, hard blocks)
- action_log::log_capture_refused (POS: the log line of a refused screenshot)

[OUTPUT]
- DesktopVisionMixin: desktop_vision_capture (screenshot; refused, and logged, while the screen is locked or asleep or a sensitive app is in front), desktop_vision_action (coordinate click, type, key, scroll, drag, move, wait), _build_multimodal_response (text plus image result)

[POS]
Coordinate-based entry for canvas areas and windows without an AX tree; screen, sensitive-app and (for input) argument,
mirror, approval and semantic gates all run before any pixel is read or touched.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.computer_use import safety
from myrm_agent_harness.toolkits.computer_use.iphone_mirror import (
    is_iphone_mirror_app,
    probe_iphone_mirror_state,
)
from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import inspect_backend, run_ax_call
from myrm_agent_harness.toolkits.computer_use.types import (
    ActionResult,
    DesktopVisionAction,
    IPhoneMirrorState,
    ModifierKey,
    ScrollDirection,
)

from .action_log import log_capture_refused
from .host import DesktopSessionHost

logger = logging.getLogger(__name__)


class DesktopVisionMixin(DesktopSessionHost):
    """Screenshot capture and coordinate actions of the desktop session."""

    async def desktop_vision_capture(self) -> str | list[object]:
        """Screenshot for the model, behind the same screen and sensitive-app checks as the AX snapshot."""
        if (refusal := await self._screen_guard.refusal(snapshot=True)) is not None:
            log_capture_refused("screen")
            return refusal
        fg_app, fg_title, fg_app_id = await run_ax_call(self._backend, self._foreground_identity)
        if blocked := safety.is_sensitive_app(fg_app, fg_title, fg_app_id):
            logger.warning("[SECURITY] Sensitive app guard (vision capture): %s", blocked)
            log_capture_refused("sensitive_app")
            return f"Safety: Cannot view the screen. {blocked}"
        return await self._capture_response()

    async def _capture_response(self) -> str | list[object]:
        """Screenshot as the tool result; callers have already run the guards."""
        result = await self.take_screenshot()
        if not result.success:
            return f"Capture failed: {result.error}"
        return self._build_multimodal_response(result, "Desktop vision capture.")

    def _foreground_identity(self) -> tuple[str, str, str]:
        """Frontmost app name, window title and app id from the lightweight foreground probe."""
        info = inspect_backend(self._backend)
        return (
            str(info.get("app_name", "") or ""),
            str(info.get("window_title", "") or ""),
            str(info.get("app_id", "") or ""),
        )

    async def desktop_vision_action(
        self,
        action: DesktopVisionAction,
        coordinate: list[int] | None = None,
        text: str | None = None,
        scroll_direction: ScrollDirection | None = None,
        scroll_amount: int = 3,
        start_coordinate: list[int] | None = None,
        duration: float = 2.0,
        modifiers: list[ModifierKey] | None = None,
    ) -> str | list[object]:
        await self._ensure_not_user_takeover()
        if (refusal := await self._screen_guard.refusal()) is not None:
            return refusal
        async with self._action_lock:
            # Reject invalid key / type payloads before any display I/O —
            # argument safety must not require a capturable display to fail closed.
            if action == "key":
                if not text:
                    return "Error: text (key combo) is required for key action"
                key_blocked = safety.is_blocked_key_combo(text)
                if key_blocked:
                    return f"Safety: {key_blocked}"
                operator_blocked = safety.is_operator_as_key_name(text)
                if operator_blocked:
                    remedy_hint = (
                        "[REMEDY_HINT: Printable operators are not keyboard key names. "
                        "Use action=type to enter the character, or desktop_interact_tool "
                        "to click the calculator/@dref button.]"
                    )
                    return f"Safety: {operator_blocked}\n{remedy_hint}"
            elif action == "type":
                if not text:
                    return "Error: text is required for type action"
                text_blocked = safety.is_dangerous_type_text(text)
                if text_blocked:
                    return f"Safety: {text_blocked}"

            # [SECURITY] Sensitive app guard — lightweight foreground app check.
            fg_app, fg_title, fg_app_id = await run_ax_call(self._backend, self._foreground_identity)

            blocked = safety.is_sensitive_app(fg_app, fg_title, fg_app_id)
            if blocked:
                logger.warning("[SECURITY] Sensitive app guard (vision): %s", blocked)
                return f"Safety: {blocked}"

            # [SECURITY] iPhone Mirroring gate — during a connect/pairing prompt
            # no coordinate/keyboard action may reach the screen (would either
            # mis-click the pairing dialog or steal focus from it).
            if is_iphone_mirror_app(fg_app, fg_app_id):
                probe = await run_ax_call(self._backend, probe_iphone_mirror_state)
                if probe.state == IPhoneMirrorState.BLOCKED_CONNECT_PROMPT:
                    logger.warning(
                        "[SECURITY] iPhone mirror connect gate (vision): %s",
                        probe.detail,
                    )
                    return f"Safety: {probe.remedy_hint}"

            # [SECURITY] Foreground permission gate for coordinate-based actions.
            if safety.is_foreground_required(action):
                app_denied = await self.check_app_approval(
                    app_name=fg_app,
                    window_title=fg_title,
                    app_id=fg_app_id,
                    operation=f"desktop_vision_action({action})",
                )
                if app_denied is not None:
                    return f"Control denied: {app_denied.error}"

                try:
                    permission_denied = await self.check_foreground_permission(
                        reason=f"Vision action '{action}' requires foreground mouse/keyboard control",
                        operation=f"desktop_vision_action({action})",
                        estimated_duration_seconds=5.0,
                        app_name=fg_app,
                        window_title=fg_title,
                        app_id=fg_app_id,
                    )
                    if permission_denied is not None:
                        return f"Permission denied: {permission_denied.error}"

                    revalidation = await self._revalidate_if_stale_after_approval()
                    if revalidation.refusal is not None:
                        return revalidation.refusal
                finally:
                    self.clear_operation_foreground_waiver()

            # [SECURITY] Desktop semantic guard — coordinate landing-point gate
            # hit-testing the interactive AX refs; unresolvable coordinates pass.
            from myrm_agent_harness.toolkits.computer_use.semantic_gate import (
                DesktopGuardContext,
                enforce_desktop_vision_guard,
            )

            semantic_blocked = await enforce_desktop_vision_guard(
                ctx=DesktopGuardContext(
                    app_name=fg_app,
                    window_title=fg_title,
                    screenshot_provider=self._capture_guard_screenshot,
                    scaler=self.scaler,
                ),
                refs=self._refs.all_refs(),
                action=action,
                coordinate=coordinate,
            )
            if semantic_blocked is not None:
                return semantic_blocked

            if action in (
                "left_click",
                "right_click",
                "middle_click",
                "double_click",
                "triple_click",
            ):
                if coordinate is None or len(coordinate) != 2:
                    return "Error: coordinate [x, y] is required for click actions"
                clicks = {"double_click": 2, "triple_click": 3}.get(action, 1)
                button = {"right_click": "right", "middle_click": "middle"}.get(action, "left")
                result = await self.click_at(
                    coordinate[0],
                    coordinate[1],
                    button=button,
                    clicks=clicks,
                    modifiers=modifiers,
                )
            elif action == "type":
                # Dangerous type payloads are rejected at method entry (no display I/O).
                result = await self.type_text(text or "")
            elif action == "key":
                # Operator / blocked-key payloads are rejected at method entry (no display I/O).
                result = await self.key_press(text or "")
            elif action == "scroll":
                if coordinate is None or len(coordinate) != 2 or not scroll_direction:
                    return "Error: coordinate and scroll_direction are required for scroll"
                result = await self.scroll_at(
                    coordinate[0],
                    coordinate[1],
                    scroll_direction,
                    scroll_amount,
                    modifiers=modifiers,
                )
            elif action == "drag":
                if start_coordinate is None or coordinate is None:
                    return "Error: start_coordinate and coordinate are required for drag"
                result = await self.drag(
                    start_coordinate[0],
                    start_coordinate[1],
                    coordinate[0],
                    coordinate[1],
                    modifiers=modifiers,
                )
            elif action == "mouse_move":
                if coordinate is None or len(coordinate) != 2:
                    return "Error: coordinate [x, y] is required for mouse_move"
                result = await self.mouse_move_to(coordinate[0], coordinate[1])
            elif action in ("capture", "screenshot"):
                return await self._capture_response()
            elif action == "wait":
                result = await self.wait_seconds(duration)
            else:
                return f"Error: unknown vision action '{action}'"

            if not result.success:
                return f"Vision action '{action}' failed: {result.error}"
            if result.screenshot_base64:
                return self._build_multimodal_response(result, f"Vision action '{action}' completed.")
            return f"Vision action '{action}' completed."

    def _build_multimodal_response(self, result: ActionResult, action_description: str) -> list[object]:
        from langchain_core.messages.content import create_image_block, create_text_block

        info = self.screen_info
        ctx = self.screen_context
        context_parts = [
            action_description,
            f"Screen: {info.width}x{info.height}, DPI: {info.dpi_scale}x. "
            f"Image size: {result.screenshot_size[0]}x{result.screenshot_size[1]}.",
        ]
        if ctx.active_window:
            context_parts.append(f"Active window: {ctx.active_window}")
        context_parts.append(f"Mouse position: ({ctx.mouse_x}, {ctx.mouse_y})")
        if result.output:
            context_parts.append(result.output)
        blocks: list[object] = [
            create_text_block("\n".join(context_parts)),
            create_image_block(base64=result.screenshot_base64, mime_type="image/jpeg"),
        ]
        return blocks
