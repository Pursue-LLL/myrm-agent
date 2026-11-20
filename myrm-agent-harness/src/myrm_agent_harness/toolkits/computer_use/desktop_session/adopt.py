"""Single write entry of the @dref registry.

[INPUT]
- host::DesktopSessionHost (POS: typed session state: the registry and the secrets the vault filled)
- perception.ax_diff::{RefDiff, diff_adopted} (POS: what a capture changed against the content the model was shown)
- safety (POS: sensitive-application name list)

[OUTPUT]
- Adoption: the refs of an accepted capture under registry ids, and the diff against what the model was last shown
- DesktopRegistryMixin: _adopt_capture (the only call site of DRefRegistry.adopt)

[POS]
Every capture the session registers (agent snapshot, approval revalidation, inspector refresh) passes through here,
so no writer can skip the sensitive-application check and register the elements of a blocked application, or the
masking of a control that holds a credential the vault filled.
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
        The diff is taken against what the model was last shown, not against the previous registry content: a
        capture that no tool result has reported yet (the re-read before an approved action) must still be reported
        by the next snapshot. A control that shows a credential the vault filled is registered as redacted, so no
        later read of the registry, the diff or the inspector carries the value.
        """
        if blocked := safety.is_sensitive_app(meta.app_name, meta.window_title, meta.app_id):
            logger.warning("[SECURITY] Sensitive app guard: %s (app=%s)", blocked, meta.app_name)
            return f"Safety: {blocked}"
        refs = self._refs.adopt(self._filled_secrets.mask(capture), meta)
        return Adoption(refs=refs, diff=diff_adopted(self._refs.shown_refs(), refs, self._refs.shown_meta, meta))
