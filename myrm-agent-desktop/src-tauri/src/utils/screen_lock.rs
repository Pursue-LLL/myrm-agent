//! Screen lock probe and lock request.
//!
//! The unlock itself (typing the credential into the login window) lives in the
//! Python server, the only party that needs the credential (see
//! `screen_credential`). This module owns what the desktop shell needs: the lock
//! probe the curtain watcher polls every second and the lock request used by the
//! curtain input guard.
//!
//! [INPUT]
//! - macOS CoreGraphics session dictionary / Win32 input desktop / loginctl
//!
//! [OUTPUT]
//! - ScreenLockError
//! - is_screen_locked / lock_screen / lock_screen_confirmed
//!
//! [POS]
//! Platform primitives behind `commands::privacy_curtain*` (probe + lock request).

use std::time::{Duration, Instant};

#[derive(Debug, thiserror::Error)]
pub enum ScreenLockError {
    #[error("screen lock operation failed: {0}")]
    OperationFailed(String),
    #[error("operation not supported on this platform")]
    #[allow(dead_code)]
    UnsupportedPlatform,
}

/// Interval between probes while waiting for a lock request to take effect.
const LOCK_CONFIRM_POLL: Duration = Duration::from_millis(50);

/// Check whether the screen is currently locked.
///
/// A failed probe reports `false` (unlocked): callers treat that as "nothing to
/// protect", never as proof the screen is safe.
pub fn is_screen_locked() -> bool {
    platform::is_screen_locked()
}

/// Request an immediate screen lock (fire-and-forget).
pub fn lock_screen() -> Result<(), ScreenLockError> {
    platform::lock_screen()
}

/// Request a screen lock and wait until the system reports a locked session.
///
/// The lock chord is only a *request*: keystroke injection can succeed while
/// nothing locks. Callers that must not expose the desktop in between (the
/// curtain input guard) use this and keep the curtain up on `Err`.
pub fn lock_screen_confirmed(timeout: Duration) -> Result<(), ScreenLockError> {
    if is_screen_locked() {
        return Ok(());
    }
    lock_screen()?;
    let deadline = Instant::now() + timeout;
    loop {
        if is_screen_locked() {
            return Ok(());
        }
        if Instant::now() >= deadline {
            return Err(ScreenLockError::OperationFailed(
                "screen did not report locked in time".into(),
            ));
        }
        std::thread::sleep(LOCK_CONFIRM_POLL);
    }
}

// ── macOS implementation ──────────────────────────────────────────

#[cfg(target_os = "macos")]
mod platform {
    use super::ScreenLockError;
    use std::ffi::{c_char, c_void, CStr};
    use std::process::Command;
    use std::ptr;

    /// Present (true) in the session dictionary only while the screen is locked.
    const SESSION_SCREEN_LOCKED_KEY: &CStr = c"CGSSessionScreenIsLocked";
    const UTF8_ENCODING: u32 = 0x0800_0100;
    /// `kCFNumberSInt32Type`.
    const CF_NUMBER_SINT32_TYPE: isize = 3;

    type CFTypeRef = *const c_void;
    type CFStringRef = *const c_void;
    type CFDictionaryRef = *const c_void;

    #[link(name = "CoreGraphics", kind = "framework")]
    unsafe extern "C" {
        fn CGSessionCopyCurrentDictionary() -> CFDictionaryRef;
    }

    #[link(name = "CoreFoundation", kind = "framework")]
    unsafe extern "C" {
        fn CFStringCreateWithCString(
            alloc: *const c_void,
            c_str: *const c_char,
            encoding: u32,
        ) -> CFStringRef;
        fn CFDictionaryGetValue(dict: CFDictionaryRef, key: CFTypeRef) -> CFTypeRef;
        fn CFGetTypeID(value: CFTypeRef) -> usize;
        fn CFBooleanGetTypeID() -> usize;
        fn CFBooleanGetValue(boolean: CFTypeRef) -> u8;
        fn CFNumberGetTypeID() -> usize;
        fn CFNumberGetValue(number: CFTypeRef, number_type: isize, value: *mut c_void) -> u8;
        fn CFRelease(value: CFTypeRef);
    }

    /// Read a boolean-like entry (CFBoolean, or a non-zero CFNumber) from a dictionary.
    ///
    /// # Safety
    /// `dict` must be a valid `CFDictionaryRef`.
    unsafe fn dictionary_flag(dict: CFDictionaryRef, key: &CStr) -> bool {
        let cf_key = CFStringCreateWithCString(ptr::null(), key.as_ptr(), UTF8_ENCODING);
        if cf_key.is_null() {
            return false;
        }
        // Get rule: `value` is borrowed from `dict`, only `cf_key` is ours to release.
        let value = CFDictionaryGetValue(dict, cf_key);
        CFRelease(cf_key);
        if value.is_null() {
            return false;
        }

        let type_id = CFGetTypeID(value);
        if type_id == CFBooleanGetTypeID() {
            return CFBooleanGetValue(value) != 0;
        }
        if type_id == CFNumberGetTypeID() {
            let mut number: i32 = 0;
            let read = CFNumberGetValue(
                value,
                CF_NUMBER_SINT32_TYPE,
                ptr::from_mut(&mut number).cast(),
            );
            return read != 0 && number != 0;
        }
        false
    }

    /// In-process probe: a spawned `osascript` costs ~290 ms of CPU per call, which
    /// at the watcher's 1 Hz tick is a quarter of a core.
    pub fn is_screen_locked() -> bool {
        // SAFETY: "Copy" rule — we own the returned dictionary and release it
        // below; it is only read through `dictionary_flag`.
        unsafe {
            let session = CGSessionCopyCurrentDictionary();
            if session.is_null() {
                // No GUI session (e.g. SSH): there is no screen to lock.
                return false;
            }
            let locked = dictionary_flag(session, SESSION_SCREEN_LOCKED_KEY);
            CFRelease(session);
            locked
        }
    }

    /// Request a screen lock via the system lock chord.
    ///
    /// The chord is only a *request*: an unprivileged caller can see the
    /// command succeed while nothing locks (keystroke injection needs
    /// Accessibility). Callers that need certainty confirm with
    /// [`is_screen_locked`] (see `lock_screen_confirmed`).
    pub fn lock_screen() -> Result<(), ScreenLockError> {
        let output = Command::new("osascript")
            .args([
                "-e",
                r#"tell application "System Events" to keystroke "q" using {control down, command down}"#,
            ])
            .output()
            .map_err(|e| {
                ScreenLockError::OperationFailed(format!("lock screen failed: {}", e))
            })?;
        if !output.status.success() {
            return Err(ScreenLockError::OperationFailed(format!(
                "lock screen command exited with {}",
                output.status
            )));
        }
        Ok(())
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        use std::time::Instant;

        #[link(name = "CoreFoundation", kind = "framework")]
        unsafe extern "C" {
            static kCFBooleanTrue: CFTypeRef;
            static kCFBooleanFalse: CFTypeRef;
            static kCFTypeDictionaryKeyCallBacks: u8;
            static kCFTypeDictionaryValueCallBacks: u8;
            fn CFDictionaryCreate(
                alloc: *const c_void,
                keys: *const CFTypeRef,
                values: *const CFTypeRef,
                count: isize,
                key_callbacks: *const u8,
                value_callbacks: *const u8,
            ) -> CFDictionaryRef;
            fn CFNumberCreate(
                alloc: *const c_void,
                number_type: isize,
                value: *const c_void,
            ) -> CFTypeRef;
        }

        /// Build a one-entry dictionary `{ SESSION_SCREEN_LOCKED_KEY: value }`.
        unsafe fn dictionary_with(value: CFTypeRef) -> CFDictionaryRef {
            let key = CFStringCreateWithCString(
                ptr::null(),
                SESSION_SCREEN_LOCKED_KEY.as_ptr(),
                UTF8_ENCODING,
            );
            let dict = CFDictionaryCreate(
                ptr::null(),
                &key,
                &value,
                1,
                ptr::addr_of!(kCFTypeDictionaryKeyCallBacks),
                ptr::addr_of!(kCFTypeDictionaryValueCallBacks),
            );
            CFRelease(key);
            dict
        }

        fn flag_for(value: CFTypeRef) -> bool {
            // SAFETY: `dict` is created and released within this scope.
            unsafe {
                let dict = dictionary_with(value);
                let flag = dictionary_flag(dict, SESSION_SCREEN_LOCKED_KEY);
                CFRelease(dict);
                flag
            }
        }

        #[test]
        fn cf_boolean_true_means_locked() {
            assert!(flag_for(unsafe { kCFBooleanTrue }));
        }

        #[test]
        fn cf_boolean_false_means_unlocked() {
            assert!(!flag_for(unsafe { kCFBooleanFalse }));
        }

        #[test]
        fn cf_number_is_read_as_non_zero() {
            for (raw, expected) in [(1_i32, true), (0_i32, false)] {
                // SAFETY: the number is created and released within this scope.
                let flag = unsafe {
                    let number = CFNumberCreate(
                        ptr::null(),
                        CF_NUMBER_SINT32_TYPE,
                        ptr::from_ref(&raw).cast(),
                    );
                    let flag = flag_for(number);
                    CFRelease(number);
                    flag
                };
                assert_eq!(flag, expected, "CFNumber {raw}");
            }
        }

        #[test]
        fn absent_key_means_unlocked() {
            let other = c"SomeOtherKey";
            // SAFETY: dictionary is created and released within this scope.
            let flag = unsafe {
                let dict = dictionary_with(kCFBooleanTrue);
                let flag = dictionary_flag(dict, other);
                CFRelease(dict);
                flag
            };
            assert!(!flag);
        }

        #[test]
        fn live_probe_is_in_process_and_cheap() {
            // Warm up once, then average: a probe that spawns osascript costs
            // hundreds of milliseconds per call.
            let _ = is_screen_locked();
            let rounds = 20;
            let started = Instant::now();
            for _ in 0..rounds {
                let _ = is_screen_locked();
            }
            let mean = started.elapsed() / rounds;
            assert!(mean.as_millis() < 20, "probe mean {mean:?}");
        }
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

    pub fn lock_screen() -> Result<(), ScreenLockError> {
        let _ = std::process::Command::new("loginctl")
            .args(["lock-session"])
            .output();
        Ok(())
    }
}

// ── Windows stub ──────────────────────────────────────────────────

#[cfg(target_os = "windows")]
mod platform {
    use super::ScreenLockError;

    pub fn is_screen_locked() -> bool {
        #[link(name = "user32")]
        extern "system" {
            fn OpenInputDesktop(flags: u32, inherit: i32, access: u32) -> isize;
            fn CloseDesktop(hdesk: isize) -> i32;
        }
        unsafe {
            // DESKTOP_SWITCHDESKTOP = 0x0100
            let hdesk = OpenInputDesktop(0, 0, 0x0100);
            if hdesk == 0 {
                true
            } else {
                CloseDesktop(hdesk);
                false
            }
        }
    }

    pub fn lock_screen() -> Result<(), ScreenLockError> {
        Err(ScreenLockError::UnsupportedPlatform)
    }
}
