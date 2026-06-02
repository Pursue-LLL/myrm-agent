from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.memory.operations.shared_contexts import approve_shared_context_write_proposal
from app.core.utils.errors import MyrmError
from app.database.standard_responses import BusinessCode
from app.services.memory.shared_context_materializer import SharedContextProposalMaterializer


class AuthenticationError(Exception):
    """LiteLLM-compatible exception name used by the shared error classifier."""


@pytest.mark.asyncio
async def test_approve_shared_context_proposal_maps_embedding_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_approval(self: SharedContextProposalMaterializer, proposal_id: str) -> None:
        _ = (self, proposal_id)
        raise AuthenticationError("Incorrect API key provided: default")

    monkeypatch.setattr(SharedContextProposalMaterializer, "approve_write_proposal", fail_approval)

    with pytest.raises(MyrmError) as exc_info:
        await approve_shared_context_write_proposal("proposal-1", cast(AsyncSession, object()))

    assert exc_info.value.code == BusinessCode.AI_AUTH_ERROR
    assert exc_info.value.status_code == 401
    assert "Shared Context proposal materialization failed" in exc_info.value.message
    assert "authentication_failed" in exc_info.value.message
