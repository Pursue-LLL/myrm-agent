"""[POS]: app/services/memory/progressive_sidecar_service.py
[INPUT]: ContextVirtualFileSystem dependency and progressive sidecar requests.
[OUTPUT]: ProgressiveSidecarService delivering business orchestration for L0/L1/L2 sidecars.
"""

from myrm_agent_harness.toolkits.memory import (
    ContextTier,
    ContextVirtualFileSystem,
    ProgressiveContextBundle,
    ProgressiveContextVFSAdapter,
    ProgressiveReadResult,
    ProgressiveSidecarEngine,
)

from app.services.memory.cvfs import get_context_vfs


class ProgressiveSidecarService:
    """Service orchestrating three-tier progressive context sidecar generation and tiered retrieval."""

    def __init__(self, vfs: ContextVirtualFileSystem | None = None) -> None:
        self.vfs = vfs or get_context_vfs()
        self.adapter = ProgressiveContextVFSAdapter(vfs=self.vfs)

    def generate_bundle(
        self,
        uri: str,
        content: str,
        title: str = "",
    ) -> ProgressiveContextBundle:
        """Synthesize three-tier bundle in memory without persisting to VFS."""
        return ProgressiveSidecarEngine.generate_bundle(
            doc_id=uri,
            content=content,
            title=title,
        )

    def write_with_sidecars(
        self,
        uri: str,
        content: str,
        title: str = "",
        metadata: dict[str, str] | None = None,
    ) -> ProgressiveContextBundle:
        """Persist document and companion L0/L1 sidecars into Context VFS."""
        return self.adapter.write_with_sidecars(
            uri=uri,
            content=content,
            title=title,
            metadata=metadata,
        )

    def read_tiered(
        self,
        uri: str,
        tier: ContextTier,
    ) -> ProgressiveReadResult:
        """Read document at specified granularity tier with dynamic fallback generation."""
        return self.adapter.read_tiered(
            uri=uri,
            tier=tier,
        )


_service_instance: ProgressiveSidecarService | None = None


def get_progressive_sidecar_service() -> ProgressiveSidecarService:
    """Dependency injection provider for ProgressiveSidecarService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = ProgressiveSidecarService()
    return _service_instance
