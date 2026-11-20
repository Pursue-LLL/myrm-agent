"""desktop_interact: act on one @dref element through the accessibility API.

[INPUT]
- host::DesktopSessionHost (POS: typed session state with the secrets the vault filled, approval revalidation, guard screenshots, follow-up snapshot)
- dref.registry::DRefRegistry.resolve (POS: the element a reference names with the snapshot that registered it)
- perception.ax_dispatch::invoke_element (POS: native AX action on an element)
- perception.ax_result::AxFailure (POS: what a failed native action proves about delivery)
- execution.healer::try_bbox_click (POS: coordinate fallback for an action the native route cannot perform)
- semantic_gate, safety, core.security.credential_vault (POS: destructive-action gate, hard blocks, credential fill)
- types::DESKTOP_TEXT_ACTIONS (POS: the verbs that only enter text; the others reach the element as an activation)

[OUTPUT]
- DesktopInteractMixin: desktop_interact (screen guard, per-app approval, revalidation, gates, native action with bbox fallback only after an unsupported action, follow-up snapshot)

[POS]
Mutating semantic entry of the desktop tools; every gate that can refuse the action runs before anything reaches the
element. The approval is asked for the application the registry holds; after the re-read, the gates, the delivery and
the follow-up snapshot all use the one capture the element was resolved from. A native failure that is stale or of
unknown outcome is reported and never retried or clicked by coordinates; a text entry the native route declines is
gated once more, as the click the coordinate fallback delivers. A credential the vault filled is remembered before it
is delivered, so no capture shows it back, and the errors a reply quotes never carry it.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace

from myrm_agent_harness.toolkits.computer_use.dref.errors import DRefStaleError
from myrm_agent_harness.toolkits.computer_use.dref.types import ElementRef, SnapshotMeta
from myrm_agent_harness.toolkits.computer_use.execution.healer import try_bbox_click
from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import invoke_element
from myrm_agent_harness.toolkits.computer_use.perception.ax_result import AxFailure, AxInvokeResult
from myrm_agent_harness.toolkits.computer_use.types import DESKTOP_TEXT_ACTIONS, DesktopInteractAction, ModifierKey

from .host import DesktopSessionHost

logger = logging.getLogger(__name__)

_NO_SNAPSHOT = SnapshotMeta(ref_count=0, app_name="", window_title="", scope="foreground")


def _snapshot_call(meta: SnapshotMeta) -> str:
    """The snapshot call that reads the application the model is working in."""
    if meta.app_name:
        return f"desktop_snapshot_tool(scope='target', app_name='{meta.app_name}')"
    return "desktop_snapshot_tool(scope='foreground')"


def _stopped_without_fallback(element: ElementRef, meta: SnapshotMeta, ax_result: AxInvokeResult) -> str:
    """Reply for a native failure that is neither repeated nor handed to the coordinate click.

    A stale element's old position may belong to something else now, and an unknown outcome may already have been
    delivered; only a failure that proves nothing reached the element is clicked again by coordinates.
    """
    snapshot = _snapshot_call(meta)
    if ax_result.failure is AxFailure.STALE:
        return (
            f"desktop_interact stopped for @{element.ref_id}: the element is no longer where the snapshot found it "
            f"({ax_result.error}).\n"
            f"[REMEDY_HINT: The UI changed after the snapshot. Call {snapshot} to refresh the @dref element tree, "
            "then use the new reference.]"
        )
    return (
        f"desktop_interact result unknown for @{element.ref_id}: {ax_result.error}. "
        "The action may or may not have been delivered, so it was not retried.\n"
        f"[REMEDY_HINT: Check the screen with {snapshot} or desktop_vision_tool before repeating the action; "
        "repeating it blindly can duplicate its effect, such as a second send or confirm.]"
    )


class DesktopInteractMixin(DesktopSessionHost):
    """Semantic element interaction of the desktop session."""

    async def _semantic_block(self, element: ElementRef, meta: SnapshotMeta, action: str, text: str) -> str | None:
        """[SECURITY] Destructive-control gate, sharing the cross-channel lexicon with the browser DOM gate.

        Returns the block message when the user refuses the action, None when it may proceed.
        """
        from myrm_agent_harness.toolkits.computer_use.semantic_gate import (
            DesktopGuardContext,
            enforce_desktop_interact_guard,
        )

        return await enforce_desktop_interact_guard(
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
                        f"Call {_snapshot_call(asked_for)} to refresh the @dref element tree.]"
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

                if (semantic_blocked := await self._semantic_block(element, meta, action, text)) is not None:
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
                    # Remembered before delivery: the follow-up snapshot already reads the filled value back.
                    self._filled_secrets.remember(effective_text)
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
                    ax_result = replace(ax_result, error=self._filled_secrets.redact(ax_result.error))
                    if ax_result.failure is not AxFailure.UNSUPPORTED:
                        return _stopped_without_fallback(element, meta, ax_result)
                    # The fallback clicks the element before it types, so a text entry reaches the control as an
                    # activation here; an activation verb was gated before the native attempt.
                    if (
                        action in DESKTOP_TEXT_ACTIONS
                        and (click_blocked := await self._semantic_block(element, meta, "click", text)) is not None
                    ):
                        return click_blocked
                    bbox_result = await try_bbox_click(self, element, effective_action, effective_text, modifiers)
                    if not bbox_result.success:
                        bbox_error = self._filled_secrets.redact(bbox_result.error)
                        remedy_hint = (
                            f"[REMEDY_HINT: Action '{action}' on @{element.ref_id} failed via accessibility invocation "
                            f"({ax_result.error}) and bounding-box fallback ({bbox_error}). "
                            "The target window may be minimized, occluded, or scrolled off-screen. "
                            "Suggested remedies: 1) Call desktop_snapshot_tool(scope='foreground') to verify window state; "
                            "2) Call desktop_snapshot_tool(scope='target', app_name='...') to bring the app window forward; "
                            "3) Use desktop_vision_tool if the element is custom-rendered on canvas.]"
                        )
                        return (
                            f"desktop_interact failed for @{element.ref_id}: "
                            f"{ax_result.error}; bbox fallback: {bbox_error}\n{remedy_hint}"
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
