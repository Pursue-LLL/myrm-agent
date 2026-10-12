"""
[POS] tests/unit/test_hardened_sandbox_perimeter_service.py
[INPUT] app.schemas.hardened_sandbox_perimeter, app.services.security.hardened_sandbox_perimeter_service
[OUTPUT] unit tests

Unit tests for HardenedSandboxPerimeterService.
Strict typing applied: No `Any` types allowed.
"""

from app.schemas.hardened_sandbox_perimeter import (
    CredentialTicketMintRequest,
    CredentialTicketVerifyRequest,
    EgressEvaluateRequest,
    EgressVerdictEnum,
    HardenedSandboxSpecRequest,
    ProcessUsageEvaluateRequest,
    RuntimeSpecValidationVerdictEnum,
    SandboxIsolationModeEnum,
)
from app.services.security.hardened_sandbox_perimeter_service import (
    HardenedSandboxPerimeterService,
)


def test_service_validate_runtime_spec() -> None:
    service = HardenedSandboxPerimeterService()

    # 1. Valid hardened container specification
    valid_req = HardenedSandboxSpecRequest(
        isolation_mode=SandboxIsolationModeEnum.CONTAINER,
        is_non_root=True,
        uid=1001,
        gid=1001,
        read_only_rootfs=True,
        tmpfs_noexec=True,
        persistent_volume_path="/persistent/data",
        memory_limit_mb=1024,
        cpu_quota_pct=2.0,
        pids_max=256,
    )
    res_valid = service.validate_runtime_spec(valid_req)
    assert res_valid.is_valid is True
    assert res_valid.verdict == RuntimeSpecValidationVerdictEnum.VALID
    assert len(res_valid.violations) == 0

    # 2. Insecure root execution
    bad_root_req = HardenedSandboxSpecRequest(
        is_non_root=False,
        uid=0,
    )
    res_root = service.validate_runtime_spec(bad_root_req)
    assert res_root.is_valid is False
    assert res_root.verdict == RuntimeSpecValidationVerdictEnum.INVALID_ROOT_USER
    assert len(res_root.violations) >= 1

    # 3. Writable root filesystem
    bad_rootfs_req = HardenedSandboxSpecRequest(read_only_rootfs=False)
    res_rootfs = service.validate_runtime_spec(bad_rootfs_req)
    assert res_rootfs.is_valid is False
    assert res_rootfs.verdict == RuntimeSpecValidationVerdictEnum.INVALID_WRITABLE_ROOTFS


def test_service_evaluate_egress_and_ssrf() -> None:
    service = HardenedSandboxPerimeterService()

    # 1. Block direct cloud metadata access
    meta_req = EgressEvaluateRequest(host="169.254.169.254", port=80)
    meta_res = service.evaluate_egress(meta_req)
    assert meta_res.is_allowed is False
    assert meta_res.verdict == EgressVerdictEnum.BLOCKED_CLOUD_METADATA

    # 2. Block private internal IP (RFC 1918)
    priv_req = EgressEvaluateRequest(host="192.168.1.100", port=443)
    priv_res = service.evaluate_egress(priv_req)
    assert priv_res.is_allowed is False
    assert priv_res.verdict == EgressVerdictEnum.BLOCKED_PRIVATE_IP

    # 3. Block loopback
    loop_req = EgressEvaluateRequest(host="127.0.0.1", port=8000)
    loop_res = service.evaluate_egress(loop_req)
    assert loop_res.is_allowed is False
    assert loop_res.verdict == EgressVerdictEnum.BLOCKED_PRIVATE_IP


def test_service_credential_ticket_lifecycle() -> None:
    service = HardenedSandboxPerimeterService()

    # 1. Register host master secret
    service.register_master_secret("openai_api_key", "sk-proj-live-token-secret")

    # 2. Mint ephemeral capability ticket
    mint_req = CredentialTicketMintRequest(
        secret_alias="openai_api_key",
        allowed_scopes=["llm:completion", "llm:stream"],
        ttl_seconds=180.0,
    )
    mint_res = service.mint_credential_ticket(mint_req)
    assert mint_res.ticket_id.startswith("tkt-")
    assert mint_res.ephemeral_token.startswith("ept-")
    assert "llm:completion" in mint_res.allowed_scopes

    # 3. Verify valid ticket with correct scope
    verify_req_good = CredentialTicketVerifyRequest(
        ticket_id=mint_res.ticket_id,
        required_scope="llm:completion",
    )
    verify_res_good = service.verify_credential_ticket(verify_req_good)
    assert verify_res_good.is_valid is True

    # 4. Verify valid ticket with unauthorized scope
    verify_req_bad = CredentialTicketVerifyRequest(
        ticket_id=mint_res.ticket_id,
        required_scope="system:root_admin",
    )
    verify_res_bad = service.verify_credential_ticket(verify_req_bad)
    assert verify_res_bad.is_valid is False


def test_service_process_guard_and_circuit_breaker() -> None:
    service = HardenedSandboxPerimeterService()
    agent_id = "agent-proc-test-01"

    # 1. Safe process usage
    safe_req = ProcessUsageEvaluateRequest(
        agent_id=agent_id,
        active_pids_count=10,
        memory_used_mb=128.0,
        cpu_percent=12.0,
        pids_max=64,
        memory_limit_mb=512.0,
    )
    safe_res = service.evaluate_process_usage(safe_req)
    assert safe_res.is_safe is True
    assert safe_res.is_circuit_broken is False

    # 2. Fork-bomb outbreak
    forkbomb_req = ProcessUsageEvaluateRequest(
        agent_id=agent_id,
        active_pids_count=120,
        memory_used_mb=256.0,
        cpu_percent=95.0,
        pids_max=64,
        memory_limit_mb=512.0,
    )
    forkbomb_res = service.evaluate_process_usage(forkbomb_req)
    assert forkbomb_res.is_safe is False
    assert forkbomb_res.is_circuit_broken is True
    assert "Fork bomb detected" in forkbomb_res.message

    # 4. Telemetry metrics inspection
    metrics = service.get_metrics()
    assert metrics.fork_bomb_mitigations == 1


def test_service_comprehensive_metrics() -> None:
    service = HardenedSandboxPerimeterService()
    service.validate_runtime_spec(HardenedSandboxSpecRequest(is_non_root=False, uid=0))
    service.evaluate_egress(EgressEvaluateRequest(host="169.254.169.254"))
    service.register_master_secret("sec", "val")
    service.mint_credential_ticket(CredentialTicketMintRequest(secret_alias="sec", allowed_scopes=["s"]))
    service.evaluate_process_usage(
        ProcessUsageEvaluateRequest(
            agent_id="ag-metrics",
            active_pids_count=500,
            memory_used_mb=100.0,
            pids_max=64,
        )
    )

    metrics = service.get_metrics()
    assert metrics.total_spec_validations == 1
    assert metrics.spec_validation_failures == 1
    assert metrics.egress_requests_evaluated == 1
    assert metrics.ssrf_blocks == 1
    assert metrics.credential_tickets_minted == 1
    assert metrics.fork_bomb_mitigations == 1

