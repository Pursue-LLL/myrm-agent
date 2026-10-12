"""
[POS] app/api/security/keychain_rest_encryption_router.py
[INPUT] app.schemas.keychain_rest_encryption, app.services.security.keychain_rest_encryption_service
[OUTPUT] router

FastAPI router for Hardware-Rooted OS Keychain & Transparent Rest Encryption Suite.
Exposes endpoints for keychain status inspection, transparent encryption/decryption,
file sealing, cold-boot guards, and instant emergency purge.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.keychain_rest_encryption import (
    DecryptFileRequest,
    DecryptFileResponse,
    DecryptTextRequest,
    DecryptTextResponse,
    EncryptFileRequest,
    EncryptFileResponse,
    EncryptTextRequest,
    EncryptTextResponse,
    KeychainSelfTestResponse,
    KeychainStatusResponse,
    PurgeCredentialsRequest,
    PurgeCredentialsResponse,
    TransparentRestMetricsResponse,
)
from app.services.security.keychain_rest_encryption_service import (
    KeychainRestEncryptionService,
    get_keychain_rest_encryption_service,
)

router = APIRouter(
    prefix="/keychain-rest-encryption",
    tags=["OS Keychain & Transparent Rest Encryption"],
)


@router.get(
    "/status",
    response_model=KeychainStatusResponse,
    summary="Get OS keychain and transparent rest encryption status",
)
def get_keychain_status(
    service: KeychainRestEncryptionService = Depends(
        get_keychain_rest_encryption_service
    ),
) -> KeychainStatusResponse:
    """Query current OS keychain backend, hardware-backed status, and key fingerprints."""
    return service.get_status()


@router.post(
    "/encrypt",
    response_model=EncryptTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Encrypt text transparently with AES-256-GCM and HKDF domain separation",
)
def encrypt_text(
    request: EncryptTextRequest,
    service: KeychainRestEncryptionService = Depends(
        get_keychain_rest_encryption_service
    ),
) -> EncryptTextResponse:
    """Encrypt plaintext string into authenticated CipherEnvelope."""
    return service.encrypt_text(request)


@router.post(
    "/decrypt",
    response_model=DecryptTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Decrypt sealed CipherEnvelope back to plaintext string",
)
def decrypt_text(
    request: DecryptTextRequest,
    service: KeychainRestEncryptionService = Depends(
        get_keychain_rest_encryption_service
    ),
) -> DecryptTextResponse:
    """Verify authentication tag and decrypt CipherEnvelope."""
    try:
        return service.decrypt_text(request)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Decryption failed: {err}",
        ) from err


@router.post(
    "/encrypt-file",
    response_model=EncryptFileResponse,
    status_code=status.HTTP_200_OK,
    summary="Encrypt file on disk to sealed JSON envelope",
)
def encrypt_file(
    request: EncryptFileRequest,
    service: KeychainRestEncryptionService = Depends(
        get_keychain_rest_encryption_service
    ),
) -> EncryptFileResponse:
    """Read file, encrypt content with AES-256-GCM, and write envelope to destination."""
    try:
        return service.encrypt_file(request)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File encryption failed: {err}",
        ) from err


@router.post(
    "/decrypt-file",
    response_model=DecryptFileResponse,
    status_code=status.HTTP_200_OK,
    summary="Decrypt sealed envelope file on disk to original content",
)
def decrypt_file(
    request: DecryptFileRequest,
    service: KeychainRestEncryptionService = Depends(
        get_keychain_rest_encryption_service
    ),
) -> DecryptFileResponse:
    """Read sealed envelope file, decrypt, and write restored plaintext to destination."""
    try:
        return service.decrypt_file(request)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File decryption failed: {err}",
        ) from err


@router.post(
    "/purge",
    response_model=PurgeCredentialsResponse,
    status_code=status.HTTP_200_OK,
    summary="Instant emergency purge of in-memory keys and OS keychain credentials",
)
def purge_credentials(
    request: PurgeCredentialsRequest,
    service: KeychainRestEncryptionService = Depends(
        get_keychain_rest_encryption_service
    ),
) -> PurgeCredentialsResponse:
    """Execute instant cryptographic purge to prevent cold-boot extraction or unauthorized access."""
    return service.purge_credentials(request)


@router.post(
    "/self-test",
    response_model=KeychainSelfTestResponse,
    status_code=status.HTTP_200_OK,
    summary="Perform cryptographic roundtrip self-test",
)
def run_self_test(
    service: KeychainRestEncryptionService = Depends(
        get_keychain_rest_encryption_service
    ),
) -> KeychainSelfTestResponse:
    """Execute diagnostic roundtrip encryption and decryption."""
    return service.self_test()


@router.get(
    "/metrics",
    response_model=TransparentRestMetricsResponse,
    summary="Get cumulative cryptographic operations metrics",
)
def get_metrics(
    service: KeychainRestEncryptionService = Depends(
        get_keychain_rest_encryption_service
    ),
) -> TransparentRestMetricsResponse:
    """Inspect total encryptions, decryptions, purges, and failures."""
    return service.get_metrics()
