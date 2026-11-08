"""Element interaction — single responsibility.

[INPUT]
- patchright.async_api::Page (POS: Patchright page instance)
- snapshot::RefInfo (POS: element ref metadata)
- snapshot::resolve_locator (POS: rebuild Locator from RefInfo)
- exceptions::RefNotFoundError (POS: structured ref-not-found exception)
- pool.config::HumanizeConfig (POS: interaction humanization config)
- session.interactor_click_mixin::ClickInteractMixin (POS: Bézier-mouse click trajectory + reachability guard)
- session.interactor_scroll_mixin::ScrollHumanizeMixin (POS: humanized wheel-input scrolling behaviors)
- session.interactor_scroll_targeting_mixin::ScrollTargetingMixin (POS: CAREFUL pre-interaction target centering)
- session.interactor_coord_mixin::CoordInteractMixin (POS: coordinate-based Visual Mode interactions)
- session.interactor_ref_action_mixin::RefActionMixin (POS: ref verb dispatch on a resolved locator)
- session.ref_metrics::RefNotFoundMetrics, RefDiagnosticsMixin (POS: ref failure statistics + diagnosis behaviors)
- wait::settle_after_action, capped_note (POS: the wait an interaction ends with: the requests the action started, within a cap; the note for a wait that hit it)

[OUTPUT]
- Interactor: element interaction manager (supports humanized delays + Bézier mouse via HumanizeConfig)

[POS]
Element interaction manager. Responsibilities:
1. Ref-based operations (15 actions: click/dblclick/type/fill/fill_credential/press/hover/focus/select/scroll/scroll_to_bottom/upload_file/drag/check/uncheck)
2. Ref resolution (from ref ID to Locator, supports iframe refs)
3. Interaction timeout control (10s)
4. Ref failure diagnosis (URL change detection + smart suggestion generation + context refs sampling)
5. Failure monitoring (failure rate, hot refs, hot actions statistics + periodic log output)

Ref interaction orchestration lives here (action validation, ref resolution and
self-healing, the wait after the action in the element's own document with a note
on the answer when it hit its cap, the answers to a failed interaction); the
verbs themselves, humanized scrolling (wheel-burst delivery, honest reporting,
scroll_to_bottom progress loop), CAREFUL pre-interaction target centering,
Bézier-mouse click trajectory, coordinate interactions (interact_at), and
ref-failure diagnosis are provided by RefActionMixin, ScrollHumanizeMixin,
ScrollTargetingMixin, ClickInteractMixin, CoordInteractMixin, and
RefDiagnosticsMixin respectively. Single responsibility: only handles element
interaction logic; does not handle navigation, snapshot, extraction, etc.
Tab-level URL state is managed by TabController.
"""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import TYPE_CHECKING

from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.toolkits.browser.exceptions import RefNotFoundError
from myrm_agent_harness.toolkits.browser.pool.config import HumanizeConfig
from myrm_agent_harness.toolkits.browser.session.interactor_click_mixin import (
    ClickInteractMixin,
)
from myrm_agent_harness.toolkits.browser.session.interactor_coord_mixin import (
    CoordInteractMixin,
)
from myrm_agent_harness.toolkits.browser.session.interactor_ref_action_mixin import (
    RefActionMixin,
)
from myrm_agent_harness.toolkits.browser.session.interactor_scroll_mixin import (
    ScrollHumanizeMixin,
)
from myrm_agent_harness.toolkits.browser.session.interactor_scroll_targeting_mixin import (
    ScrollTargetingMixin,
)
from myrm_agent_harness.toolkits.browser.session.ref_metrics import (
    RefDiagnosticsMixin,
    RefNotFoundMetrics,
)
from myrm_agent_harness.toolkits.browser.snapshot import resolve_locator
from myrm_agent_harness.toolkits.browser.wait import capped_note, settle_after_action

if TYPE_CHECKING:
    from patchright.async_api import Frame, Locator, Page

    from myrm_agent_harness.toolkits.browser.snapshot import RefInfo

logger = logging.getLogger(__name__)
_VALID_ACTIONS = frozenset(
    {
        "click",
        "dblclick",
        "type",
        "fill",
        "press",
        "hover",
        "focus",
        "select",
        "scroll",
        "scroll_to_bottom",
        "upload_file",
        "drag",
        "check",
        "uncheck",
        "fill_credential",
    }
)
# Only the actions that move the pointer, the focus or the viewport start no request the next read depends on;
# every other action ends by waiting for the requests it started.
_NO_SETTLE_ACTIONS = frozenset({"hover", "focus", "scroll", "scroll_to_bottom"})


class Interactor(
    ScrollHumanizeMixin,
    ScrollTargetingMixin,
    CoordInteractMixin,
    ClickInteractMixin,
    RefDiagnosticsMixin,
    RefActionMixin,
):
    """Element interaction manager — single responsibility.

    Responsibilities:
    1. Ref-based actions (15 types: click/dblclick/type/fill/fill_credential/press/hover/focus/select/scroll/scroll_to_bottom/upload_file/drag/check/uncheck)
    2. Ref resolution (ref ID -> Locator, including iframe refs)
    3. Interaction timeout control (10 s)
    4. Ref-not-found diagnosis (URL change detection + smart suggestion generation + context ref sampling)
    5. Failure monitoring (failure rate, hot refs/actions statistics + periodic log output)

    The verbs (`_perform_ref_action`), scrolling (wheel-burst inertial delivery,
    honest reporting, CAREFUL pre-interaction target centering), Bézier-mouse
    click trajectory, coordinate interactions (interact_at), and ref-failure
    diagnosis (`_get_context_refs`/`_log_metrics_if_needed`) are inherited from
    RefActionMixin, ScrollHumanizeMixin, ScrollTargetingMixin, CoordInteractMixin,
    ClickInteractMixin, and RefDiagnosticsMixin.

    Not responsible for: navigation, snapshot generation, content extraction, etc.
    """

    def __init__(
        self,
        page: Page,
        refs: dict[str, RefInfo],
        last_snapshot_url: str | None = None,
        humanize: HumanizeConfig | None = None,
    ):
        """Initialize Interactor

        Args:
            page: Patchright Page Instance
            refs: Ref ID -> RefInfo mapping.
            last_snapshot_url: URL from the last snapshot (used for smart diagnosis on ref failure).
            humanize: Interaction humanization config. None defaults to FAST (no humanization).
        """
        self._page = page
        self._refs = refs
        self._metrics = RefNotFoundMetrics()
        self._last_snapshot_url = last_snapshot_url
        self._humanize = humanize or HumanizeConfig()
        self._mouse_x: float = 0.0
        self._mouse_y: float = 0.0

    def update_refs(
        self,
        refs: dict[str, RefInfo] | MappingProxyType[str, RefInfo],
        last_snapshot_url: str | None = None,
    ) -> None:
        """Update the refs mapping (called after each snapshot).

        Args:
            refs: New Ref ID -> RefInfo mapping (dict or MappingProxyType).
            last_snapshot_url: URL of this snapshot (for subsequent ref-failure diagnosis).
        """
        self._refs = dict(refs) if isinstance(refs, MappingProxyType) else refs
        if last_snapshot_url is not None:
            self._last_snapshot_url = last_snapshot_url

    def _resolve_frame(self, ref: str) -> Page | Frame:
        """Resolve ref to the corresponding Page or Frame instance.

        If ref starts with 'f', it's an iframe ref (e.g., f1_e0).
        Otherwise it's the main page.
        """
        if ref.startswith("f"):
            parts = ref.split("_", 1)
            if len(parts) == 2:
                frame_idx_str = parts[0][1:]
                try:
                    frame_idx = int(frame_idx_str)
                    if frame_idx < len(self._page.frames):
                        return self._page.frames[frame_idx]
                except ValueError:
                    pass
        return self._page

    async def _assert_not_password_field(self, locator: Locator, verb: str) -> None:
        """Refuse plain-text input into a password field.

        A ref locator may resolve to a password input; typing or filling plain
        text there would leak the secret into snapshots and logs. Agents must
        use the dedicated ``fill_credential`` action instead. ``verb`` reads
        naturally in the raised error ("typing" / "filling").
        """
        try:
            input_type = await locator.get_attribute("type", timeout=1000)
        except Exception:
            return
        if input_type and input_type.lower() == "password":
            raise ValueError(
                "SecurityError: Plain text "
                f"{verb} into a password field is strictly forbidden. "
                "You MUST use the 'fill_credential' action and provide the "
                "credential label instead of the plain text password."
            )

    async def interact(self, action: str, ref: str, text: str = "") -> str:
        """Execute an element interaction.

        Args:
            action: Interaction action (click/type/fill/...).
            ref: Element ref ID (e0/e1/f1_e0/...).
            text: Interaction text (required for type/fill/press/select).

        Returns:
            Description of the interaction result.

        Raises:
            ValueError: If the action is invalid.
            RefNotFoundError: If the ref does not exist (includes structured diagnosis).
        """
        if action not in _VALID_ACTIONS:
            raise ValueError(f"Invalid action: {action}, must be one of {_VALID_ACTIONS}")

        if ref not in self._refs:
            total_refs = len(self._refs)
            ref_ids = self._refs.keys()
            ref_range = f"{min(ref_ids)}-{max(ref_ids)}" if ref_ids else "none"
            context_refs = self._get_context_refs(max_total=15)

            self._metrics.record_interaction(failed=True, ref=ref, action=action)

            current_url = self._page.url

            logger.warning(
                "Ref not found: %s (action=%s, page=%s). Total refs: %d, Failure rate: %.1f%% (recent: %.1f%%)",
                ref,
                action,
                redact_sensitive_text(current_url)[:80],
                total_refs,
                self._metrics.failure_rate * 100,
                self._metrics.recent_failure_rate * 100,
            )

            self._log_metrics_if_needed()

            raise RefNotFoundError(
                ref=ref,
                total_refs=total_refs,
                ref_range=ref_range,
                context_refs=context_refs,
                last_snapshot_url=self._last_snapshot_url,
                context={
                    "action": action,
                    "text": text if text else None,
                    "page_url": current_url,
                },
            )

        self._metrics.record_interaction(failed=False)

        ref_info = self._refs[ref]
        frame = self._resolve_frame(ref)
        locator = resolve_locator(frame, ref_info)

        healed_msg = ""
        try:
            # Check if locator is attached. If DOM mutated significantly, this will timeout quickly.
            await locator.wait_for(state="attached", timeout=800)
        except Exception as detach_err:
            # Check if URL changed since snapshot, indicating page navigated or submitted
            current_url = getattr(self._page, "url", "")
            if current_url and self._last_snapshot_url:
                change_type, _, _ = RefNotFoundError._classify_url_change(self._last_snapshot_url, current_url)
                if change_type == "path":
                    raise RefNotFoundError(
                        ref=ref,
                        total_refs=len(self._refs),
                        ref_range=f"{min(self._refs.keys())}-{max(self._refs.keys())}" if self._refs else "none",
                        context_refs=[],
                        last_snapshot_url=self._last_snapshot_url,
                        context={"action": action, "text": text, "page_url": current_url},
                    ) from detach_err

            # Attempt spatial-fingerprint self-healing
            from myrm_agent_harness.toolkits.browser.snapshot.self_healer import (
                SelfHealer,
            )

            healed_loc, new_name, _distance = await SelfHealer.heal(frame, ref_info)
            if healed_loc:
                locator = healed_loc
                healed_msg = f" [Auto-Healed to '{new_name or ref_info.name}']"
                logger.info(f"Interactor: locator for {ref} self-healed.{healed_msg}")

        # CAREFUL-only: bring the target into the viewport center band with the same
        # humanized wheel stack used by explicit scrolls, instead of Playwright's
        # implicit one-shot scrollIntoViewIfNeeded (instant JS jump, CDP fingerprint).
        # Scroll actions own their own positioning, so they are excluded.
        if self._humanize.enable_bezier_mouse and action not in (
            "scroll",
            "scroll_to_bottom",
        ):
            await self._ensure_target_in_view(locator)

        try:
            result = await self._perform_ref_action(action, ref, text, locator, healed_msg)
            if action not in _NO_SETTLE_ACTIONS:
                result += capped_note(await settle_after_action(frame))
            return result
        except Exception as e:
            error_msg = str(e)
            target_closed = (
                "TargetClosedError" in error_msg or "Target closed" in error_msg or "has been closed" in error_msg
            )
            if target_closed:
                # A tab the user closed or that detached is a state the agent can act on, so it is answered, not raised.
                is_closed = True
                try:
                    is_closed = self._page.is_closed()
                except Exception:
                    is_closed = True
                if is_closed:
                    logger.warning(f"Browser interaction target closed: {error_msg}")
                    return (
                        f"Interaction failed: The browser tab was closed or detached ({error_msg}). "
                        "The target page is no longer available. Please inspect open tabs or ask the user."
                    )
            if target_closed or "Timeout" in error_msg:
                logger.warning("Browser interaction failed: %s", error_msg)
            raise
