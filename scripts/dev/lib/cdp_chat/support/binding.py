"""Runtime binding of the chat page to the backend under test.

[INPUT]
- cdp_chat.support.api_client::_LOOPBACK_HOSTS, get_e2e_api_url, get_e2e_ui_url, resolve_e2e_api_base (POS: Where the E2E API and UI live and the loopback-only HTTP calls to them, retried under parallel load)
- cdp_chat.support.timeouts::e2e_attach_timeout_ms (POS: Turns a base timeout into the budget a parallel run needs, from the active wave leases, parallel tests and mux peers)

[OUTPUT]
- e2e_runtime_binding: the validated page-local binding of a private backend
- e2e_runtime_binding_source, e2e_page_binding_source, e2e_runtime_bootstrap_apply_js, e2e_api_base_persist_source, e2e_api_base_inject_js: page scripts that bind a document to its backend
- E2E_API_BINDING_PROBE_JS, require_e2e_api_binding_probe: read the binding back and fail closed on a mismatch

[POS]
Binds the chat page to the backend under test: the scripts that put the runtime identity and API base into the page, and the check that the page reports the expected one.
"""

from __future__ import annotations

import json
import os
import re
from urllib.parse import urlsplit

from cdp_chat.support.api_client import (
    _LOOPBACK_HOSTS,
    get_e2e_api_url,
    get_e2e_ui_url,
    resolve_e2e_api_base,
)
from cdp_chat.support.timeouts import e2e_attach_timeout_ms

_E2E_RUNTIME_BINDING_PREFIX = "myrm-e2e-v1:"
_E2E_RUNTIME_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


def e2e_runtime_binding(api_base: str | None = None) -> dict[str, object] | None:
    """Return a validated page-local private Backend binding."""
    base = resolve_e2e_api_base(api_base)
    runtime_id = os.getenv("MYRM_E2E_PRIVATE_RUNTIME_ID", "").strip()
    run_id = os.getenv("MYRM_E2E_RUN_ID", "").strip()
    ui_base = get_e2e_ui_url()
    if not base or not runtime_id or not run_id:
        return None
    if not _E2E_RUNTIME_ID_RE.fullmatch(runtime_id) or not _E2E_RUNTIME_ID_RE.fullmatch(
        run_id
    ):
        raise RuntimeError("E2E runtime/run identity contains unsupported characters")
    api = urlsplit(base)
    ui = urlsplit(ui_base)
    loopback_hosts = _LOOPBACK_HOSTS
    if (
        api.scheme not in {"http", "https"}
        or ui.scheme not in {"http", "https"}
        or api.hostname not in loopback_hosts
        or ui.hostname not in loopback_hosts
        or not api.port
        or not ui.port
    ):
        raise RuntimeError(
            "E2E runtime binding only permits explicit loopback HTTP origins"
        )
    return {
        "version": 1,
        "runId": run_id,
        "runtimeId": runtime_id,
        "apiBase": f"{api.scheme}://{api.hostname}:{api.port}",
        "uiOrigin": f"{ui.scheme}://{ui.hostname}:{ui.port}",
    }


def e2e_runtime_binding_source(api_base: str | None = None) -> str | None:
    binding = e2e_runtime_binding(api_base)
    if binding is None:
        return None
    name = _E2E_RUNTIME_BINDING_PREFIX + json.dumps(binding, separators=(",", ":"))
    attach_ms = e2e_attach_timeout_ms()
    return (
        f"window.name = {json.dumps(name)};"
        f"window.__MYRM_E2E_RUNTIME__ = Object.freeze({json.dumps(binding)});"
        f"window.__MYRM_E2E_API_BASE__ = {json.dumps(binding['apiBase'])};"
        f"window.__MYRM_E2E_ATTACH_TIMEOUT_MS__ = {attach_ms};"
    )


def e2e_page_binding_source(api_base: str | None = None) -> str | None:
    """Page window.name runtime binding — disabled on isolated stacks (Next proxy SSOT)."""
    if os.environ.get("MYRM_E2E_ISOLATED", "").strip() == "1":
        return None
    return e2e_runtime_binding_source(api_base)


def e2e_runtime_bootstrap_apply_js(api_base: str | None = None) -> str | None:
    """Apply binding + health-ready promise after navigation (MCP mux path)."""
    if os.environ.get("MYRM_E2E_ISOLATED", "").strip() == "1":
        return None
    binding = e2e_runtime_binding(api_base)
    if binding is None:
        return None
    binding_json = json.dumps(binding)
    prefix = json.dumps(_E2E_RUNTIME_BINDING_PREFIX)
    attach_ms = e2e_attach_timeout_ms()
    return f"""(async () => {{
  const binding = Object.freeze({binding_json});
  const prefix = {prefix};
  window.name = prefix + JSON.stringify(binding);
  window.__MYRM_E2E_RUNTIME__ = binding;
  window.__MYRM_E2E_API_BASE__ = binding.apiBase;
  window.__MYRM_E2E_ATTACH_TIMEOUT_MS__ = {attach_ms};
  const nativeFetch = window.fetch.bind(window);
  const healthUrl = `${{binding.apiBase}}/api/v1/health`;
  window.__MYRM_E2E_RUNTIME_READY__ = nativeFetch(healthUrl, {{ cache: 'no-store' }})
    .then(async (response) => {{
      if (!response.ok) {{
        throw new Error(`E2E_RUNTIME_HEALTH_HTTP_${{response.status}}`);
      }}
      const payload = await response.json();
      if (payload.runtime_id !== binding.runtimeId) {{
        throw new Error(
          `E2E_RUNTIME_MISMATCH expected=${{binding.runtimeId}} actual=${{payload.runtime_id || '<missing>'}}`,
        );
      }}
      window.dispatchEvent(new CustomEvent('myrm_e2e_runtime_ready', {{ detail: binding }}));
      return binding;
    }});
  try {{
    const value = await window.__MYRM_E2E_RUNTIME_READY__;
    return {{ ok: true, runtimeId: value.runtimeId, apiBase: value.apiBase }};
  }} catch (error) {{
    return {{ ok: false, error: String(error) }};
  }}
}})()"""


def e2e_api_base_persist_source(api_base: str | None = None) -> str | None:
    """JS source for Page.addScriptToEvaluateOnNewDocument (survives hard navigation)."""
    runtime_source = e2e_runtime_binding_source(api_base)
    if runtime_source is not None:
        return runtime_source
    base = resolve_e2e_api_base(api_base)
    if not base:
        return None
    encoded = json.dumps(base)
    return f"window.__MYRM_E2E_API_BASE__ = {encoded};"


def e2e_api_base_inject_js(api_base: str | None = None) -> str:
    runtime_source = e2e_runtime_binding_source(api_base)
    if runtime_source is not None:
        binding = e2e_runtime_binding(api_base)
        assert binding is not None
        return f"(() => {{{runtime_source} return {{ ok: true, base: {json.dumps(binding['apiBase'])}, runtimeId: {json.dumps(binding['runtimeId'])} }}; }})()"
    base = resolve_e2e_api_base(api_base) or get_e2e_api_url()
    encoded = json.dumps(base)
    return f"""(() => {{
  window.__MYRM_E2E_API_BASE__ = {encoded};
  return {{ ok: true, base: {encoded} }};
}})()"""


E2E_API_BINDING_PROBE_JS = """
(() => ({
  apiBase: window.__MYRM_E2E_API_BASE__ ?? null,
  runtimeId: window.__MYRM_E2E_RUNTIME__?.runtimeId ?? null,
}))()
""".strip()


def require_e2e_api_binding_probe(
    probe: object,
    expected_api_base: str,
) -> dict[str, object]:
    """Fail closed when WebUI document is not bound to the expected SHPOIB private API."""
    if not isinstance(probe, dict):
        raise TypeError(f"E2E API binding probe invalid: {probe!r}")
    expected = expected_api_base.rstrip("/")
    actual = str(probe.get("apiBase") or "").rstrip("/")
    if actual != expected:
        raise AssertionError(
            f"E2E API binding mismatch: expected {expected!r}, got {actual!r}; "
            f"probe={probe!r}"
        )
    return probe
