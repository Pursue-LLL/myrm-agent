"""
[INPUT]
- routes.py router definition

[OUTPUT]
- router facade for self_evolution API

[POS]
Package facade for Designer's Eye Self-Evolution backend API.
"""

from .routes import router

__all__ = ["router"]
