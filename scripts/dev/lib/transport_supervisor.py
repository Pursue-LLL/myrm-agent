"""Compatibility shim — module alias for mux.transport_supervisor.

The implementation uses fcntl.flock for cross-process recovery admission.
Its default lock is the per-host mux-recovery.lock state file.
The live symbol is _CROSS_PROCESS_RECOVERY_LOCK_PATH.
"""
from module_alias import install_module_alias as _install_module_alias

_install_module_alias(__name__, "mux.transport_supervisor")
