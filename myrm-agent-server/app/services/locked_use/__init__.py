"""Locked Use service — coordinates Computer Use with screen lock management.

[INPUT]
- macOS Keychain (unlock credential, written by the Tauri desktop shell)
- harness screen detector (native in-process lock-state probe)
- SleepInhibitor (display keep-awake during CU sessions)
- curtain_state.json file bridge (MYRM_CURTAIN_STATE_FILE; Tauri privacy curtain)

[OUTPUT]
- MacScreenUnlocker: lock probe / serialized unlock / verified re-lock primitives
- release_unlock_lease: hands the lease back only once the screen is confirmed locked
- locked_use_session: async context manager that acquires and releases the CU lease
- curtain_bridge: bridge state read + lease-bit write + capture-exclusion titles
- unattended: curtain watcher (lease acquisition after the quiet period)

[POS]
Business coordination layer between Computer Use and screen lock management,
including unattended curtain orchestration (lease → excluded screenshot channel →
verified re-lock). Only activates in local/Tauri deployment mode, where a
physical screen exists.
"""
