//! Inline Input：全局快捷键唤起 FlowPad Inline Mode + 结果回写原应用
//!
//! [INPUT]
//! - ConfigManager (POS: 配置管理，提供 inline_input_shortcut)
//! - Tauri AppHandle (IPC 事件、窗口管理、剪贴板)
//! - enigo (跨平台键盘模拟)
//!
//! [OUTPUT]
//! - IPC 事件: `inline-input-activated` (screenshot_b64, windowTitle, extractedText, sourcePid, timestamp)
//! - Tauri 命令: `inline_paste_back` (将内容粘贴回原应用)
//!
//! [POS]
//! Inline Input 的唯一入口。负责记录原应用 PID、触发截屏、
//! emit 事件到前端 FlowPad Inline Mode，以及将 AI 结果通过
//! 剪贴板 + Cmd/Ctrl+V 回写到原应用。

use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager};

use crate::config::ConfigManager;

/// 用于在全局快捷键 handler 中识别 Inline Input 绑定
pub static INLINE_INPUT_SHORTCUT_STR: Mutex<String> = Mutex::new(String::new());

/// 记录触发 Inline Input 时的原应用 PID（用于激活回写）
static SOURCE_PID: Mutex<Option<u32>> = Mutex::new(None);

/// Inline Input 快捷键触发：记录原应用 PID，截屏，emit 事件
pub fn handle_inline_input_shortcut(app: &AppHandle) {
    let app_handle = app.clone();

    thread::spawn(move || {
        let pid = get_frontmost_pid();
        if let Ok(mut guard) = SOURCE_PID.lock() {
            *guard = Some(pid);
        }

        let excluded_apps = load_excluded_apps(&app_handle);
        let front_app_name = get_frontmost_app_name();

        if is_app_excluded(&front_app_name, &excluded_apps) {
            return;
        }

        let timestamp = current_timestamp_ms();

        #[cfg(target_os = "macos")]
        let (screenshot_b64, window_title, extracted_text, _) = super::appshot::capture_macos();

        #[cfg(target_os = "windows")]
        let (screenshot_b64, window_title, extracted_text, _) = super::appshot::capture_windows();

        #[cfg(not(any(target_os = "macos", target_os = "windows")))]
        let (screenshot_b64, window_title, extracted_text) =
            (String::new(), String::new(), String::new());

        let payload = serde_json::json!({
            "screenshot": screenshot_b64,
            "windowTitle": window_title,
            "extractedText": extracted_text,
            "sourcePid": pid,
            "timestamp": timestamp,
        });

        let _ = app_handle.emit("inline-input-activated", payload);
        show_main_window_inline(&app_handle);
    });
}

/// 将内容粘贴回原应用：保存剪贴板 → 写入内容 → 激活原应用 → Cmd+V → 恢复剪贴板
pub fn paste_back(app: &AppHandle, content: String) -> Result<(), String> {
    let source_pid = SOURCE_PID
        .lock()
        .map_err(|e| format!("Failed to read source PID: {}", e))?
        .ok_or_else(|| "No source app recorded".to_string())?;

    let app_handle = app.clone();

    thread::spawn(move || {
        let saved_clipboard = save_clipboard();

        set_clipboard_text(&app_handle, &content);

        thread::sleep(Duration::from_millis(100));

        activate_pid(source_pid);

        thread::sleep(Duration::from_millis(200));

        simulate_paste();

        thread::sleep(Duration::from_millis(300));

        if let Some(saved) = saved_clipboard {
            set_clipboard_text(&app_handle, &saved);
        }
    });

    Ok(())
}

/// 显示主窗口（Inline 模式：不抢焦点，仅显示）
fn show_main_window_inline(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        #[cfg(target_os = "macos")]
        {
            let _ = app.set_activation_policy(tauri::ActivationPolicy::Regular);
        }
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn current_timestamp_ms() -> u128 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

fn load_excluded_apps(app: &AppHandle) -> std::collections::HashSet<String> {
    let config_manager = app.state::<ConfigManager>();
    let config = config_manager.load();
    config
        .appshot_excluded_apps
        .into_iter()
        .map(|s| s.to_lowercase())
        .collect()
}

fn is_app_excluded(app_name: &str, excluded: &std::collections::HashSet<String>) -> bool {
    if app_name.is_empty() || excluded.is_empty() {
        return false;
    }
    excluded.contains(&app_name.to_lowercase())
}

// ─── Platform-specific implementations ───────────────────────────────────────

fn save_clipboard() -> Option<String> {
    #[cfg(target_os = "macos")]
    {
        use std::process::Command;
        Command::new("pbpaste")
            .output()
            .ok()
            .filter(|o| o.status.success())
            .map(|o| String::from_utf8_lossy(&o.stdout).to_string())
    }
    #[cfg(target_os = "windows")]
    {
        // Windows clipboard save via PowerShell
        use std::process::Command;
        let mut cmd = Command::new("powershell");
        cmd.args(["-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard"]);
        super::suppress_console_window(&mut cmd);
        cmd.output()
            .ok()
            .filter(|o| o.status.success())
            .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        None
    }
}

fn set_clipboard_text(app: &AppHandle, text: &str) {
    // Use Tauri clipboard plugin via IPC (synchronous for this thread context)
    #[cfg(target_os = "macos")]
    {
        use std::process::Command;
        let mut child = Command::new("pbcopy")
            .stdin(std::process::Stdio::piped())
            .spawn()
            .expect("Failed to spawn pbcopy");
        if let Some(stdin) = child.stdin.as_mut() {
            use std::io::Write;
            let _ = stdin.write_all(text.as_bytes());
        }
        let _ = child.wait();
    }
    #[cfg(target_os = "windows")]
    {
        use std::process::Command;
        let escaped = text.replace('\'', "''");
        let script = format!("Set-Clipboard -Value '{}'", escaped);
        let mut cmd = Command::new("powershell");
        cmd.args(["-NoProfile", "-NonInteractive", "-Command", &script]);
        super::suppress_console_window(&mut cmd);
        let _ = cmd.output();
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        let _ = (app, text);
    }
}

fn simulate_paste() {
    use enigo::{Enigo, Key, Keyboard, Settings};

    let Ok(mut enigo) = Enigo::new(&Settings::default()) else {
        eprintln!("Failed to create Enigo instance for paste simulation");
        return;
    };

    #[cfg(target_os = "macos")]
    {
        let _ = enigo.key(Key::Meta, enigo::Direction::Press);
        let _ = enigo.key(Key::Unicode('v'), enigo::Direction::Click);
        let _ = enigo.key(Key::Meta, enigo::Direction::Release);
    }

    #[cfg(target_os = "windows")]
    {
        let _ = enigo.key(Key::Control, enigo::Direction::Press);
        let _ = enigo.key(Key::Unicode('v'), enigo::Direction::Click);
        let _ = enigo.key(Key::Control, enigo::Direction::Release);
    }

    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        eprintln!("Inline paste not supported on this platform");
    }
}

fn get_frontmost_pid() -> u32 {
    #[cfg(target_os = "macos")]
    {
        use std::process::Command;
        if let Ok(output) = Command::new("osascript")
            .args([
                "-e",
                r#"tell application "System Events" to get unix id of first application process whose frontmost is true"#,
            ])
            .output()
        {
            if output.status.success() {
                let pid_str = String::from_utf8_lossy(&output.stdout).trim().to_string();
                return pid_str.parse().unwrap_or(0);
            }
        }
        0
    }
    #[cfg(target_os = "windows")]
    {
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            GetForegroundWindow, GetWindowThreadProcessId,
        };
        unsafe {
            let hwnd = GetForegroundWindow();
            if hwnd == 0 {
                return 0;
            }
            let mut pid: u32 = 0;
            GetWindowThreadProcessId(hwnd, &mut pid);
            pid
        }
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        0
    }
}

fn activate_pid(pid: u32) {
    #[cfg(target_os = "macos")]
    {
        use std::process::Command;
        let script = format!(
            r#"tell application "System Events" to set frontmost of first process whose unix id is {} to true"#,
            pid
        );
        let _ = Command::new("osascript").args(["-e", &script]).output();
    }
    #[cfg(target_os = "windows")]
    {
        use windows_sys::Win32::UI::WindowsAndMessaging::{
            EnumWindows, GetWindowThreadProcessId, IsWindowVisible, SetForegroundWindow,
        };
        unsafe {
            unsafe extern "system" fn callback(hwnd: isize, lparam: isize) -> i32 {
                let target_pid = lparam as u32;
                let mut window_pid: u32 = 0;
                GetWindowThreadProcessId(hwnd, &mut window_pid);
                if window_pid == target_pid && IsWindowVisible(hwnd) != 0 {
                    SetForegroundWindow(hwnd);
                    return 0; // stop
                }
                1 // continue
            }
            EnumWindows(Some(callback), pid as isize);
        }
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        let _ = pid;
    }
}

fn get_frontmost_app_name() -> String {
    #[cfg(target_os = "macos")]
    {
        use std::process::Command;
        if let Ok(output) = Command::new("osascript")
            .args([
                "-e",
                r#"tell application "System Events" to get name of first application process whose frontmost is true"#,
            ])
            .output()
        {
            if output.status.success() {
                return String::from_utf8_lossy(&output.stdout).trim().to_string();
            }
        }
        String::new()
    }
    #[cfg(target_os = "windows")]
    {
        super::appshot::win_get_foreground_app_name()
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        String::new()
    }
}
