"""FastAPI router for Zero Knowledge Memory Vault and Provenance Watermarking (Item 159).

[INPUT]
- SealMemoryRequest, UnsealMemoryRequest, ExportDistilledRequest, VerifyWatermarkRequest.

[OUTPUT]
- EncryptedEnvelopeDTO, DistilledMemoryItemDTO, DistilledExportPackageDTO, ProvenanceWatermarkDTO.

[POS]
- Router endpoints in myrm-agent-server/app/api/memory/zk_vault_watermark_router.py.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.zk_vault_watermark import (
    DistilledExportPackageDTO,
    DistilledMemoryItemDTO,
    EncryptedEnvelopeDTO,
    ExportDistilledRequest,
    MemorySensitivityTierDTO,
    ProvenanceWatermarkDTO,
    ResidencyCheckResponse,
    SealMemoryRequest,
    UnlockResidencyRequest,
    UnsealMemoryRequest,
    VerifyResidencyRequest,
    VerifyWatermarkRequest,
)
from app.services.memory.zk_vault_watermark_service import (
    ZkVaultWatermarkService,
)

router = APIRouter(prefix="/zk-vault", tags=["memory-zk-vault"])
_service = ZkVaultWatermarkService()


def get_zk_vault_service() -> ZkVaultWatermarkService:
    """Dependency helper providing the active ZkVaultWatermarkService."""
    return _service


@router.post(
    "/seal",
    response_model=EncryptedEnvelopeDTO,
    status_code=status.HTTP_201_CREATED,
)
async def seal_memory(
    req: SealMemoryRequest,
) -> EncryptedEnvelopeDTO:
    """Seal a memory item with envelope encryption using user master passphrase."""
    return get_zk_vault_service().seal_memory(req)


@router.post(
    "/unseal",
    response_model=DistilledMemoryItemDTO,
)
async def unseal_memory(
    req: UnsealMemoryRequest,
) -> DistilledMemoryItemDTO:
    """Unseal an encrypted envelope using master passphrase."""
    try:
        return get_zk_vault_service().unseal_memory(req)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Decryption failed: {exc}",
        ) from exc


@router.get(
    "/memories",
    response_model=list[DistilledMemoryItemDTO],
)
async def list_memories(
    tier: MemorySensitivityTierDTO | None = Query(
        default=None, description="Optional sensitivity tier filter"
    ),
) -> list[DistilledMemoryItemDTO]:
    """List unsealed memory records optionally filtered by sensitivity tier."""
    return get_zk_vault_service().list_memories(tier=tier)


@router.post(
    "/export",
    response_model=DistilledExportPackageDTO,
)
async def export_distilled_package(
    req: ExportDistilledRequest,
) -> DistilledExportPackageDTO:
    """Export sanitized memories embedded with invisible zero-width provenance watermark."""
    return get_zk_vault_service().export_distilled(req)


@router.post(
    "/verify-watermark",
    response_model=ProvenanceWatermarkDTO,
)
async def verify_watermark(
    req: VerifyWatermarkRequest,
) -> ProvenanceWatermarkDTO:
    """Extract and verify invisible provenance watermark from potentially leaked text."""
    wm = get_zk_vault_service().verify_watermark(req)
    if wm is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No valid provenance watermark detected in provided text",
        )
    return wm


@router.post(
    "/verify-residency",
    response_model=ResidencyCheckResponse,
)
async def verify_residency(
    req: VerifyResidencyRequest,
) -> ResidencyCheckResponse:
    """Verify that current execution environment matches bound sandbox fingerprint."""
    return get_zk_vault_service().verify_residency(req)


@router.post(
    "/unlock-residency",
    response_model=dict[str, bool],
)
async def unlock_residency(
    req: UnlockResidencyRequest,
) -> dict[str, bool]:
    """Unlock hardware binding and rebind to new sandbox instance upon authorized migration."""
    success = get_zk_vault_service().unlock_residency(req)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid unlock passphrase provided",
        )
    return {"unlocked": True}
