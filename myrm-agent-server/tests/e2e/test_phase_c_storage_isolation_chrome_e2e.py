"""Phase C A/B storage isolation sentinel — negative probe for context-local state."""

from __future__ import annotations

import pytest

from tests.e2e.test_chrome_mcp_parallel_tabs_e2e import (
    test_isolated_browser_contexts_do_not_share_global_state,
)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_phase_c_storage_isolation_sentinel() -> None:
    """Phase C negative probe: isolated mux contexts must not share storage/cookies."""
    test_isolated_browser_contexts_do_not_share_global_state()
