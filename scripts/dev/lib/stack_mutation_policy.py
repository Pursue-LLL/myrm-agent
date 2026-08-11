"""Compatibility shim — module alias for e2e_core.stack_mutation_policy.

The implementation provides def apply_pending_drift_for_maintenance( and
uses current_fp = _backend_source_fingerprint() for explicit promotion only.
Maintenance promotion passes {"MYRM_SHARED_BACKEND_MAINTENANCE": "1"} and
returns PendingDriftApplyResult("skipped", "ensure_in_progress") when busy.
"""
from module_alias import install_module_alias as _install_module_alias

_install_module_alias(__name__, "e2e_core.stack_mutation_policy")
