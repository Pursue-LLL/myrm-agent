"""Mark integration-backed prebuilt skills unavailable when OAuth is disconnected.

[INPUT]
- app.services.integrations.oauth_store (POS: encrypted oauthCredentials row)
- app.core.skills.models::Skill (POS: prebuilt skill list entries)

[OUTPUT]
- is_google_workspace_oauth_connected: bool probe for Settings OAuth state
- apply_integration_oauth_availability: mutates Skill.available / unavailable_reason

[POS]
Skills API layer guard — hides google-workspace prebuilt skill when OAuth disconnected.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.skills.models import Skill
from app.services.agent.oauth_refresher import GOOGLE_WORKSPACE_ISSUER
from app.services.integrations.oauth_store import (
    decrypt_oauth_credentials,
    load_oauth_credentials_row,
)

GOOGLE_WORKSPACE_SKILL_ID = "google-workspace"
GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE = (
    "Connect Google Workspace in Settings → Integrations → Credentials"
)


async def is_google_workspace_oauth_connected(db: AsyncSession) -> bool:
    row = await load_oauth_credentials_row(db)
    if not row:
        return False
    credentials = decrypt_oauth_credentials(row.config_value, row.is_encrypted)
    cred_val = credentials.get(GOOGLE_WORKSPACE_ISSUER)
    return isinstance(cred_val, dict) and bool(cred_val.get("token"))


async def apply_integration_oauth_availability(
    skills: list[Skill],
    db: AsyncSession,
) -> None:
    """Set available=False when a skill requires OAuth that is not connected."""
    needs_google = any(skill.id == GOOGLE_WORKSPACE_SKILL_ID for skill in skills)
    if not needs_google:
        return
    if await is_google_workspace_oauth_connected(db):
        return
    for skill in skills:
        if skill.id == GOOGLE_WORKSPACE_SKILL_ID:
            skill.available = False
            skill.unavailable_reason = GOOGLE_WORKSPACE_OAUTH_UNAVAILABLE
