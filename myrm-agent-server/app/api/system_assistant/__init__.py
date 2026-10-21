"""
[INPUT]
- routes.py::router (POS: System Assistant and Multi-Agent Orchestration APIRouter)

[OUTPUT]
- router: Re-exported APIRouter instance for global API registry

[POS]
Package entry point for system assistant module.
"""

from .routes import router

__all__ = ["router"]
