"""Ingress requirement snapshot cache invalidation."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.infra.ingress_requirement import (
    IngressRequirementSnapshot,
    invalidate_ingress_requirement_cache,
    resolve_ingress_requirement,
)


@pytest.mark.asyncio
async def test_resolve_recomputes_after_invalidate():
    first = IngressRequirementSnapshot(required=True, has_public_ingress=False, reasons=("channel:line",))
    second = IngressRequirementSnapshot(required=False, has_public_ingress=True)

    with patch(
        "app.core.infra.ingress_requirement._evaluate_ingress_requirement",
        new_callable=AsyncMock,
    ) as mock_eval:
        mock_eval.side_effect = [first, second]

        cached = await resolve_ingress_requirement()
        assert cached.required is True

        still_cached = await resolve_ingress_requirement()
        assert still_cached.required is True
        assert mock_eval.await_count == 1

        invalidate_ingress_requirement_cache()
        refreshed = await resolve_ingress_requirement()
        assert refreshed.required is False
        assert mock_eval.await_count == 2
