"""Bind the active page to the isolated private API and wait until that API is healthy."""

from __future__ import annotations

import json

from cdp_chat.support import (
    E2E_API_BINDING_PROBE_JS,
    e2e_api_base_inject_js,
    e2e_runtime_binding_source,
    e2e_runtime_bootstrap_apply_js,
    get_e2e_api_url,
    require_e2e_api_binding_probe,
)
from chrome_mcp.client import ChromeMcpClient, McpPage
from e2e_core.dev_ports import shared_api_base

from .reload import _wait_for_shpoib_runtime_ready
from .wait_state import wait_for_state


def _ensure_e2e_private_api_live(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    timeout_sec: float,
) -> None:
    """Ensure SHPOIB private API binding is applied and health-ready on the active page."""
    api_base = get_e2e_api_url().rstrip("/")
    shared_api = shared_api_base()
    if api_base == shared_api:
        return

    bootstrap_js = e2e_runtime_bootstrap_apply_js()
    binding_source = e2e_runtime_binding_source()
    if bootstrap_js is not None:
        if binding_source is not None:
            client.evaluate(
                page,
                f"(() => {{{binding_source} return true; }})()",
                timeout_sec=min(15.0, timeout_sec),
            )
        observed = client.evaluate(
            page,
            bootstrap_js,
            timeout_sec=min(60.0, timeout_sec),
        )
        if isinstance(observed, dict) and observed.get("ok") is True:
            _wait_for_shpoib_runtime_ready(
                client,
                page,
                timeout_sec=min(60.0, timeout_sec),
            )
            return

    client.evaluate(
        page,
        e2e_api_base_inject_js(api_base),
        timeout_sec=min(15.0, timeout_sec),
    )

    probe_raw = client.evaluate(
        page,
        E2E_API_BINDING_PROBE_JS,
        timeout_sec=10.0,
    )
    require_e2e_api_binding_probe(probe_raw, api_base)
    health_js = f"""(async () => {{
      const base = {json.dumps(api_base)};
      try {{
        const response = await fetch(`${{base}}/api/v1/health`, {{ cache: 'no-store' }});
        return {{ ready: response.ok }};
      }} catch (error) {{
        return {{ ready: false, error: String(error) }};
      }}
    }})()"""
    wait_for_state(
        client,
        page,
        health_js,
        timeout_sec=min(45.0, timeout_sec),
    )
