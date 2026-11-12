"""Machines API package.

[INPUT]
- app.api.machines.router::router (POS: HTTP layer of the machines API: lists and reads the registry's machines, issues a registration command, and starts, releases or reads a machine's takeover session.)

[OUTPUT]
- router: the machines router that the main API router mounts

[POS]
Package facade of the machines API: exposes the router that the main API router mounts.
"""

from .router import router

__all__ = ["router"]
