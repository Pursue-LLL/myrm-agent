"""Phase C light smoke variant J — home shell (16-lane pool; SHPOIB path)."""

from __future__ import annotations

import pytest

from tests.e2e.test_phase_c_shared_read_smoke_chrome_e2e import (
    test_phase_c_shared_read_home_shell_smoke,
)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_phase_c_light_smoke_variant_j() -> None:
    test_phase_c_shared_read_home_shell_smoke()
