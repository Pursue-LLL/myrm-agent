"""Control Plane → sandbox archive import endpoint.

[INPUT]
- Control Plane HTTP POST with archive path to import

[OUTPUT]
- POST /api/admin/import-archive: Import a tar.gz backup into /persistent

[POS]
CP-to-sandbox internal endpoint for employee offboarding volume transfer.
Receives path to a tar.gz archive and extracts it into the sandbox persistent volume.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

PERSISTENT_DIR = Path("/persistent")


class ImportArchiveRequest(BaseModel):
    archive_path: str
    merge_mode: str = "overlay"


class ImportArchiveResponse(BaseModel):
    status: str
    files_imported: int
    message: str


@router.post("/admin/import-archive", tags=["internal"])
async def import_archive(body: ImportArchiveRequest) -> ImportArchiveResponse:
    """Import a tar.gz archive into the sandbox persistent volume.

    merge_mode:
        - "overlay": Extract on top of existing data (default)
        - "replace": Clear persistent dir first, then extract
    """
    archive = Path(body.archive_path)
    if not archive.exists():
        raise HTTPException(status_code=404, detail=f"Archive not found: {body.archive_path}")
    if not archive.suffix == ".gz" and not archive.name.endswith(".tar.gz"):
        raise HTTPException(status_code=400, detail="Archive must be .tar.gz format")

    if body.merge_mode not in ("overlay", "replace"):
        raise HTTPException(status_code=400, detail="merge_mode must be 'overlay' or 'replace'")

    if body.merge_mode == "replace":
        for item in PERSISTENT_DIR.iterdir():
            if item.name.startswith("."):
                continue
            if item.is_dir():
                import shutil
                shutil.rmtree(item)
            else:
                item.unlink()

    try:
        proc = await asyncio.create_subprocess_exec(
            "tar", "-xzf", str(archive), "-C", str(PERSISTENT_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

        if proc.returncode != 0:
            err_msg = stderr.decode().strip() if stderr else "Unknown extraction error"
            raise HTTPException(status_code=500, detail=f"Archive extraction failed: {err_msg}")

        file_count = sum(1 for _ in PERSISTENT_DIR.rglob("*") if _.is_file())

        logger.info("Archive imported: %s (%d files)", archive.name, file_count)
        return ImportArchiveResponse(
            status="success",
            files_imported=file_count,
            message=f"Archive {archive.name} imported successfully",
        )

    except asyncio.TimeoutError as e:
        raise HTTPException(status_code=504, detail="Archive extraction timed out") from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Archive import failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Import failed: {e}") from e
