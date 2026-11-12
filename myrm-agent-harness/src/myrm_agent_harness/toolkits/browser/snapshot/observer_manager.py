"""MutationObserver management for change detection.

[INPUT]
- (none)

[OUTPUT]
- ObserverManager: class — Observer Manager

[POS]
MutationObserver management for change detection.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

from ..exceptions import AriaCrossOriginError
from .observer_scripts import MUTATION_OBSERVER_SCRIPT

if TYPE_CHECKING:
    from patchright.async_api import Frame, Page

logger = logging.getLogger(__name__)


class ObserverManager:
    """MutationObserver manager.

    Responsibilities:
    - Install and detach MutationObserver
    - Detect cross-origin iframes
    - Get DOM change records
    """

    def __init__(self, frame: Page | Frame):
        """Initialize the observer manager.

        Args:
            frame: Page or Frame instance.
        """
        self._frame = frame
        self._installed = False
        self._is_cross_origin = False

    async def install(self) -> None:
        """Install the MutationObserver on the frame."""
        try:
            await asyncio.wait_for(self._frame.evaluate(MUTATION_OBSERVER_SCRIPT), timeout=2.0)
            self._installed = True
            logger.info("MutationObserver installed")
        except Exception as exc:
            error = AriaCrossOriginError(
                "Failed to install observer (likely cross-origin)",
                cause=exc,
            )
            logger.warning(str(error))
            self._is_cross_origin = True
            self._installed = False

    async def ensure_active(self) -> bool:
        """Ensure an observer is watching the current document's live body.

        The observer is an object inside the page, and two things leave it behind:
        - a new document: a link click, form submit or script redirect loads another
          page, and the object installed in the old one is gone with it;
        - a replaced body: pages can swap ``document.body`` without navigating
          (``document.write``, SPA full re-render, ``innerHTML`` swap on body), and
          the observer keeps watching the detached body and reports no changes.
        Either way the cached snapshot no longer describes the page.

        Returns:
            True when an observer was installed or re-anchored, so the cached
            snapshot is out of date; False when it already watches the current body.
        """
        try:
            re_anchored = await asyncio.wait_for(
                self._frame.evaluate("() => window.__ariaObserver ? window.__ariaObserver.ensureActive() : null"),
                timeout=2.0,
            )
        except Exception as exc:
            error = AriaCrossOriginError(
                "Failed to ensure observer active (likely cross-origin)",
                cause=exc,
            )
            logger.warning(str(error))
            self._is_cross_origin = True
            self._installed = False
            return False
        if re_anchored is None:
            await self.install()
            return self._installed
        if re_anchored:
            self._installed = True
            return True
        return False

    async def get_changes(self) -> list[dict[str, str]]:
        """Get DOM change records.

        Returns:
            List of changes, format: [{type, target, ...}]
        """
        try:
            changes = await asyncio.wait_for(
                self._frame.evaluate("() => window.__ariaObserver ? window.__ariaObserver.getChanges() : []"),
                timeout=1.0,
            )
            return changes if isinstance(changes, list) else []
        except Exception as exc:
            logger.warning(f"Failed to get changes: {exc}")
            return []

    async def disconnect(self) -> None:
        """Disconnect the MutationObserver."""
        if self._installed and not self._is_cross_origin:
            with contextlib.suppress(Exception):
                await self._frame.evaluate("() => window.__ariaObserver && window.__ariaObserver.disconnect()")

    def reset(self) -> None:
        """Reset state."""
        self._installed = False
        self._is_cross_origin = False

    @property
    def is_installed(self) -> bool:
        """Whether the observer is already installed."""
        return self._installed

    @property
    def is_cross_origin(self) -> bool:
        """Whether the frame is a cross-origin iframe."""
        return self._is_cross_origin
