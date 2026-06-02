"""Locked Use service — coordinates Computer Use with screen lock management.

[INPUT]
- Tauri IPC (screen_is_locked, screen_unlock, screen_relock via HTTP proxy)
- SleepInhibitor (prevent display sleep during CU sessions)

[OUTPUT]
- LockedUseService: async context manager for CU sessions requiring screen access

[POS]
Business coordination layer between Computer Use and screen lock management.
Only activates in local/Tauri deployment mode (desktop has a physical screen).
"""
