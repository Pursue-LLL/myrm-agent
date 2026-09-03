"""Personal Data Sovereignty & Takeout Archive Export Service.

[INPUT]
- app.config.settings::get_settings (POS: System paths & deploy mode)
- app.database.operations.backup::get_sqlite_backup_manager (POS: SQLite online consistent hot-backup)

[OUTPUT]
- UserTakeoutService.build_takeout_zip: Non-blocking scoped export of user data assets (DB, Wiki, Skills, Deliverables)

[POS]
Generates a structured, portable, and standard ZIP archive containing all user
assets (SQLite transactional snapshot, Markdown Wiki vault, custom skills, and deliverables)
for offline desktop migration and full data sovereignty.
"""

from __future__ import annotations

import io
import json
import logging
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.config.deploy_mode import get_deploy_mode
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

# Max asset size per file when archiving deliverables to avoid OOM / freeze (50 MB)
_MAX_FILE_BYTES_TO_ARCHIVE = 50 * 1024 * 1024


class UserTakeoutService:
    """Orchestrates comprehensive user data asset aggregation into a portable Takeout ZIP."""

    @classmethod
    async def build_takeout_zip(
        cls,
        include_db: bool = True,
        include_wiki: bool = True,
        include_skills: bool = True,
        include_deliverables: bool = True,
    ) -> bytes:
        """Assemble all core personal assets into a structured ZIP archive in memory."""
        settings = get_settings()
        state_dir = Path(settings.database.state_dir)
        deploy_mode = get_deploy_mode().value

        timestamp = datetime.now(timezone.utc).isoformat()
        manifest: dict[str, object] = {
            "version": "1.0.0",
            "format": "myrm-takeout",
            "exported_at": timestamp,
            "source_deploy_mode": deploy_mode,
            "contents": {},
        }

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            # 1. SQLite Database Online Consistent Hot-Backup
            if include_db:
                db_file = state_dir / "data.db"
                if db_file.exists():
                    db_bytes = cls._create_sqlite_backup_bytes(db_file)
                    if db_bytes:
                        zf.writestr("db/data.db", db_bytes)
                        manifest["contents"]["db"] = {
                            "file": "db/data.db",
                            "size_bytes": len(db_bytes),
                        }

            # 2. Wiki Knowledge Base (Markdown files)
            if include_wiki:
                wiki_dir = state_dir / "wiki"
                if wiki_dir.exists() and wiki_dir.is_dir():
                    wiki_count = cls._archive_directory(zf, wiki_dir, "wiki")
                    manifest["contents"]["wiki"] = {
                        "path": "wiki/",
                        "file_count": wiki_count,
                    }

            # 3. User Custom Skills
            if include_skills:
                skills_dir = state_dir / "skills"
                if skills_dir.exists() and skills_dir.is_dir():
                    skills_count = cls._archive_directory(zf, skills_dir, "skills")
                    manifest["contents"]["skills"] = {
                        "path": "skills/",
                        "file_count": skills_count,
                    }

            # 4. User Workspace Deliverables / Artifacts
            if include_deliverables:
                deliverables_dir = state_dir / "workspace_deliverables"
                if deliverables_dir.exists() and deliverables_dir.is_dir():
                    deliverables_count = cls._archive_directory(zf, deliverables_dir, "deliverables")
                    manifest["contents"]["deliverables"] = {
                        "path": "deliverables/",
                        "file_count": deliverables_count,
                    }

            # 5. Manifest metadata
            manifest_bytes = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
            zf.writestr("manifest.json", manifest_bytes)

        return zip_buffer.getvalue()

    @classmethod
    def _create_sqlite_backup_bytes(cls, src_db_path: Path) -> bytes | None:
        """Create a consistent online SQLite backup without locking or dirty reads."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)

        try:
            src_conn = sqlite3.connect(str(src_db_path), timeout=5.0)
            dest_conn = sqlite3.connect(str(tmp_path))
            try:
                src_conn.backup(dest_conn)
            finally:
                dest_conn.close()
                src_conn.close()

            return tmp_path.read_bytes()
        except Exception as exc:
            logger.error("Failed to create SQLite backup for takeout: %s", exc)
            return None
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    @classmethod
    def _archive_directory(cls, zf: zipfile.ZipFile, root_dir: Path, target_subfolder: str) -> int:
        """Recursively add files from a directory into the zip with relative paths."""
        count = 0
        for entry in root_dir.rglob("*"):
            if not entry.is_file():
                continue
            # Skip hidden temporary/lock files
            if entry.name.startswith(".") or entry.name.endswith(".tmp") or entry.name.endswith(".lock"):
                continue

            try:
                size = entry.stat().st_size
                if size > _MAX_FILE_BYTES_TO_ARCHIVE:
                    logger.warning("Skipping file %s because size %d exceeds limit", entry, size)
                    continue

                rel_path = entry.relative_to(root_dir)
                archive_name = f"{target_subfolder}/{rel_path.as_posix()}"
                zf.write(entry, arcname=archive_name)
                count += 1
            except Exception as exc:
                logger.warning("Failed to archive file %s: %s", entry, exc)

        return count
