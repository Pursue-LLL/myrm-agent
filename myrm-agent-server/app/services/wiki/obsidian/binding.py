"""Obsidian Vault declarative binding and mtime watermark tracker.

[INPUT]
- pathlib::Path
- app.database.connection::get_session (POS: DB session)
- app.database.models.config::UserConfig (POS: Config store)

[OUTPUT]
- get_obsidian_vault_binding: Retrieve currently bound vault configuration.
- set_obsidian_vault_binding: Set or update bound vault path, watermark, and settings.
- scan_vault_mtime_watermark: Quick mtime check to compute modified or added markdown/canvas files.

[POS]
Business service layer for declarative Obsidian Vault binding.
Tracks local vault directory, last sync watermark, and calculates delta files.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select

from app.database.connection import get_session
from app.database.models.config import UserConfig

logger = logging.getLogger(__name__)

OBSIDIAN_VAULT_CONFIG_KEY = "obsidian_vault_binding"


@dataclass
class ObsidianVaultBinding:
    """Configured Obsidian Vault binding state."""

    vault_path: str
    is_active: bool = True
    last_sync_watermark: float = 0.0
    auto_sync_on_recall: bool = True
    allow_inbox_write: bool = True
    inbox_folder_name: str = "_Myrm_Inbox"
    created_at: float = 0.0
    updated_at: float = 0.0


@dataclass
class VaultDeltaScanResult:
    """Files added or modified since watermark."""

    vault_path: str
    total_files_scanned: int
    modified_files: list[str]  # relative paths
    new_watermark: float
    has_changes: bool


async def get_obsidian_vault_binding() -> ObsidianVaultBinding | None:
    """Fetch active Obsidian vault binding from user config."""
    async with get_session() as session:
        stmt = select(UserConfig).where(UserConfig.config_key == OBSIDIAN_VAULT_CONFIG_KEY)
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record or not record.config_value:
            return None

        val = record.config_value
        return ObsidianVaultBinding(
            vault_path=str(val.get("vault_path", "")),
            is_active=bool(val.get("is_active", True)),
            last_sync_watermark=float(val.get("last_sync_watermark", 0.0)),
            auto_sync_on_recall=bool(val.get("auto_sync_on_recall", True)),
            allow_inbox_write=bool(val.get("allow_inbox_write", True)),
            inbox_folder_name=str(val.get("inbox_folder_name", "_Myrm_Inbox")),
            created_at=float(val.get("created_at", 0.0)),
            updated_at=float(val.get("updated_at", 0.0)),
        )


async def set_obsidian_vault_binding(binding: ObsidianVaultBinding) -> ObsidianVaultBinding:
    """Persist or update Obsidian vault binding."""
    now = time.time()
    async with get_session() as session:
        stmt = select(UserConfig).where(UserConfig.config_key == OBSIDIAN_VAULT_CONFIG_KEY)
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()

        data = asdict(binding)
        data["updated_at"] = now
        if not data.get("created_at"):
            data["created_at"] = now

        if record:
            record.config_value = data
            record.version = f"{int(now * 1000)}_0"
            record.last_device_id = "server"
        else:
            new_record = UserConfig(
                id=f"cfg_{int(now * 1000)}_obsidian",
                config_key=OBSIDIAN_VAULT_CONFIG_KEY,
                config_value=data,
                version=f"{int(now * 1000)}_0",
                last_device_id="server",
                is_encrypted=False,
            )
            session.add(new_record)
        await session.commit()

    return binding


def scan_vault_mtime_watermark(
    vault_root: Path | str,
    watermark: float,
    *,
    extensions: tuple[str, ...] = (".md", ".canvas"),
) -> VaultDeltaScanResult:
    """Scan vault files whose mtime > watermark (O(N) stat, no content read)."""
    root = Path(vault_root)
    if not root.is_dir():
        return VaultDeltaScanResult(
            vault_path=str(vault_root),
            total_files_scanned=0,
            modified_files=[],
            new_watermark=watermark,
            has_changes=False,
        )

    scanned_count = 0
    modified: list[str] = []
    max_mtime = watermark

    for item in root.rglob("*"):
        if not item.is_file():
            continue
        # Exclude hidden files or folders like .obsidian, .git
        if any(part.startswith(".") for part in item.relative_to(root).parts):
            continue
        if item.suffix.lower() not in extensions:
            continue

        scanned_count += 1
        try:
            mtime = item.stat().st_mtime
            if mtime > watermark:
                rel = item.relative_to(root).as_posix()
                modified.append(rel)
                if mtime > max_mtime:
                    max_mtime = mtime
        except OSError:
            continue

    return VaultDeltaScanResult(
        vault_path=str(root),
        total_files_scanned=scanned_count,
        modified_files=modified,
        new_watermark=max_mtime,
        has_changes=len(modified) > 0,
    )
