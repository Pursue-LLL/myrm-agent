"""SSRF guard for the provider-returned image URLs the engine downloads."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError
from myrm_agent_harness.toolkits.llms.image.models import _download_url


@pytest.mark.asyncio
async def test_download_url_blocks_ssrf() -> None:
    with patch(
        "myrm_agent_harness.core.security.http.secure_fetch.secure_get",
        new_callable=AsyncMock,
        side_effect=SSRFSecurityError("private IP"),
    ):
        result = await _download_url("http://169.254.169.254/")

    assert result is None
