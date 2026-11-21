"""Semantic desktop control session: AX snapshot, @dref registry, interact, vision and WebUI views.

[INPUT]
- .core::DesktopSession, create_desktop_session

[OUTPUT]
- DesktopSession, create_desktop_session

[POS]
Facade of the desktop session package; the implementation lives in the mixin modules composed by core.
"""

from __future__ import annotations

from .core import DesktopSession, create_desktop_session

__all__ = ["DesktopSession", "create_desktop_session"]
