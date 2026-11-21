"""Seeding helpers shared by the hosting API integration tests."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.artifacts.listener import upsert_processor_artifact
from app.core.artifacts.source_path import to_source_path
from app.services.hosting.targets import save_hosting_targets
from app.services.hosting.types import HostingTarget

CHAT_ID = "chat-hosting-int"


def public_dns(*_args: object, **_kwargs: object) -> list[tuple[int, int, int, str, tuple[str, int]]]:
    return [(2, 1, 6, "", ("8.8.8.8", 0))]


async def seed_webhook_target(db_session: AsyncSession, target_id: str) -> None:
    await save_hosting_targets(
        db_session,
        [
            HostingTarget(
                id=target_id,
                name="CI Webhook",
                provider_type="http_webhook",
                config={"webhook_url": "https://hooks.example.com/publish"},
                is_default=True,
            )
        ],
    )


async def seed_html_artifact(db_session: AsyncSession, workspace, *, file_id: str | None = None) -> str:
    html_path = workspace / "index.html"
    html_path.write_text("<html><body><h1>Integration</h1></body></html>", encoding="utf-8")
    artifact_id = file_id or f"hosting-int-{uuid.uuid4().hex[:8]}"
    await upsert_processor_artifact(
        db_session,
        file_id=artifact_id,
        filename="index.html",
        sandbox_path=str(html_path),
        workspace_root=str(workspace),
        chat_id=CHAT_ID,
        source_path=to_source_path(str(html_path), str(workspace)),
    )
    return artifact_id
