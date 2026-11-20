"""desktop_snapshot: the AX tree of the foreground or a target app as @dref refs.

[INPUT]
- host::DesktopSessionHost (POS: typed session state and the view-emission methods)
- perception.ax_dispatch::capture_snapshot (POS: AX snapshot of the foreground or a target app)
- perception.ax_diff::compute_ref_diff, perception.renderer::render_diff_tree, render_snapshot_tree (POS: incremental and full tree text)
- som_overlay::build_som_index_map (POS: numbered overlay indexes)
- iphone_mirror::is_iphone_mirror_app, probe_iphone_mirror_state (POS: connect-prompt gate hint)

[OUTPUT]
- DesktopSnapshotMixin: desktop_snapshot (screen guard, sensitive-app guard, registry replace, diff or full tree, optional annotated screenshot)

[POS]
Read-only perception entry of the semantic desktop tools; it is the only writer of the @dref registry besides the
inspector refresh and the approval revalidation.
"""

from __future__ import annotations

import asyncio
import logging
import time

from myrm_agent_harness.toolkits.computer_use.dref.errors import AXPermissionRequiredError, AXTreeEmptyError
from myrm_agent_harness.toolkits.computer_use.dref.types import SnapshotScope
from myrm_agent_harness.toolkits.computer_use.iphone_mirror import (
    is_iphone_mirror_app,
    probe_iphone_mirror_state,
)
from myrm_agent_harness.toolkits.computer_use.perception.ax_diff import compute_ref_diff
from myrm_agent_harness.toolkits.computer_use.perception.ax_dispatch import capture_snapshot
from myrm_agent_harness.toolkits.computer_use.perception.renderer import (
    render_diff_tree,
    render_snapshot_tree,
)
from myrm_agent_harness.toolkits.computer_use.som_overlay import build_som_index_map
from myrm_agent_harness.toolkits.computer_use.types import IPhoneMirrorState

from .host import DesktopSessionHost

logger = logging.getLogger(__name__)


class DesktopSnapshotMixin(DesktopSessionHost):
    """AX snapshot entry of the desktop session."""

    async def desktop_snapshot(
        self,
        scope: SnapshotScope = "foreground",
        app_name: str | None = None,
        include_screenshot: bool = False,
        query: str | None = None,
        role: str | None = None,
        wait_seconds: float = 0.0,
    ) -> str | list[object]:
        from myrm_agent_harness.toolkits.computer_use import safety

        if wait_seconds > 0:
            effective_delay = min(max(float(wait_seconds), 0.0), 10.0)
            await asyncio.sleep(effective_delay)

        if (refusal := await self._screen_guard.refusal(snapshot=True)) is not None:
            return refusal

        try:
            meta, refs = capture_snapshot(self._backend, scope, app_name=app_name, query=query, role=role)
        except AXPermissionRequiredError as exc:
            await self._emit_permission_view_update()
            return str(exc)
        except AXTreeEmptyError as exc:
            return str(exc)

        blocked = safety.is_sensitive_app(meta.app_name, meta.window_title, meta.app_id)
        if blocked:
            logger.warning("[SECURITY] Sensitive app guard: %s (app=%s)", blocked, meta.app_name)
            return f"Safety: {blocked}"

        prev_refs = self._refs.all_refs()
        prev_meta = self._refs.meta

        self._refs.replace(refs, meta)
        self._last_snapshot_time = time.time()

        som_index_map = build_som_index_map(refs) if include_screenshot else None

        use_diff = False
        diff_text = ""
        if not include_screenshot and prev_refs:
            diff = compute_ref_diff(prev_refs, refs, prev_meta, meta)
            if not diff.use_full_view:
                diff_text, enriched_meta = render_diff_tree(meta, diff)
                use_diff = True

        if not use_diff:
            tree_text, enriched_meta = render_snapshot_tree(meta, refs, som_index_map=som_index_map)
        else:
            tree_text = diff_text

        self._last_tree_text = tree_text

        screenshot_b64 = ""
        screenshot_size = (0, 0)
        if include_screenshot:
            target_app = app_name if scope == "target" else None
            shot = await self.take_screenshot(app_name=target_app)
            screenshot_b64 = self._annotate_screenshot_som(
                shot.screenshot_base64,
                refs,
                som_index_map,
            )
            screenshot_size = shot.screenshot_size

        await self._emit_view_update(
            screenshot_base64=screenshot_b64,
            screenshot_size=screenshot_size,
            refs=refs,
            meta=enriched_meta,
            som_index_map=som_index_map,
        )

        header = f"Desktop snapshot ready ({enriched_meta.ref_count} refs, ~{enriched_meta.token_estimate} tokens)."
        if is_iphone_mirror_app(meta.app_name, meta.app_id):
            probe = probe_iphone_mirror_state()
            if probe.state == IPhoneMirrorState.BLOCKED_CONNECT_PROMPT:
                header = f"{header}\n[IPHONE_MIRROR_GATE] {probe.detail} {probe.remedy_hint}"
        if include_screenshot and screenshot_b64:
            from langchain_core.messages.content import create_image_block, create_text_block

            blocks: list[object] = [
                create_text_block(f"{header}\n\n{tree_text}"),
                create_image_block(base64=screenshot_b64, mime_type="image/jpeg"),
            ]
            return blocks
        return f"{header}\n\n{tree_text}"
