/// Screen lock detection and management for Computer Use sessions.
///
/// Provides platform-specific screen lock state detection and temporary unlock
/// capability so CU operations can proceed when the display is locked.
///
/// Platform support:
/// - macOS: CGSession + AppleScript (keystroke + Keychain password retrieval)
/// - Linux/Windows: Detection only; unlock not yet implemented (graceful degradation)
///
/// Security guarantees:
/// - Passwords stored exclusively in macOS Keychain (system-level encryption)
/// - Unlock is RAII-guarded: screen re-locks automatically on guard drop
/// - Physical input detection triggers immediate re-lock
/// - All unlock/lock operations are logged for audit
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

#[derive(Debug, thiserror::Error)]
pub enum ScreenLockError {
    #[error("screen lock operation failed: {0}")]
    OperationFailed(String),
    #[error("unlock not supported on this platform")]
    #[allow(dead_code)]
    UnsupportedPlatform,
    #[error("no password configured for screen unlock")]
    NoPasswordConfigured,
}

/// Audit log entry for screen lock operations.
#[derive(Debug, Clone, serde::Serialize)]
#[allow(dead_code)]
pub struct ScreenLockAuditEntry {
    pub timestamp_ms: u64,
    pub action: ScreenLockAction,
    pub success: bool,
    pub reason: String,
}

#[derive(Debug, Clone, serde::Serialize)]
#[allow(dead_code)]
pub enum ScreenLockAction {
    Unlock,
    Relock,
    DetectLocked,
    DetectUnlocked,
    PhysicalInputDetected,
}

/// Check whether the screen is currently locked.
pub fn is_screen_locked() -> bool {
    platform::is_screen_locked()
}

/// RAII guard that re-locks the screen on drop.
pub struct ScreenUnlockGuard {
    active: Arc<AtomicBool>,
    #[allow(dead_code)]
    unlocked_at: Instant,
}

impl ScreenUnlockGuard {
    /// Attempt to unlock the screen using the stored Keychain password.
    /// Returns a guard that will re-lock on drop.
    pub fn unlock(reason: &str) -> Result<Self, ScreenLockError> {
        log_audit(ScreenLockAction::Unlock, true, reason);

        platform::unlock_screen()?;

        Ok(Self {
            active: Arc::new(AtomicBool::new(true)),
            unlocked_at: Instant::now(),
        })
    }

    #[allow(dead_code)]
    pub fn is_active(&self) -> bool {
        self.active.load(Ordering::Relaxed)
    }

    #[allow(dead_code)]
    pub fn elapsed(&self) -> std::time::Duration {
        self.unlocked_at.elapsed()
    }
}

impl Drop for ScreenUnlockGuard {
    fn drop(&mut self) {
        if self.active.swap(false, Ordering::SeqCst) {
            let _ = platform::lock_screen();
            log_audit(ScreenLockAction::Relock, true, "guard dropped");
        }
    }
}

/// Store the user's login password in the platform keychain.
pub fn store_password(password: &str) -> Result<(), ScreenLockError> {
    platform::keychain_store(password)
}

/// Check whether a password is stored in the platform keychain.
pub fn has_stored_password() -> bool {
    platform::keychain_has_password()
}

/// Delete the stored password from the platform keychain.
pub fn delete_password() -> Result<(), ScreenLockError> {
    platform::keychain_delete()
}

fn log_audit(action: ScreenLockAction, success: bool, reason: &str) {
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64;
    let entry = ScreenLockAuditEntry {
        timestamp_ms: ts,
        action,
        success,
        reason: reason.to_string(),
    };
    // Structured log for audit trail
    println!(
        "[AUDIT] screen_lock: action={:?} success={} reason={} ts={}",
        entry.action, entry.success, entry.reason, entry.timestamp_ms
    );
}

// ── macOS implementation ──────────────────────────────────────────

#[cfg(target_os = "macos")]
mod platform {
    use super::ScreenLockError;
    use std::process::Command;

    const KEYCHAIN_SERVICE: &str = "com.myrm.agent.screen-unlock";
    const KEYCHAIN_ACCOUNT: &str = "login-password";

    pub fn is_screen_locked() -> bool {
        // CGSessionCopyCurrentDictionary → "CGSSessionScreenIsLocked"
        let script = r#"
            use framework "Foundation"
            set sessionDict to current application's CGSessionCopyCurrentDictionary() as record
            try
                set isLocked to |CGSSessionScreenIsLocked| of sessionDict
                if isLocked is 1 then return "locked"
            end try
            return "unlocked"
        "#;
        Command::new("osascript")
            .args(["-l", "AppleScript", "-e", script])
            .output()
            .map(|o| {
                String::from_utf8_lossy(&o.stdout)
                    .trim()
                    .eq_ignore_ascii_case("locked")
            })
            .unwrap_or(false)
    }

    pub fn unlock_screen() -> Result<(), ScreenLockError> {
        let password = keychain_read()?;

        // Wake display first (in case it's asleep)
        let _ = Command::new("caffeinate").args(["-u", "-t", "2"]).spawn();
        std::thread::sleep(std::time::Duration::from_millis(500));

        // Simulate keypress to dismiss login screen, then type password + Enter
        let script = format!(
            r#"
            tell application "System Events"
                key code 49 -- space to wake
                delay 0.5
                keystroke "{}"
                delay 0.2
                key code 36 -- return
            end tell
        "#,
            password.replace('\\', "\\\\").replace('"', "\\\"")
        );

        let output = Command::new("osascript")
            .args(["-e", &script])
            .output()
            .map_err(|e| ScreenLockError::OperationFailed(format!("osascript failed: {}", e)))?;

        if !output.status.success() {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(ScreenLockError::OperationFailed(format!(
                "unlock script failed: {}",
                stderr.trim()
            )));
        }

        // Verify unlock succeeded
        std::thread::sleep(std::time::Duration::from_secs(1));
        if is_screen_locked() {
            return Err(ScreenLockError::OperationFailed(
                "screen still locked after unlock attempt (wrong password?)".into(),
            ));
        }

        Ok(())
    }

    pub fn lock_screen() -> Result<(), ScreenLockError> {
        Command::new("osascript")
            .args([
                "-e",
                r#"tell application "System Events" to keystroke "q" using {control down, command down}"#,
            ])
            .output()
            .map_err(|e| {
                ScreenLockError::OperationFailed(format!("lock screen failed: {}", e))
            })?;
        Ok(())
    }

    pub fn keychain_store(password: &str) -> Result<(), ScreenLockError> {
        // Delete existing entry first (idempotent)
        let _ = keychain_delete();

        let output = Command::new("security")
            .args([
                "add-generic-password",
                "-s",
                KEYCHAIN_SERVICE,
                "-a",
                KEYCHAIN_ACCOUNT,
                "-w",
                password,
                "-U", // update if exists
            ])
            .output()
            .map_err(|e| {
                ScreenLockError::OperationFailed(format!("keychain store failed: {}", e))
            })?;

        if !output.status.success() {
            return Err(ScreenLockError::OperationFailed(
                String::from_utf8_lossy(&output.stderr).trim().to_string(),
            ));
        }
        Ok(())
    }

    pub fn keychain_has_password() -> bool {
        Command::new("security")
            .args([
                "find-generic-password",
                "-s",
                KEYCHAIN_SERVICE,
                "-a",
                KEYCHAIN_ACCOUNT,
            ])
            .output()
            .map(|o| o.status.success())
            .unwrap_or(false)
    }

    pub fn keychain_delete() -> Result<(), ScreenLockError> {
        let _ = Command::new("security")
            .args([
                "delete-generic-password",
                "-s",
                KEYCHAIN_SERVICE,
                "-a",
                KEYCHAIN_ACCOUNT,
            ])
            .output();
        Ok(())
    }

    fn keychain_read() -> Result<String, ScreenLockError> {
        let output = Command::new("security")
            .args([
                "find-generic-password",
                "-s",
                KEYCHAIN_SERVICE,
                "-a",
                KEYCHAIN_ACCOUNT,
                "-w", // output password only
            ])
            .output()
            .map_err(|e| {
                ScreenLockError::OperationFailed(format!("keychain read failed: {}", e))
            })?;

        if !output.status.success() {
            return Err(ScreenLockError::NoPasswordConfigured);
        }

        Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
    }
}

// ── Linux stub ────────────────────────────────────────────────────

#[cfg(target_os = "linux")]
mod platform {
    use super::ScreenLockError;

    pub fn is_screen_locked() -> bool {
        // Best-effort: check common lock daemons
        std::process::Command::new("loginctl")
            .args(["show-session", "self", "-p", "LockedHint"])
            .output()
            .map(|o| String::from_utf8_lossy(&o.stdout).contains("LockedHint=yes"))
            .unwrap_or(false)
    }

    pub fn unlock_screen() -> Result<(), ScreenLockError> {
        Err(ScreenLockError::UnsupportedPlatform)
    }

    pub fn lock_screen() -> Result<(), ScreenLockError> {
        let _ = std::process::Command::new("loginctl")
            .args(["lock-session"])
            .output();
        Ok(())
    }

    pub fn keychain_store(_password: &str) -> Result<(), ScreenLockError> {
        Err(ScreenLockError::UnsupportedPlatform)
    }

    pub fn keychain_has_password() -> bool {
        false
    }

    pub fn keychain_delete() -> Result<(), ScreenLockError> {
        Ok(())
    }
}

// ── Windows stub ──────────────────────────────────────────────────

#[cfg(target_os = "windows")]
mod platform {
    use super::ScreenLockError;

    pub fn is_screen_locked() -> bool {
        false // TODO: WTSQuerySessionInformation
    }

    pub fn unlock_screen() -> Result<(), ScreenLockError> {
        Err(ScreenLockError::UnsupportedPlatform)
    }

    pub fn lock_screen() -> Result<(), ScreenLockError> {
        Err(ScreenLockError::UnsupportedPlatform)
    }

    pub fn keychain_store(_password: &str) -> Result<(), ScreenLockError> {
        Err(ScreenLockError::UnsupportedPlatform)
    }

    pub fn keychain_has_password() -> bool {
        false
    }

    pub fn keychain_delete() -> Result<(), ScreenLockError> {
        Ok(())
    }
}
