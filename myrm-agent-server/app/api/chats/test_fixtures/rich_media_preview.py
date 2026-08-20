"""Local-only workspace rich-media preview Chrome E2E seed routes.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: local/tauri gate)
app.services.agent.agent_service::AgentService (POS: agent list for seed scope)
app.services.chat.chat_service::ChatService (POS: chat/message persistence)
app.services.agent.params.workspace_resolve::resolve_default_chat_workspace_dir (POS: workspace path)

[OUTPUT]
seed_rich_media_preview_fixture: chat + workspace rich-media files (png/pdf/zip/txt)
for the workspace browser preview Chrome E2E.

[POS]
Mounted via test_fixtures/__init__.py router include. Files are written to the
chat workspace on disk so the real /files/browse/content path (including binary
streaming) is exercised end-to-end.
"""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.agent.params.workspace_resolve import (
    resolve_default_chat_workspace_dir,
)
from app.services.chat.chat_service import ChatService

router = APIRouter()

_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _png_bytes() -> bytes:
    try:
        return base64.b64decode(_PNG_B64)
    except binascii.Error as exc:  # pragma: no cover - constant is verified valid
        raise HTTPException(status_code=500, detail="Invalid PNG fixture") from exc


def _minimal_pdf() -> bytes:
    """Build a minimal valid single-page PDF with a correct xref table."""
    bodies = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] >>",
    )
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, body in enumerate(bodies, start=1):
        offsets.append(len(out))
        out.extend(f"{index} 0 obj\n".encode("ascii"))
        out.extend(body + b"\nendobj\n")
    xref_pos = len(out)
    count = len(bodies) + 1
    out.extend(f"xref\n0 {count}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        out.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.extend(b"trailer\n<< /Size ")
    out.extend(str(count).encode("ascii"))
    out.extend(b" /Root 1 0 R >>\nstartxref\n")
    out.extend(str(xref_pos).encode("ascii"))
    out.extend(b"\n%%EOF\n")
    return bytes(out)


_FIXTURE_FILES: dict[str, bytes] = {
    "preview.png": _png_bytes(),
    "preview.pdf": _minimal_pdf(),
    "bundle.zip": b"PK\x03\x04rich-media-preview-placeholder",
    "readme.txt": b"rich media preview E2E fixture\n",
}


@router.post("/test/seed-rich-media-preview-fixture", include_in_schema=False)
async def seed_rich_media_preview_fixture(
    agent_id: str | None = None,
) -> dict[str, object]:
    """Local dev/test only: seed a chat whose workspace holds rich-media files."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500,
            detail="No agents available for rich-media preview E2E seed",
        )
    agent = agents[0]
    resolved_agent_id = (agent_id or "").strip() or agent.id

    chat_id = f"e2ermd{uuid4().hex[:8]}"

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Rich media preview Chrome E2E",
            agent_id=resolved_agent_id,
            messages=[],
        ),
    )

    # A user message is required so the frontend E2E bridge attachToChat
    # reports userCount >= 1 (the workspace merge fixture does the same).
    now = datetime.now(UTC)
    await ChatService.append_message(
        chat_id,
        "user",
        "Rich media preview E2E fixture question",
        now,
        "UTC",
    )

    # Resolve after the chat exists so the persisted chat.workspace_dir field
    # is actually updated (update_chat_fields is a silent SQL UPDATE otherwise).
    workspace_dir = await resolve_default_chat_workspace_dir(chat_id, persist_workspace=True)
    if not workspace_dir:
        raise HTTPException(
            status_code=500,
            detail="Failed to resolve workspace for rich-media preview E2E seed",
        )

    written: dict[str, str] = {}
    for name, payload in _FIXTURE_FILES.items():
        target = Path(workspace_dir) / name
        target.write_bytes(payload)
        written[name] = str(target)

    return {
        "chat_id": chat_id,
        "ui_path": f"/{chat_id}",
        "workspace_dir": str(workspace_dir),
        "files": written,
        "agent_id": resolved_agent_id,
    }
