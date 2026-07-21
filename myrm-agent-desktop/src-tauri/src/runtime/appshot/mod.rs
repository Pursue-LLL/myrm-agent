//! 全局快捷键处理中心：Appshot 截屏 + Voice PTT + 窗口切换
//!
//! [INPUT]
//! - config::ConfigManager (POS: 配置管理，提供 appshot_excluded_apps 隐私黑名单)
//! - Tauri AppHandle (用于 emit IPC 事件和窗口管理)
//! - appshot::capture_macos / capture_windows (POS: 平台截屏实现)
//!
//! [OUTPUT]
//! - IPC 事件: `appshot-captured` / `appshot-blocked` / `voice-ptt-*`
//! - 全局快捷键静态绑定: APPSHOT_SHORTCUT_STR / VOICE_PTT_SHORTCUT_STR
//!
//! [POS]
//! 全局快捷键处理的唯一入口。负责隐私黑名单、Voice PTT、主窗口 toggle。

mod common;

#[cfg(target_os = "macos")]
mod capture_macos;
#[cfg(target_os = "windows")]
mod capture_windows;

use tauri::{AppHandle, Emitter, Manager};

pub(crate) use common::{
    current_timestamp_ms, get_frontmost_app_name, is_app_excluded, load_excluded_apps,
};

#[cfg(target_os = "macos")]
pub(crate) use capture_macos::capture_macos;
#[cfg(target_os = "windows")]
pub use capture_windows::capture_windows;

pub static APPSHOT_SHORTCUT_STR: std::sync::Mutex<String> = std::sync::Mutex::new(String::new());
pub static VOICE_PTT_SHORTCUT_STR: std::sync::Mutex<String> = std::sync::Mutex::new(String::new());

pub fn handle_voice_ptt_start(app: &AppHandle) {
    let _ = app.emit("voice-ptt-start", ());
    capture_screen_context_for_ptt(app);
}

fn capture_screen_context_for_ptt(app: &AppHandle) {
    let excluded_apps = load_excluded_apps(app);
    let app_handle = app.clone();

    std::thread::spawn(move || {
        let front_app_name = get_frontmost_app_name();

        if is_app_excluded(&front_app_name, &excluded_apps) {
            return;
        }

        let timestamp = current_timestamp_ms();

        #[cfg(target_os = "macos")]
        let (screenshot_b64, window_title, extracted_text, _, _selected) =
            capture_macos::capture_appshot_macos();

        #[cfg(target_os = "windows")]
        let (screenshot_b64, window_title, extracted_text, _, _selected) =
            capture_windows::capture_appshot_windows();

        #[cfg(not(any(target_os = "macos", target_os = "windows")))]
        let (screenshot_b64, window_title, extracted_text) =
            (String::new(), String::new(), String::new());

        let payload = serde_json::json!({
            "screenshot": screenshot_b64,
            "windowTitle": window_title,
            "extractedText": extracted_text,
            "timestamp": timestamp,
        });

        let _ = app_handle.emit("voice-ptt-context", payload);
    });
}

pub fn handle_voice_ptt_stop(app: &AppHandle) {
    let _ = app.emit("voice-ptt-stop", ());
}

pub fn handle_toggle_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.is_minimized().unwrap_or(false) {
            let _ = window.unminimize();
            let _ = window.set_focus();
        } else if window.is_visible().unwrap_or(false) {
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

pub fn force_capture(app: &AppHandle) {
    let app_handle = app.clone();
    std::thread::spawn(move || {
        do_capture_and_emit(&app_handle);
    });
}

fn do_capture_and_emit(app: &AppHandle) {
    let timestamp = current_timestamp_ms();

    #[cfg(target_os = "macos")]
    let (screenshot_b64, window_title, extracted_text, needs_permission, _selected) =
        capture_macos::capture_appshot_macos();

    #[cfg(target_os = "windows")]
    let (screenshot_b64, window_title, extracted_text, needs_permission, _selected) =
        capture_windows::capture_appshot_windows();

    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    let (screenshot_b64, window_title, extracted_text, needs_permission, _selected) = (
        String::new(),
        String::new(),
        String::new(),
        false,
        String::new(),
    );

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
