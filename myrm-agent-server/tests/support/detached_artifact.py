"""A detached ``Artifact`` whose versions are set in memory.

[OUTPUT]
- make_detached_artifact: Artifact with eagerly assigned ``versions``, so code that reads them needs no lazy load

[POS]
tests/support/detached_artifact.py
Shared by the share tests that stub the artifact resolver with a hand-built artifact.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.database.models.artifact import Artifact, ArtifactVersion


def make_detached_artifact(*, artifact_id: str, name: str, chat_id: str | None, versions: Iterable[ArtifactVersion]) -> Artifact:
    """Build a detached Artifact with eagerly-set versions (no lazy load)."""
    artifact = Artifact(id=artifact_id, name=name, chat_id=chat_id, is_deleted=False)
    artifact.versions = list(versions)
    return artifact
