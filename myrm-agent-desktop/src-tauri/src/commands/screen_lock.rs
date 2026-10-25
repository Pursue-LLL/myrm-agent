//! Locked Use credential IPC commands.
//!
//! The settings page stores, checks and deletes the Keychain credential the
//! server uses to unlock the screen for Computer Use sessions, and queries the
//! platform capability. Lock detection and unlocking never cross this IPC
//! surface: the watcher probes the lock state in-process and the server types
//! the credential itself.
//!
//! [INPUT]
//! - utils::screen_credential (POS: login-password keychain access)
//!
//! [OUTPUT]
//! - screen_lock_store_password / screen_lock_has_password / screen_lock_delete_password: credential IPC
//! - screen_lock_platform_support: platform capability query for the settings page
//!   (includes runtime `curtain_capture_exclusion_ready`, e.g. Windows build ≥ 2004 for WDA)
//!
//! [POS]
//! Settings-page IPC surface of Locked Use; owns no lock logic of its own.

use crate::utils::screen_credential;

/// True when the desktop shell can exclude the privacy curtain from screen capture on this machine.
fn curtain_capture_exclusion_ready() -> bool {
    #[cfg(target_os = "macos")]
    {
        true
    }
    #[cfg(target_os = "windows")]
    {
        // WDA_EXCLUDEFROMCAPTURE requires Windows 10 version 2004 (build 19041) or later.
        const MIN_WDA_BUILD: u32 = 19_041;
        windows_build_number() >= MIN_WDA_BUILD
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        return false;
    }
}

#[cfg(target_os = "windows")]
fn windows_build_number() -> u32 {
    use std::mem::{size_of, zeroed};
    use windows_sys::Win32::System::SystemInformation::{RtlGetVersion, OSVERSIONINFOEXW};

    // RtlGetVersion reports the real build number on Windows 10+.
    unsafe {
        let mut info: OSVERSIONINFOEXW = zeroed();
        info.dwOSVersionInfoSize = size_of::<OSVERSIONINFOEXW>() as u32;
        if RtlGetVersion(&mut info as *mut OSVERSIONINFOEXW) != 0 {
            return 0;
        }
        info.dwBuildNumber
    }
}

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
        "curtain_supported": !cfg!(target_os = "linux"),
        "curtain_capture_excluded_on_desktop": cfg!(any(target_os = "macos", target_os = "windows")),
        "curtain_capture_exclusion_ready": curtain_capture_exclusion_ready(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn platform_support_reports_curtain_exclusion_ready() {
        let payload = screen_lock_platform_support();
        assert_eq!(
            payload
                .get("curtain_capture_excluded_on_desktop")
                .and_then(|v| v.as_bool()),
            Some(cfg!(any(target_os = "macos", target_os = "windows")))
        );
        assert!(payload.get("curtain_capture_exclusion_ready").is_some());
        #[cfg(target_os = "macos")]
        assert_eq!(
            payload
                .get("curtain_capture_exclusion_ready")
                .and_then(|v| v.as_bool()),
            Some(true),
        );
    }
}
