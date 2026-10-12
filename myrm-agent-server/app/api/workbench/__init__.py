"""[INPUT]
- .routes::workbench_router

[OUTPUT]
- workbench_router: Top-level API router for Workbench multi-tab auxiliary system

[POS]
Package entry point for app.api.workbench.
"""

from .routes import workbench_router

__all__ = ["workbench_router"]
