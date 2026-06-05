"""Security Profile Manager — CRUD for named security configuration profiles.

Persists SecurityConfig snapshots as named profiles in the database.
Users can save, load, delete, and switch between profiles.
Builtin profiles (readonly, workspace, full_access) are seeded on first access.

[INPUT]
- app.database.models.security::SecurityProfile (ORM model)
- app.platform_utils::get_session_factory

[OUTPUT]
- ProfileManager: async CRUD service for security profiles

[POS]
Server-layer profile persistence and lifecycle management.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from sqlalchemy import select, update

from app.database.models.security import SecurityProfile
from app.platform_utils import get_session_factory

logger = logging.getLogger(__name__)

# Builtin profile definitions — seeded on first access
_BUILTIN_PROFILES: list[dict[str, object]] = [
    {
        "profile_key": "readonly",
        "display_name": "Read Only",
        "description": "No file writes, no shell, no browser mutations. For research and analysis.",
        "config_json": {
            "capabilities": [{"permission": "*", "pattern": "*"}],
            "permissions": {
                "file_write": "deny",
                "file_edit": "deny",
                "file_delete": "deny",
                "shell_exec": "deny",
                "code_interpreter": "deny",
                "browser_evaluate": "deny",
                "browser_fill": "deny",
                "browser_upload": "deny",
                "browser_download": "deny",
                "mcp_invoke": "ask",
                "delegate_agent": "allow",
            },
            "autoModeEnabled": False,
            "yoloModeEnabled": False,
        },
    },
    {
        "profile_key": "workspace",
        "display_name": "Workspace",
        "description": "File ops within allowed roots, shell requires approval.",
        "config_json": {
            "capabilities": [{"permission": "*", "pattern": "*"}],
            "permissions": {
                "shell_exec": "ask",
                "code_interpreter": "ask",
                "browser_evaluate": "deny",
                "browser_upload": "ask",
                "browser_download": "ask",
                "browser_fill": "ask",
                "mcp_invoke": "ask",
                "delegate_agent": "allow",
            },
            "autoModeEnabled": False,
            "yoloModeEnabled": False,
        },
    },
    {
        "profile_key": "full_access",
        "display_name": "Full Access",
        "description": "All operations allowed, YOLO mode enabled. For trusted local environments.",
        "config_json": {
            "capabilities": [{"permission": "*", "pattern": "*"}],
            "permissions": {"*": "allow"},
            "autoModeEnabled": False,
            "yoloModeEnabled": True,
        },
    },
]


def _serialize_config(config_dict: dict[str, object]) -> dict[str, object]:
    """Normalize config dict for JSON storage (ensure serializable)."""
    return json.loads(json.dumps(config_dict, default=str))


class ProfileManager:
    """Async CRUD service for security profiles.

    Builtin profiles are seeded lazily on first ``list_all()`` call.
    Builtin profiles cannot be deleted or overwritten — only cloned.
    """

    async def list_all(self) -> list[dict[str, object]]:
        """List all profiles, seeding builtins if needed."""
        await self._ensure_builtins()
        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(SecurityProfile).order_by(SecurityProfile.is_builtin.desc(), SecurityProfile.profile_key)
            )
            profiles = result.scalars().all()
            return [_to_dict(p) for p in profiles]

    async def get(self, profile_key: str) -> dict[str, object] | None:
        """Get a single profile by key."""
        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await session.execute(select(SecurityProfile).where(SecurityProfile.profile_key == profile_key))
            profile = result.scalar_one_or_none()
            return _to_dict(profile) if profile else None

    async def get_active(self) -> dict[str, object] | None:
        """Get the currently active profile."""
        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await session.execute(select(SecurityProfile).where(SecurityProfile.is_active.is_(True)))
            profile = result.scalar_one_or_none()
            return _to_dict(profile) if profile else None

    async def activate(self, profile_key: str) -> dict[str, object] | None:
        """Set a profile as active (deactivates all others)."""
        session_factory = get_session_factory()
        async with session_factory() as session:
            # Deactivate all
            await session.execute(update(SecurityProfile).values(is_active=False))
            # Activate target
            result = await session.execute(select(SecurityProfile).where(SecurityProfile.profile_key == profile_key))
            profile = result.scalar_one_or_none()
            if profile is None:
                await session.commit()
                return None
            profile.is_active = True
            await session.commit()
            await session.refresh(profile)
            logger.info("Activated security profile: %s", profile_key)
            return _to_dict(profile)

    async def save(
        self,
        profile_key: str,
        display_name: str,
        config_json: dict[str, object],
        *,
        description: str | None = None,
    ) -> dict[str, object]:
        """Create or update a custom profile.

        Cannot overwrite builtin profiles — raises ValueError.
        """
        if profile_key in ("readonly", "workspace", "full_access"):
            raise ValueError(f"Cannot overwrite builtin profile '{profile_key}'. Clone it instead.")

        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await session.execute(select(SecurityProfile).where(SecurityProfile.profile_key == profile_key))
            existing = result.scalar_one_or_none()

            if existing:
                existing.display_name = display_name
                existing.description = description
                existing.config_json = _serialize_config(config_json)
                existing.updated_at = datetime.now()
                await session.commit()
                await session.refresh(existing)
                logger.info("Updated security profile: %s", profile_key)
                return _to_dict(existing)

            new_profile = SecurityProfile(
                id=str(uuid.uuid4()),
                profile_key=profile_key,
                display_name=display_name,
                description=description,
                config_json=_serialize_config(config_json),
                is_builtin=False,
                is_active=False,
            )
            session.add(new_profile)
            await session.commit()
            await session.refresh(new_profile)
            logger.info("Created security profile: %s", profile_key)
            return _to_dict(new_profile)

    async def delete(self, profile_key: str) -> bool:
        """Delete a custom profile. Builtin profiles cannot be deleted."""
        if profile_key in ("readonly", "workspace", "full_access"):
            raise ValueError(f"Cannot delete builtin profile '{profile_key}'.")

        session_factory = get_session_factory()
        async with session_factory() as session:
            result = await session.execute(select(SecurityProfile).where(SecurityProfile.profile_key == profile_key))
            profile = result.scalar_one_or_none()
            if profile is None:
                return False
            await session.delete(profile)
            await session.commit()
            logger.info("Deleted security profile: %s", profile_key)
            return True

    async def clone(self, source_key: str, new_key: str, new_display_name: str) -> dict[str, object]:
        """Clone an existing profile under a new key."""
        source = await self.get(source_key)
        if source is None:
            raise ValueError(f"Source profile '{source_key}' not found.")
        config = source.get("config_json")
        if not isinstance(config, dict):
            raise ValueError(f"Source profile '{source_key}' has invalid config.")
        return await self.save(
            profile_key=new_key,
            display_name=new_display_name,
            config_json=config,
            description=f"Cloned from '{source_key}'",
        )

    async def _ensure_builtins(self) -> None:
        """Seed builtin profiles if they don't exist yet."""
        session_factory = get_session_factory()
        async with session_factory() as session:
            for builtin in _BUILTIN_PROFILES:
                key = str(builtin["profile_key"])
                result = await session.execute(select(SecurityProfile).where(SecurityProfile.profile_key == key))
                if result.scalar_one_or_none() is None:
                    profile = SecurityProfile(
                        id=str(uuid.uuid4()),
                        profile_key=key,
                        display_name=str(builtin["display_name"]),
                        description=str(builtin.get("description", "")),
                        config_json=_serialize_config(dict(builtin["config_json"])),  # type: ignore[arg-type]
                        is_builtin=True,
                        is_active=False,
                    )
                    session.add(profile)
            await session.commit()


def _to_dict(profile: SecurityProfile) -> dict[str, object]:
    """Convert ORM model to API-friendly dict."""
    return {
        "id": profile.id,
        "profile_key": profile.profile_key,
        "display_name": profile.display_name,
        "description": profile.description,
        "config_json": profile.config_json,
        "is_builtin": profile.is_builtin,
        "is_active": profile.is_active,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
        "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
    }
