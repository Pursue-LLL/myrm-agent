"""
[INPUT]
- routes.py::router (POS: Developer server listening ports APIRouter)

[OUTPUT]
- router: Re-exported APIRouter instance for global API registry

[POS]
Package entry point for dev_ports module.
"""

from .routes import router

__all__ = ["router"]
