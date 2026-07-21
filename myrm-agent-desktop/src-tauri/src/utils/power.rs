/// Intelligent power lock to prevent system sleep while agent tasks are executing.
///
/// Platform support:
/// - macOS: `IOKit` native API (`IOPMAssertionCreateWithName`)
/// - Linux: `systemd-inhibit` subprocess
/// - Windows: SetThreadExecutionState Win32 API
///
/// Usage:
/// ```rust
/// let guard = PowerLock::acquire("Agent task in progress", false)?;
/// // ... task runs ...
/// drop(guard); // releases the lock
///
/// // For Computer Use sessions that need the display to stay on:
/// let guard = PowerLock::acquire("CU session", true)?;
/// ```
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

#[derive(Debug, thiserror::Error)]
pub enum PowerError {
    #[error("platform API failed: {0}")]
    PlatformError(String),
}

/// RAII guard that releases the power assertion on drop.
pub struct PowerLock {
    _inner: PlatformLock,
    active: Arc<AtomicBool>,
}

impl PowerLock {
    /// Acquire a power lock preventing system sleep.
    ///
    /// When `prevent_display_sleep` is true, the display is also kept awake
    /// (required for Computer Use screenshots to capture actual screen content).
    pub fn acquire(reason: &str, prevent_display_sleep: bool) -> Result<Self, PowerError> {
        let active = Arc::new(AtomicBool::new(true));
        let inner = PlatformLock::acquire(reason, prevent_display_sleep)?;
        Ok(Self {
            _inner: inner,
            active,
        })
    }

    #[allow(dead_code)]
    pub fn is_active(&self) -> bool {
        self.active.load(Ordering::Relaxed)
    }
}

impl Drop for PowerLock {
    fn drop(&mut self) {
        self.active.store(false, Ordering::Relaxed);
    }
}

// --- macOS: IOKit native API ---

#[cfg(target_os = "macos")]
mod platform {
    use super::PowerError;
    use std::ffi::{c_char, c_void, CString};
    use std::ptr;

    const UTF8_ENCODING: u32 = 0x0800_0100;
    const ASSERTION_LEVEL_ON: u32 = 255;
    const ASSERTION_ID_NONE: u32 = 0;
    const PREVENT_USER_IDLE_SYSTEM_SLEEP: &str = "PreventUserIdleSystemSleep";
    const PREVENT_SYSTEM_SLEEP: &str = "PreventSystemSleep";
    const PREVENT_USER_IDLE_DISPLAY_SLEEP: &str = "PreventUserIdleDisplaySleep";

    type CFStringRef = *const c_void;
    type CFTypeRef = *const c_void;
    type IOPMAssertionID = u32;
    type IOPMAssertionLevel = u32;
    type IOReturn = i32;

    #[link(name = "CoreFoundation", kind = "framework")]
    unsafe extern "C" {
        fn CFStringCreateWithCString(
            alloc: *const c_void,
            c_str: *const c_char,
            encoding: u32,
        ) -> CFStringRef;
        fn CFRelease(value: CFTypeRef);
    }

    #[link(name = "IOKit", kind = "framework")]
    unsafe extern "C" {
        fn IOPMAssertionCreateWithName(
            assertion_type: CFStringRef,
            assertion_level: IOPMAssertionLevel,
            assertion_name: CFStringRef,
            assertion_id: *mut IOPMAssertionID,
        ) -> IOReturn;
        fn IOPMAssertionRelease(assertion_id: IOPMAssertionID) -> IOReturn;
    }

    struct CfString(CFStringRef);

    impl CfString {
        fn new(value: &str) -> Result<Self, PowerError> {
            let c_string = CString::new(value).map_err(|_| {
                PowerError::PlatformError(
                    "Power assertion strings must not contain NUL bytes".into(),
                )
            })?;
            let string_ref =
                unsafe { CFStringCreateWithCString(ptr::null(), c_string.as_ptr(), UTF8_ENCODING) };
            if string_ref.is_null() {
                return Err(PowerError::PlatformError(
                    "Failed to allocate CoreFoundation string".into(),
                ));
            }
            Ok(Self(string_ref))
        }

        const fn as_ptr(&self) -> CFStringRef {
            self.0
        }
    }

    impl Drop for CfString {
        fn drop(&mut self) {
            if !self.0.is_null() {
                unsafe { CFRelease(self.0) };
            }
        }
    }

    pub struct PlatformLock {
        assertion_ids: Vec<IOPMAssertionID>,
    }

    impl PlatformLock {
        pub fn acquire(reason: &str, prevent_display_sleep: bool) -> Result<Self, PowerError> {
            let mut assertion_ids = Vec::new();

            // We always want to prevent idle system sleep and system sleep on AC
            let kinds = if prevent_display_sleep {
                vec![
                    PREVENT_USER_IDLE_SYSTEM_SLEEP,
                    PREVENT_SYSTEM_SLEEP,
                    PREVENT_USER_IDLE_DISPLAY_SLEEP,
                ]
            } else {
                vec![PREVENT_USER_IDLE_SYSTEM_SLEEP, PREVENT_SYSTEM_SLEEP]
            };

            for kind in kinds {
                let assertion_type = CfString::new(kind)?;
                let assertion_reason = CfString::new(reason)?;
                let mut assertion_id = ASSERTION_ID_NONE;

                let status = unsafe {
                    IOPMAssertionCreateWithName(
                        assertion_type.as_ptr(),
                        ASSERTION_LEVEL_ON,
                        assertion_reason.as_ptr(),
                        &mut assertion_id,
                    )
                };

                if status != 0 {
                    // Cleanup already acquired assertions
                    for id in assertion_ids {
                        unsafe { IOPMAssertionRelease(id) };
                    }
                    return Err(PowerError::PlatformError(format!(
                        "Failed to acquire macOS power assertion {} (IOReturn={})",
                        kind, status
                    )));
                }
                assertion_ids.push(assertion_id);
            }

            Ok(Self { assertion_ids })
        }
    }

    impl Drop for PlatformLock {
        fn drop(&mut self) {
            for id in self.assertion_ids.drain(..) {
                if id != ASSERTION_ID_NONE {
                    unsafe { IOPMAssertionRelease(id) };
                }
            }
        }
    }
}

// --- Linux: systemd-inhibit subprocess ---

#[cfg(target_os = "linux")]
mod platform {
    use super::PowerError;
    use std::process::{Child, Command, Stdio};

    pub struct PlatformLock {
        child: Option<Child>,
    }

    impl PlatformLock {
        pub fn acquire(reason: &str, _prevent_display_sleep: bool) -> Result<Self, PowerError> {
            let child = Command::new("systemd-inhibit")
                .args([
                    "--what=idle:sleep",
                    &format!("--why={}", reason),
                    "sleep",
                    "infinity",
                ])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn()
                .map_err(|e| PowerError::PlatformError(format!("systemd-inhibit: {}", e)))?;

            Ok(Self { child: Some(child) })
        }
    }

    impl Drop for PlatformLock {
        fn drop(&mut self) {
            if let Some(ref mut child) = self.child {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

// --- Windows: SetThreadExecutionState ---

#[cfg(target_os = "windows")]
mod platform {
    use super::PowerError;

    #[link(name = "kernel32")]
    extern "system" {
        fn SetThreadExecutionState(es_flags: u32) -> u32;
    }

    const ES_CONTINUOUS: u32 = 0x80000000;
    const ES_SYSTEM_REQUIRED: u32 = 0x00000001;
    const ES_DISPLAY_REQUIRED: u32 = 0x00000002;

    pub struct PlatformLock;

    impl PlatformLock {
        pub fn acquire(_reason: &str, prevent_display_sleep: bool) -> Result<Self, PowerError> {
            let mut flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED;
            if prevent_display_sleep {
                flags |= ES_DISPLAY_REQUIRED;
            }
            let result = unsafe { SetThreadExecutionState(flags) };
            if result == 0 {
                return Err(PowerError::PlatformError(
                    "SetThreadExecutionState returned 0".to_string(),
                ));
            }
            Ok(Self)
        }
    }

    impl Drop for PlatformLock {
        fn drop(&mut self) {
            unsafe {
                SetThreadExecutionState(ES_CONTINUOUS);
            }
        }
    }
}

use platform::PlatformLock;
