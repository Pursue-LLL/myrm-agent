"""Single write entry of the @dref registry.

[INPUT]
- host::DesktopSessionHost (POS: typed session state: the registry)
- perception.ax_diff::{RefDiff, diff_adopted} (POS: what a capture changed against the registry content it replaces)
- safety (POS: sensitive-application name list)

[OUTPUT]
- Adoption: the refs of an accepted capture under registry ids, and the diff against the content they replaced
- DesktopRegistryMixin: _adopt_capture (the only call site of DRefRegistry.adopt)

[POS]
Every capture the session registers (agent snapshot, approval revalidation, inspector refresh) passes through here,
so no writer can skip the sensitive-application check and register the elements of a blocked application.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from myrm_agent_harness.toolkits.computer_use import safety
from myrm_agent_harness.toolkits.computer_use.dref.types import ElementRef, SnapshotMeta
from myrm_agent_harness.toolkits.computer_use.perception.ax_diff import RefDiff, diff_adopted

from .host import DesktopSessionHost

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Adoption:
    """A capture the registry accepted."""

    refs: dict[str, ElementRef]
    diff: RefDiff


class DesktopRegistryMixin(DesktopSessionHost):
    """Registration of captures in the @dref registry."""

    def _adopt_capture(self, meta: SnapshotMeta, capture: Mapping[str, ElementRef]) -> Adoption | str:
        """Register a capture, or return the refusal text when its application is on the sensitive list.

        A refused capture leaves the registry untouched, so no element of a sensitive application can be addressed.
        """
        if blocked := safety.is_sensitive_app(meta.app_name, meta.window_title, meta.app_id):
            logger.warning("[SECURITY] Sensitive app guard: %s (app=%s)", blocked, meta.app_name)
            return f"Safety: {blocked}"
        previous_refs, previous_meta = self._refs.all_refs(), self._refs.meta
        refs = self._refs.adopt(capture, meta)
        return Adoption(refs=refs, diff=diff_adopted(previous_refs, refs, previous_meta, meta))
