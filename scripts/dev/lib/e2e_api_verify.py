"""Compatibility shim — module alias for e2e_core.api_verify.

The implementation owns browser_isolation_payload, browserIsolation and
CHROME_INSTANCE_ISOLATION.  Keep those contracts in the implementation so
tests and runtime callers patch one module object instead of a stale copy.
Peer cleanup remains coordinator-owned: let Coordinator reap automatically.
The canonical context output includes E2E_BLOCKED_EPOCH: when the workspace
epoch has no matching backend.
When blocked, the agent rule is: do not wait, restart shared :8080, or stop peers.
The implementation also exposes host_resource_governor_snapshot,
hostGovernor, parallelSnapshot and E2E_HOST_GOVERNOR= in context output.
"""
import sys as _sys

from module_alias import install_module_alias as _install_module_alias

_install_module_alias(__name__, "e2e_core.api_verify")

if __name__ == "__main__":
    raise SystemExit(_sys.modules[__name__].main())
