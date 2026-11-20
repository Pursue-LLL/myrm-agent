"""desktop_interact: act on one @dref element through the accessibility API.

[INPUT]
- host::DesktopSessionHost (POS: typed session state, approval revalidation, guard screenshots, follow-up snapshot)
- dref.registry::DRefRegistry.resolve (POS: the element a reference names with the snapshot that registered it)
- perception.ax_dispatch::invoke_element (POS: native AX action on an element)
- execution.healer::try_bbox_click (POS: coordinate fallback when the native action fails)
- semantic_gate, safety, core.security.credential_vault (POS: destructive-action gate, hard blocks, credential fill)

[OUTPUT]
- DesktopInteractMixin: desktop_interact (screen guard, per-app approval, revalidation, gates, native action with bbox fallback, follow-up snapshot)

[POS]
Mutating semantic entry of the desktop tools; every gate that can refuse the action runs before the element is touched.
The approval is asked for the application the registry holds; after the re-read, the gates, the delivery and the
follow-up snapshot all use the one capture the element was resolved from.
"""

from __future__ import annotations

import asyncio
import logging

from myrm_agent_harness.toolkits.computer_use.dref.errors import DRefStaleError
from myrm_agent_harness.toolkits.computer_use.dref.types import SnapshotMeta
from myrm_agent_harness.toolkits.computer_use.execution.healer import try_bbox_click
from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import invoke_element
from myrm_agent_harness.toolkits.computer_use.types import DesktopInteractAction, ModifierKey

from .host import DesktopSessionHost

logger = logging.getLogger(__name__)

_NO_SNAPSHOT = SnapshotMeta(ref_count=0, app_name="", window_title="", scope="foreground")


class DesktopInteractMixin(DesktopSessionHost):
    """Semantic element interaction of the desktop session."""

    async def desktop_interact(
        self,
        ref: str,
        action: DesktopInteractAction,
        text: str = "",
        modifiers: list[ModifierKey] | None = None,
        wait_seconds: float = 0.0,
    ) -> str | list[object]:
        await self._ensure_not_user_takeover()
        if (refusal := await self._screen_guard.refusal()) is not None:
            return refusal
        async with self._action_lock:
            from myrm_agent_harness.toolkits.computer_use import safety

            asked_for = self._refs.meta or _NO_SNAPSHOT
            app_denied = await self.check_app_approval(
                app_name=asked_for.app_name,
                window_title=asked_for.window_title,
                app_id=asked_for.app_id,
                operation=f"desktop_interact({action}, @{ref})",
            )
            if app_denied is not None:
                return f"Control denied: {app_denied.error}"

            try:
                stale_error = await self._revalidate_if_stale_after_approval(interact_ref=ref)
                if stale_error is not None:
                    return stale_error

                try:
                    element, meta = self._refs.resolve(ref)
                except DRefStaleError as exc:
                    remedy_hint = (
                        f"[REMEDY_HINT: The element reference @{ref} is stale because the UI state has changed. "
                        "Call desktop_snapshot_tool(scope='foreground') to refresh the @dref element tree.]"
                    )
                    return f"{exc}\n{remedy_hint}"

                # [SECURITY] iPhone Mirroring connect/pairing gate — hard block,
                # not approvable: user must confirm connection on the device.
                mirror_blocked = safety.is_iphone_mirror_blocked_action(
                    app_name=meta.app_name,
                    window_title=meta.window_title,
                    app_id=meta.app_id,
                    action_text=f"{element.name} {text}".strip(),
                )
                if mirror_blocked:
                    logger.warning(
                        "[SECURITY] iPhone mirror connect gate (interact): %s",
                        mirror_blocked,
                    )
                    return f"Safety: {mirror_blocked}"

                # [SECURITY] Desktop semantic guard — destructive AX control gate
                # sharing the cross-channel lexicon with the browser DOM gate.
                from myrm_agent_harness.toolkits.computer_use.semantic_gate import (
                    DesktopGuardContext,
                    enforce_desktop_interact_guard,
                )

                semantic_blocked = await enforce_desktop_interact_guard(
                    ctx=DesktopGuardContext(
                        app_name=meta.app_name,
                        window_title=meta.window_title,
                        screenshot_provider=self._capture_guard_screenshot,
                        scaler=self.scaler,
                    ),
                    ref_id=element.ref_id,
                    role=element.role,
                    name=element.name,
                    action=action,
                    text=text,
                )
                if semantic_blocked is not None:
                    return semantic_blocked

                effective_action = action
                effective_text = text

                if action == "fill_credential":
                    from myrm_agent_harness.core.security.credential_vault import (
                        get_global_credential_vault,
                    )

                    vault = get_global_credential_vault()
                    is_totp = text.endswith("-totp")
                    try:
                        if is_totp:
                            effective_text = vault.get_totp_token(text)
                        else:
                            effective_text = vault.get_password(text)
                    except Exception:
                        return f"Failed to retrieve credential for label '{text}'"
                    effective_action = "fill"
                elif action == "set_value":
                    effective_action = "set_value"

                ax_result = invoke_element(
                    self._backend,
                    element,
                    effective_action,
                    effective_text,
                    app_name=meta.app_name,
                )
                if not ax_result.success:
                    bbox_result = await try_bbox_click(self, element, effective_action, effective_text, modifiers)
                    if not bbox_result.success:
                        remedy_hint = (
                            f"[REMEDY_HINT: Action '{action}' on @{element.ref_id} failed via accessibility invocation "
                            f"({ax_result.error}) and bounding-box fallback ({bbox_result.error}). "
                            "The target window may be minimized, occluded, or scrolled off-screen. "
                            "Suggested remedies: 1) Call desktop_snapshot_tool(scope='foreground') to verify window state; "
                            "2) Call desktop_snapshot_tool(scope='target', app_name='...') to bring the app window forward; "
                            "3) Use desktop_vision_tool if the element is custom-rendered on canvas.]"
                        )
                        return (
                            f"desktop_interact failed for @{element.ref_id}: "
                            f"{ax_result.error}; bbox fallback: {bbox_result.error}\n{remedy_hint}"
                        )

                base_delay = self._config.screenshot_delay
                if wait_seconds > 0:
                    base_delay += min(max(float(wait_seconds), 0.0), 10.0)
                await asyncio.sleep(base_delay)
                if meta.app_name:
                    follow_up = await self.desktop_snapshot(
                        scope="target",
                        app_name=meta.app_name,
                        include_screenshot=False,
                    )
                else:
                    follow_up = await self.desktop_snapshot(
                        scope="foreground",
                        include_screenshot=False,
                    )
                if action == "fill_credential":
                    result_prefix = f"Filled credential '{text}' into @{element.ref_id} [CREDENTIAL_FILLED]\n\n"
                else:
                    result_prefix = f"Action '{action}' on @{element.ref_id} succeeded.\n\n"
                if isinstance(follow_up, list):
                    first = follow_up[0]
                    if hasattr(first, "text"):
                        first.text = result_prefix + getattr(first, "text", "")
                    return follow_up
                return f"{result_prefix}{follow_up}"
            finally:
                self.clear_operation_foreground_waiver()
