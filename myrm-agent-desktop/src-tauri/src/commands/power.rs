//! Power management IPC commands.
//!
//! Frontend calls these when agent tasks start/stop to prevent system sleep.

use std::sync::Mutex;
use tauri::State;

use crate::utils::power::{PowerError, PowerLock};

/// Shared state holding the current power lock (if any).
pub struct PowerState {
    lock: Mutex<Option<PowerLock>>,
}

impl PowerState {
    pub fn new() -> Self {
        Self {
            lock: Mutex::new(None),
        }
    }
}

/// Acquire power lock to prevent sleep during agent execution.
/// No-op if already held. Set `prevent_display_sleep` to true for CU sessions
/// that need the display to stay on for screenshots.
#[tauri::command]
pub fn power_lock_acquire(
    state: State<'_, PowerState>,
    reason: Option<String>,
    prevent_display_sleep: Option<bool>,
) -> Result<bool, String> {
    let mut guard = state.lock.lock().map_err(|e| e.to_string())?;

    if guard.is_some() {
        return Ok(false); // Already held
    }

    let reason_str = reason.as_deref().unwrap_or("Agent task in progress");
    let display = prevent_display_sleep.unwrap_or(false);
    match PowerLock::acquire(reason_str, display) {
        Ok(lock) => {
            *guard = Some(lock);
            Ok(true)
        }
        Err(PowerError::PlatformError(msg)) => Err(msg),
    }
}

/// Release power lock, allowing system to sleep again.
#[tauri::command]
pub fn power_lock_release(state: State<'_, PowerState>) -> Result<bool, String> {
    let mut guard = state.lock.lock().map_err(|e| e.to_string())?;

    if guard.is_none() {
        return Ok(false); // Not held
    }

    *guard = None; // Drops the PowerLock, releasing the assertion
    Ok(true)
}

/// Check if power lock is currently held.
#[tauri::command]
pub fn power_lock_status(state: State<'_, PowerState>) -> Result<bool, String> {
    let guard = state.lock.lock().map_err(|e| e.to_string())?;
    Ok(guard.is_some())
}
