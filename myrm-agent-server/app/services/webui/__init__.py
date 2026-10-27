"""WebUI service package.

[INPUT]
- Submodules: auth_service, session, access_policy, admin_store, passwords, temp_token, pending_setup_store, protection_store, qrcode, og_metadata

[OUTPUT]
- No re-exports; callers import the submodules directly

[POS]
app.services.webui: package namespace for WebUI domain services (auth, access policy, QR codes, link previews).
"""

from __future__ import annotations

__all__ = []
