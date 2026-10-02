"""Locked Use service — coordinates Computer Use with screen lock management.

[INPUT]
- Tauri IPC (screen_is_locked, screen_unlock, screen_relock via HTTP proxy)
- SleepInhibitor (prevent display sleep during CU sessions)
- curtain_state.json file bridge (MYRM_CURTAIN_STATE_FILE; Tauri privacy curtain)

[OUTPUT]
- LockedUseService: async context manager for CU sessions requiring screen access
- curtain_bridge: curtain state read + pending flag write + capture-exclusion titles
- unattended: curtain watcher (auto unlock after quiet period when CU session active)

[POS]
Business coordination layer between Computer Use and screen lock management,
including unattended curtain orchestration (auto unlock → excluded screenshot
channel → relock on user return). Only activates in local/Tauri deployment mode
(desktop has a physical screen).
"""
