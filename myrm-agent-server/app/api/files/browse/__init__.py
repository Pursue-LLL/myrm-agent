"""Workspace browse API.

[INPUT]
- .listing / .content / .search (POS: endpoint modules)

[OUTPUT]
- router

[POS]
Aggregate exit of the browse API package.
"""

from __future__ import annotations

from . import content, listing, search  # noqa: F401  (register routes)
from .common import router

__all__ = ["router"]
