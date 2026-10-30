//! Exclude a WebviewWindow from system screen capture (Windows WDA; macOS no-op here).

use tauri::WebviewWindow;

/// Windows：WDA_EXCLUDEFROMCAPTURE；其它平台当前为 no-op（macOS 由 harness Quartz 通道处理）。
pub fn apply_capture_exclusion(window: &WebviewWindow) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            SetWindowDisplayAffinity, WDA_EXCLUDEFROMCAPTURE,
        };
        let hwnd = window.hwnd().map_err(|e| e.to_string())?;
        // SAFETY: `hwnd` is the live native handle of `window`; tauri's HWND wraps the raw pointer windows-sys expects.
        let ok = unsafe { SetWindowDisplayAffinity(hwnd.0, WDA_EXCLUDEFROMCAPTURE) };
        if ok == 0 {
            return Err(
                "SetWindowDisplayAffinity failed: Windows build below 2004 cannot exclude window from capture"
                    .to_string(),
            );
        }
        Ok(())
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = window;
        Ok(())
    }
}
