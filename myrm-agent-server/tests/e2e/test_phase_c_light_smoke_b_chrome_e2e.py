"""Phase C light smoke variant B — home shell (8-lane pool filler)."""

from __future__ import annotations

import pytest

from tests.e2e.test_phase_c_shared_read_smoke_chrome_e2e import (
    test_phase_c_shared_read_home_shell_smoke,
)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_phase_c_light_smoke_variant_b() -> None:
    test_phase_c_shared_read_home_shell_smoke()
