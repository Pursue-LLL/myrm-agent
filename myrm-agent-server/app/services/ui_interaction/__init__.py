"""UI Interaction Service Module.

[INPUT]
- ui_request_manager from .ui_request_manager

[OUTPUT]
- UIRequestManager, get_ui_request_manager

[POS]
Server-side coordination layer for bi-directional Extension UI interactions (Item 28).
Strictly typed, zero `Any`.
"""

from __future__ import annotations

from .ui_request_manager import UIRequestManager, get_ui_request_manager

__all__ = [
    "UIRequestManager",
    "get_ui_request_manager",
]
