//! Screen lock management IPC commands.
//!
//! Frontend and Server call these to detect screen lock state, temporarily
//! unlock for CU sessions, store/manage Keychain credentials, and query
//! Locked Use capability.

use std::sync::Mutex;
use tauri::State;

use crate::utils::screen_lock::{self, ScreenLockError, ScreenUnlockGuard};

/// Shared state holding the active unlock guard (if any).
pub struct ScreenLockState {
    guard: Mutex<Option<ScreenUnlockGuard>>,
}

impl ScreenLockState {
    pub fn new() -> Self {
        Self {
            guard: Mutex::new(None),
        }
    }
}

/// Check whether the screen is currently locked.
#[tauri::command]
pub fn screen_is_locked() -> bool {
    screen_lock::is_screen_locked()
}

/// Temporarily unlock the screen for a CU session.
/// Returns true if unlock succeeded, false if already unlocked.
#[tauri::command]
pub fn screen_unlock(
    state: State<'_, ScreenLockState>,
    reason: Option<String>,
) -> Result<bool, String> {
    let mut guard = state.guard.lock().map_err(|e| e.to_string())?;

    if guard.is_some() {
        return Ok(false); // Already unlocked by us
    }

    if !screen_lock::is_screen_locked() {
        return Ok(false); // Screen not locked
    }

    let reason_str = reason.as_deref().unwrap_or("CU session requires screen access");
    match ScreenUnlockGuard::unlock(reason_str) {
        Ok(g) => {
            *guard = Some(g);
            Ok(true)
        }
        Err(ScreenLockError::UnsupportedPlatform) => {
            Err("Screen unlock is not supported on this platform".into())
        }
        Err(ScreenLockError::NoPasswordConfigured) => {
            Err("No password configured. Please set your login password in Settings → Computer Use → Locked Use".into())
        }
        Err(e) => Err(e.to_string()),
    }
}

/// Re-lock the screen (releases the unlock guard).
#[tauri::command]
pub fn screen_relock(state: State<'_, ScreenLockState>) -> Result<bool, String> {
    let mut guard = state.guard.lock().map_err(|e| e.to_string())?;

    if guard.is_none() {
        return Ok(false); // No active unlock
    }

    *guard = None; // Drops the ScreenUnlockGuard → re-locks screen
    Ok(true)
}

/// Store the login password in the platform keychain.
#[tauri::command]
pub fn screen_lock_store_password(password: String) -> Result<(), String> {
    screen_lock::store_password(&password).map_err(|e| e.to_string())
}

/// Check whether a password is stored for screen unlock.
#[tauri::command]
pub fn screen_lock_has_password() -> bool {
    screen_lock::has_stored_password()
}

/// Delete the stored password from the keychain.
#[tauri::command]
pub fn screen_lock_delete_password() -> Result<(), String> {
    screen_lock::delete_password().map_err(|e| e.to_string())
}

/// Query platform capability for screen unlock.
#[tauri::command]
pub fn screen_lock_platform_support() -> serde_json::Value {
    serde_json::json!({
        "detection": true,
        "unlock": cfg!(target_os = "macos"),
        "keychain": cfg!(target_os = "macos"),
        "platform": std::env::consts::OS,
    })
}
