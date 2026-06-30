"""Hosting provider protocol for artifact publication.

[POS] Provider-agnostic contract for packaging and publishing artifacts.

[INPUT]
- app.services.hosting.packager::PublishFile (POS: deployable file payload)

[OUTPUT]
- HostingProvider Protocol: preflight, publish, and status polling hooks
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.services.hosting.packager import PublishFile
from app.services.hosting.types import HostingTarget, PublicationResult


@runtime_checkable
class HostingProvider(Protocol):
    provider_type: str

    async def test_connection(self, target: HostingTarget, credentials: dict[str, object]) -> tuple[bool, str]:
        """Return (ok, message)."""
        ...

    async def publish(
        self,
        *,
        target: HostingTarget,
        credentials: dict[str, object],
        artifact_id: str,
        artifact_name: str,
        files: dict[str, PublishFile],
        existing_project_ref: str | None,
    ) -> PublicationResult:
        ...

    async def poll_status(
        self,
        *,
        target: HostingTarget,
        credentials: dict[str, object],
        publication_id: str,
    ) -> dict[str, str]:
        ...
