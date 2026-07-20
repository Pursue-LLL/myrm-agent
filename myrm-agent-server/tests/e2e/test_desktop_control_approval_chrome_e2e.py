"""Chrome E2E: desktop control approval via real WebUI SSE + Inspector banner.

Flow:
  enable computer_use → send agent message → desktop_interact triggers approval
  → click Allow once / Allow always → tool resumes → assistant replies DONE.

Prerequisites:
  ./myrm ready --chrome  (macOS, Accessibility granted, provider ready)

Implementation modules: tests/e2e/desktop_approval/
"""

from __future__ import annotations

import platform

import pytest

from tests.e2e.desktop_approval.runner import run_desktop_approval_chrome_e2e
from tests.support.e2e_runtime_guard import E2EResourceLedger


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=False)
@pytest.mark.chrome_e2e_desktop
@pytest.mark.integration
@pytest.mark.timeout(1800)
@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS computer_use only")
@pytest.mark.asyncio
async def test_chrome_ui_desktop_control_approval_allow_once(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    await run_desktop_approval_chrome_e2e(
        scope="once",
        label="allow-once",
        e2e_resource_ledger=e2e_resource_ledger,
    )


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=False)
@pytest.mark.chrome_e2e_desktop
@pytest.mark.integration
@pytest.mark.timeout(2400)
@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS computer_use only")
@pytest.mark.asyncio
async def test_chrome_ui_desktop_control_approval_allow_always_settings_revoke(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    await run_desktop_approval_chrome_e2e(
        scope="always",
        label="allow-always-settings-revoke",
        e2e_resource_ledger=e2e_resource_ledger,
    )
