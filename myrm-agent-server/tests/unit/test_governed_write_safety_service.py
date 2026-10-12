"""
[POS] tests/unit/test_governed_write_safety_service.py
[INPUT] app.schemas.governed_write_safety, app.services.security.governed_write_safety_service
[OUTPUT] Unit tests for GovernedWriteSafetyService
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest

from app.schemas.governed_write_safety import (
    ApproveEditRequestDTO,
    CommitEditRequestDTO,
    ProposeEditRequestDTO,
    RegisterOpaqueFileRequestDTO,
)
from app.services.security.governed_write_safety_service import (
    GovernedWriteSafetyService,
)


@pytest.fixture
def service() -> GovernedWriteSafetyService:
    return GovernedWriteSafetyService()


def test_register_and_resolve_opaque_file(service: GovernedWriteSafetyService) -> None:
    reg_req = RegisterOpaqueFileRequestDTO(raw_path="/workspace/src/app.py")
    reg_res = service.register_opaque_file(reg_req)

    assert reg_res.opaque_file_id.startswith("@file_")
    assert reg_res.raw_path == "/workspace/src/app.py"

    resolved = service.resolve_path(reg_res.opaque_file_id)
    assert resolved == "/workspace/src/app.py"


def test_propose_and_approve_edit(service: GovernedWriteSafetyService) -> None:
    reg_res = service.register_opaque_file(RegisterOpaqueFileRequestDTO(raw_path="/data/file.txt"))
    opaque_id = reg_res.opaque_file_id

    prop_req = ProposeEditRequestDTO(
        opaque_file_id=opaque_id,
        current_disk_content="initial content",
        candidate_content="updated content",
    )
    proposal = service.propose_edit(prop_req)

    assert proposal.proposal_id.startswith("prop-w-")
    assert proposal.opaque_file_id == opaque_id
    assert proposal.status == "proposed"
    assert proposal.lease_token is None

    # Approve proposal
    appr_res = service.approve_edit(ApproveEditRequestDTO(proposal_id=proposal.proposal_id))
    assert appr_res.proposal_id == proposal.proposal_id
    assert appr_res.lease_token.startswith("lease-tok-")

    # Fetch proposal details
    fetched = service.get_proposal(proposal.proposal_id)
    assert fetched is not None
    assert fetched.status == "approved"
    assert fetched.lease_token == appr_res.lease_token


def test_commit_edit_success(service: GovernedWriteSafetyService) -> None:
    reg_res = service.register_opaque_file(RegisterOpaqueFileRequestDTO(raw_path="/src/config.json"))
    opaque_id = reg_res.opaque_file_id

    base_content = '{"version": 1}'
    candidate_content = '{"version": 2}'

    proposal = service.propose_edit(
        ProposeEditRequestDTO(
            opaque_file_id=opaque_id,
            current_disk_content=base_content,
            candidate_content=candidate_content,
        )
    )
    appr = service.approve_edit(ApproveEditRequestDTO(proposal_id=proposal.proposal_id))

    commit_res = service.commit_edit(
        CommitEditRequestDTO(
            proposal_id=proposal.proposal_id,
            lease_token=appr.lease_token,
            current_disk_content=base_content,
        )
    )

    assert commit_res.success is True
    assert commit_res.status == "committed"
    assert commit_res.pre_image_snapshot_id is not None
    assert commit_res.verified_disk_hash is not None

    # Check pre-image snapshot
    snapshot = service.get_snapshot(commit_res.pre_image_snapshot_id)
    assert snapshot is not None
    assert snapshot.content_preview == base_content


def test_commit_edit_stale_rejection(service: GovernedWriteSafetyService) -> None:
    reg_res = service.register_opaque_file(RegisterOpaqueFileRequestDTO(raw_path="/src/main.rs"))
    opaque_id = reg_res.opaque_file_id

    original_base = "fn main() { println!(\"v1\"); }"
    candidate = "fn main() { println!(\"v2\"); }"

    proposal = service.propose_edit(
        ProposeEditRequestDTO(
            opaque_file_id=opaque_id,
            current_disk_content=original_base,
            candidate_content=candidate,
        )
    )
    appr = service.approve_edit(ApproveEditRequestDTO(proposal_id=proposal.proposal_id))

    # Concurrently modified on disk
    tampered_content = "fn main() { println!(\"concurrent external change\"); }"

    commit_res = service.commit_edit(
        CommitEditRequestDTO(
            proposal_id=proposal.proposal_id,
            lease_token=appr.lease_token,
            current_disk_content=tampered_content,
        )
    )

    assert commit_res.success is False
    assert commit_res.status == "stale_rejected"
    assert commit_res.conflict_bundle is not None
    assert commit_res.conflict_bundle.opaque_file_id == opaque_id
    assert commit_res.conflict_bundle.expected_base_hash != commit_res.conflict_bundle.actual_disk_hash
