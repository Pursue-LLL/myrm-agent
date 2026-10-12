"""
[INPUT]
- routes.py::router (POS: APIRouter for session_map endpoints)

[OUTPUT]
- router: Facade export for session_map API module

[POS]
Package facade for Project-Centric Session Map and Agent State Cockpit API.
"""

from .routes import router

__all__ = ["router"]
