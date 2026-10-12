"""Unit tests for DataErasurePortabilityService."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas.data_erasure_portability import (
    ExecuteErasureRequest,
    ExportPortabilityBundleRequest,
    RegisterTenantKeyRequest,
    ShredPathRequest,
    VerifyBundleRequest,
    VerifyCertificateRequest,
)
from app.services.security.data_erasure_portability_service import (
    DataErasurePortabilityService,
    get_data_erasure_portability_service,
)


@pytest.fixture
def service() -> DataErasurePortabilityService:
    return DataErasurePortabilityService()


def test_singleton_getter() -> None:
    svc1 = get_data_erasure_portability_service()
    svc2 = get_data_erasure_portability_service()
    assert svc1 is svc2


def test_register_tenant_key(service: DataErasurePortabilityService) -> None:
    req = RegisterTenantKeyRequest(tenant_id="tenant-alpha")
    res = service.register_tenant_key(req)
    assert res.tenant_id == "tenant-alpha"
    assert len(res.key_fingerprint) == 64
    assert res.status == "ACTIVE"


def test_execute_erasure_with_file_shredding(
    service: DataErasurePortabilityService,
    tmp_path: Path,
) -> None:
    # Setup temporary file
    temp_file = tmp_path / "sqlite_memory.db"
    temp_file.write_bytes(b"SENSITIVE_VECTOR_DATA_PAYLOAD" * 50)
    assert temp_file.exists()

    # Register key first
    service.register_tenant_key(RegisterTenantKeyRequest(tenant_id="tenant-purge"))

    # Execute erasure
    req = ExecuteErasureRequest(
        tenant_id="tenant-purge",
        target_resource_types=["VECTORS", "MEMORY"],
        physical_path_to_shred=str(temp_file),
    )
    res = service.execute_erasure(req)

    assert res.success is True
    assert res.erasure_method == "CRYPTOGRAPHIC"
    assert res.certificate is not None
    assert res.shredded_files_count == 1
    assert res.shredded_bytes_count > 0
    assert not temp_file.exists()

    # Verify generated certificate
    verify_req = VerifyCertificateRequest(certificate=res.certificate)
    v_res = service.verify_certificate(verify_req)
    assert v_res.is_valid is True


def test_export_and_verify_portability_bundle(service: DataErasurePortabilityService) -> None:
    req = ExportPortabilityBundleRequest(
        tenant_id="tenant-gdpr-user",
        conversations=[{"role": "user", "content": "analyze code"}],
        memory_entries=[{"concept": "fastapi", "summary": "modern web framework"}],
        agent_configs=[{"name": "lead-architect", "temperature": "0.2"}],
    )
    bundle = service.export_bundle(req)

    assert bundle.tenant_id == "tenant-gdpr-user"
    assert len(bundle.bundle_sha256) == 64
    assert len(bundle.bundle_signature) == 64

    # Verify authentic bundle
    verify_res = service.verify_bundle(VerifyBundleRequest(bundle=bundle))
    assert verify_res.is_valid is True


def test_shred_path_file_and_directory(
    service: DataErasurePortabilityService,
    tmp_path: Path,
) -> None:
    # 1. Shred file
    target_f = tmp_path / "confidential.txt"
    target_f.write_text("classified data")
    f_res = service.shred_path(ShredPathRequest(path=str(target_f), passes=3))
    assert f_res.success is True
    assert f_res.files_shredded == 1
    assert not target_f.exists()

    # 2. Shred directory
    target_d = tmp_path / "sandbox_dir"
    target_d.mkdir()
    (target_d / "file1.log").write_text("log data")
    (target_d / "file2.log").write_text("more log data")

    d_res = service.shred_path(ShredPathRequest(path=str(target_d), passes=2))
    assert d_res.success is True
    assert d_res.files_shredded == 2
    assert not target_d.exists()
