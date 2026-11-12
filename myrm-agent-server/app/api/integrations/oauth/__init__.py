"""OAuth endpoints of the integrations API.

[INPUT]
- none (the integrations router mounts each module's `router` under its own prefix)

[OUTPUT]
- package marker; the routers live in the credentials, mcp, google_workspace, provider and xai modules

[POS]
Package marker of the integrations OAuth endpoints: each module exposes its own router, which the integrations router mounts
under that module's prefix.
"""
