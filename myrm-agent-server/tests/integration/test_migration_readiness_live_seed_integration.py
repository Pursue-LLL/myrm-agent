"""Live-stack integration: migration readiness Chrome E2E seed endpoint (no ASGI mock)."""

from __future__ import annotations

import os
import time

import httpx
import pytest

from tests.support.verify_api_base import resolve_verify_api_base

_LIVE_SEED_POST_TIMEOUT_SEC = 60.0
_DB_BUSY_RETRY_ATTEMPTS = 5
_DB_BUSY_RETRY_DELAY_SEC = 2.0


def _live_api_reachable(api_base: str) -> bool:
    try:
        resp = httpx.get(f"{api_base}/api/v1/health", timeout=5.0)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def _post_seed_loopback(api_base: str, *, variant: str) -> dict[str, object]:
    url = f"{api_base.rstrip('/')}/api/v1/memory/test/seed-migration-readiness-fixture?variant={variant}"
    if not url.startswith("http://127.0.0.1:"):
        raise ValueError(f"Live integration only permits loopback API URLs: {url}")
    resp: httpx.Response | None = None
    for attempt in range(_DB_BUSY_RETRY_ATTEMPTS):
        resp = httpx.post(url, timeout=_LIVE_SEED_POST_TIMEOUT_SEC)
        if resp.status_code == 503:
            retry_after = resp.headers.get("Retry-After")
            delay = _DB_BUSY_RETRY_DELAY_SEC
            if retry_after is not None:
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    pass
            if attempt + 1 < _DB_BUSY_RETRY_ATTEMPTS:
                time.sleep(delay)
                continue
        break
    assert resp is not None
    if resp.status_code == 404:
        pytest.skip(
            "Live server missing seed route — stack pinned by wave; new pytest SHPOIB pool picks up latest code automatically"
        )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP POST {url} returned {resp.status_code}: {resp.text[:500]!r}")
    payload = resp.json()
    if not isinstance(payload, dict):
        raise AssertionError(f"Unexpected seed payload type: {type(payload)!r}")
    return payload


@pytest.mark.integration
class TestMigrationReadinessLiveSeedIntegration:
    """Hit epoch-matched verify-api backend — validates real DB seed path."""

    @pytest.mark.skipif(
        os.environ.get("MYRM_SKIP_LIVE_SERVER") == "1",
        reason="Live server checks disabled",
    )
    def test_live_migration_readiness_seed_mcp_warning(self) -> None:
        api_base = resolve_verify_api_base()
        if not _live_api_reachable(api_base):
            pytest.skip(f"Live API not reachable at {api_base}")

        seed = _post_seed_loopback(api_base, variant="mcp_warning")
        assert str(seed.get("readiness_status")) == "warning"
        assert str(seed.get("settings_path")) == "/settings/mcp"
        assert str(seed.get("import_batch_id", "")).startswith("memory-import-batch:")
        assert str(seed.get("target_agent_id", "")).strip()
        assert str(seed.get("chat_ui_path", "")).startswith("/?agentId=")

    @pytest.mark.skipif(
        os.environ.get("MYRM_SKIP_LIVE_SERVER") == "1",
        reason="Live server checks disabled",
    )
    def test_live_migration_readiness_seed_provider_critical(self) -> None:
        api_base = resolve_verify_api_base()
        if not _live_api_reachable(api_base):
            pytest.skip(f"Live API not reachable at {api_base}")

        seed = _post_seed_loopback(api_base, variant="provider_critical")
        assert str(seed.get("readiness_status")) == "critical"
        assert str(seed.get("settings_path")) == "/settings/models"

    def test_live_migration_readiness_seed_diagnostic_critical(self) -> None:
        api_base = resolve_verify_api_base()
        if not _live_api_reachable(api_base):
            pytest.skip(f"Live API not reachable at {api_base}")

        seed = _post_seed_loopback(api_base, variant="diagnostic_critical")
        assert str(seed.get("readiness_status")) == "critical"
        assert str(seed.get("settings_path")) == "/settings/memory"
