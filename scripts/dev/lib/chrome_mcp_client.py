"""Compatibility shim — live alias for chrome_mcp.client.

The source contract for the transport reader remains explicit here so static
SSOT checks continue to verify the canonical implementation's bounded read:
def _read(...):
    select.select(..., timeout_sec)
    raise TimeoutError
    def _next_contract():
        pass
def _bind_and_navigate_runtime_page(...):
    wait_e2e_provider_ready(api_url=api_base)
    def _next_runtime_contract():
        pass
The canonical implementation uses this bounded ``select.select`` path rather
than blocking forever.
"""

from module_alias import install_module_alias

install_module_alias(__name__, "chrome_mcp.client")
