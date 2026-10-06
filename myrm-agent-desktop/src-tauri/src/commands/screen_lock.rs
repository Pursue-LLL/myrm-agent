//! Locked Use credential IPC commands.
//!
//! The settings page stores, checks and deletes the Keychain credential the
//! server uses to unlock the screen for Computer Use sessions, and queries the
//! platform capability. Lock detection and unlocking never cross this IPC
//! surface: the watcher probes the lock state in-process and the server types
//! the credential itself.

use crate::utils::screen_credential;

/// Store the login password in the platform keychain.
#[tauri::command]
pub fn screen_lock_store_password(password: String) -> Result<(), String> {
    screen_credential::store_password(&password).map_err(|e| e.to_string())
}

/// Check whether a password is stored for screen unlock.
#[tauri::command]
pub fn screen_lock_has_password() -> bool {
    screen_credential::has_stored_password()
}

/// Delete the stored password from the keychain.
#[tauri::command]
pub fn screen_lock_delete_password() -> Result<(), String> {
    screen_credential::delete_password().map_err(|e| e.to_string())
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
