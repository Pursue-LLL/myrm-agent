//! Appshot 全局快捷键：截屏 + 前台窗口文本提取 + 隐私黑名单拦截

use std::collections::HashSet;
use std::process::Command;
use tauri::{AppHandle, Emitter, Manager};

use crate::config::ConfigManager;

/// 用于在全局快捷键 handler 中识别 Appshot 绑定
pub static APPSHOT_SHORTCUT_STR: std::sync::Mutex<String> =
    std::sync::Mutex::new(String::new());

/// 切换主窗口显示/隐藏
pub fn handle_toggle_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.is_visible().unwrap_or(false) {
            let _ = window.hide();
            #[cfg(target_os = "macos")]
            {
                let _ = app.set_activation_policy(tauri::ActivationPolicy::Accessory);
            }
        } else {
            #[cfg(target_os = "macos")]
            {
                let _ = app.set_activation_policy(tauri::ActivationPolicy::Regular);
            }
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
}

/// 截屏入口：检查隐私黑名单后执行截屏
pub fn handle_appshot_shortcut(app: &AppHandle) {
    let excluded_apps = load_excluded_apps(app);
    let app_handle = app.clone();

    std::thread::spawn(move || {
        let front_app_name = get_frontmost_app_name();

        if is_app_excluded(&front_app_name, &excluded_apps) {
            let timestamp = current_timestamp_ms();
            let payload = serde_json::json!({
                "blockedApp": front_app_name,
                "timestamp": timestamp,
            });
            let _ = app_handle.emit("appshot-blocked", payload);
            show_main_window(&app_handle);
            return;
        }

        do_capture_and_emit(&app_handle);
    });
}

/// 绕过黑名单强制截屏（用户点击 "Continue Anyway" 后调用）
pub fn force_capture(app: &AppHandle) {
    let app_handle = app.clone();
    std::thread::spawn(move || {
        do_capture_and_emit(&app_handle);
    });
}

fn do_capture_and_emit(app: &AppHandle) {
    let timestamp = current_timestamp_ms();

    #[cfg(target_os = "macos")]
    let (screenshot_b64, window_title, extracted_text, needs_permission) = capture_appshot_macos();

    #[cfg(not(target_os = "macos"))]
    let (screenshot_b64, window_title, extracted_text, needs_permission) =
        capture_appshot_fallback();

    let payload = serde_json::json!({
        "screenshot": screenshot_b64,
        "windowTitle": window_title,
        "extractedText": extracted_text,
        "needsPermission": needs_permission,
        "timestamp": timestamp,
    });

    if let Err(e) = app.emit("appshot-captured", payload) {
        eprintln!("Failed to emit appshot event: {}", e);
    }

    show_main_window(app);
}

fn show_main_window(app: &AppHandle) {
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

fn load_excluded_apps(app: &AppHandle) -> HashSet<String> {
    let config_manager = app.state::<ConfigManager>();
    let config = config_manager.load();
    config
        .appshot_excluded_apps
        .into_iter()
        .map(|s| s.to_lowercase())
        .collect()
}

fn is_app_excluded(app_name: &str, excluded: &HashSet<String>) -> bool {
    if app_name.is_empty() || excluded.is_empty() {
        return false;
    }
    excluded.contains(&app_name.to_lowercase())
}

fn get_frontmost_app_name() -> String {
    #[cfg(target_os = "macos")]
    {
        if let Ok(output) = Command::new("osascript")
            .args(["-e", r#"tell application "System Events" to get name of first application process whose frontmost is true"#])
            .output()
        {
            if output.status.success() {
                return String::from_utf8_lossy(&output.stdout).trim().to_string();
            }
        }
        String::new()
    }
    #[cfg(not(target_os = "macos"))]
    {
        String::new()
    }
}

#[cfg(target_os = "macos")]
fn capture_appshot_macos() -> (String, String, String, bool) {
    use base64::Engine;
    use std::io::Read;

    let mut screenshot_b64 = String::new();
    let tmp_path = std::env::temp_dir().join(format!("appshot_{}.jpg", std::process::id()));

    if let Ok(output) = Command::new("screencapture")
        .args(["-x", "-C", "-t", "jpg", tmp_path.to_str().unwrap_or("/tmp/appshot.jpg")])
        .output()
    {
        if output.status.success() {
            if let Ok(mut f) = std::fs::File::open(&tmp_path) {
                let mut buf = Vec::new();
                if f.read_to_end(&mut buf).is_ok() {
                    screenshot_b64 = base64::engine::general_purpose::STANDARD.encode(&buf);
                }
            }
        }
    }
    let _ = std::fs::remove_file(&tmp_path);

    let ax_script = r#"
tell application "System Events"
    set frontApp to first application process whose frontmost is true
    set appName to name of frontApp
    set winTitle to ""
    try
        set winTitle to name of window 1 of frontApp
    end try
    set textParts to {}
    try
        set uiElements to entire contents of window 1 of frontApp
        set maxElements to (count of uiElements)
        if maxElements > 500 then set maxElements to 500
        repeat with i from 1 to maxElements
            set elem to item i of uiElements
            try
                set elemRole to role of elem
                if elemRole is in {"AXTextField", "AXTextArea", "AXStaticText"} then
                    set elemValue to value of elem
                    if elemValue is not missing value and elemValue is not "" then
                        set end of textParts to elemValue
                    end if
                end if
            end try
        end repeat
    end try
    set AppleScript's text item delimiters to linefeed
    return appName & "|||" & winTitle & "|||" & (textParts as string)
end tell
"#;

    let (mut window_title, mut extracted_text, mut needs_permission) =
        (String::new(), String::new(), false);

    if let Ok(output) = Command::new("osascript").args(["-e", ax_script]).output() {
        if output.status.success() {
            let result = String::from_utf8_lossy(&output.stdout).trim().to_string();
            let parts: Vec<&str> = result.splitn(3, "|||").collect();
            window_title = parts.first().unwrap_or(&"").to_string();
            if parts.len() > 1 {
                window_title = format!("{} - {}", window_title, parts[1]);
            }
            if parts.len() > 2 {
                extracted_text = parts[2].to_string();
            }
        } else {
            let stderr = String::from_utf8_lossy(&output.stderr);
            if stderr.contains("不允许辅助访问")
                || stderr.to_lowercase().contains("not allowed assistive")
            {
                needs_permission = true;
            }
            if let Ok(title_out) = Command::new("osascript")
                .args(["-e", r#"tell application "System Events" to get name of first application process whose frontmost is true"#])
                .output()
            {
                if title_out.status.success() {
                    window_title = String::from_utf8_lossy(&title_out.stdout).trim().to_string();
                }
            }
        }
    }

    (screenshot_b64, window_title, extracted_text, needs_permission)
}

#[cfg(not(target_os = "macos"))]
fn capture_appshot_fallback() -> (String, String, String, bool) {
    (String::new(), String::new(), String::new(), false)
}
