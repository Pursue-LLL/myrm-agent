//! 系统托盘初始化与状态管理
//!
//! [INPUT]
//! - super::lifecycle::graceful_shutdown (POS: 优雅停机)
//! - 前端 useTrayEvents.ts 监听 tray:new_chat / tray:settings / tray:workspace 事件
//!
//! [OUTPUT]
//! - setup_tray: 初始化 Tray 菜单（Show / New Chat / Settings / Workspace / Quit）
//! - set_tray_status: IPC 命令，前端同步 Agent 运行状态与 i18n tooltip 到托盘
//! - update_native_tray_status: Rust 侧托盘 error/idle 状态（watchdog、启动失败）
//!
//! [POS]
//! 系统托盘模块。提供 Tray 菜单快捷操作和动态状态 tooltip。

use tauri::image::Image;
use tauri::{AppHandle, Emitter, Manager};
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};

fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        #[cfg(target_os = "macos")]
        {
            let _ = app.set_activation_policy(tauri::ActivationPolicy::Regular);
        }
        if window.is_minimized().unwrap_or(false) {
            let _ = window.unminimize();
        }
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn show_and_navigate(app: &AppHandle, event_name: &str) {
    if let Some(window) = app.get_webview_window("main") {
        #[cfg(target_os = "macos")]
        {
            let _ = app.set_activation_policy(tauri::ActivationPolicy::Regular);
        }
        if window.is_minimized().unwrap_or(false) {
            let _ = window.unminimize();
        }
        let _ = window.show();
        let _ = window.set_focus();
        let _ = window.emit(event_name, ());
    }
}

fn load_tray_icon() -> Result<Image<'static>, Box<dyn std::error::Error>> {
    Ok(Image::from_bytes(include_bytes!("../../icons/tray_icon@2x.png"))?)
}

pub fn load_tray_icon_for_status(status: &str) -> Result<Image<'static>, Box<dyn std::error::Error>> {
    match status {
        "busy" => Ok(Image::from_bytes(include_bytes!("../../icons/tray_icon_busy@2x.png"))?),
        "degraded" | "error" => Ok(Image::from_bytes(include_bytes!("../../icons/tray_icon_degraded@2x.png"))?),
        _ => load_tray_icon(),
    }
}

pub fn setup_tray(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let show_i = MenuItem::with_id(app, "show", "Show", true, None::<&str>)?;
    let new_chat_i = MenuItem::with_id(app, "new_chat", "New Chat", true, None::<&str>)?;
    let sep1 = PredefinedMenuItem::separator(app)?;
    let settings_i = MenuItem::with_id(app, "settings", "Settings", true, None::<&str>)?;
    let workspace_i = MenuItem::with_id(app, "workspace", "Workspace", true, None::<&str>)?;
    let sep2 = PredefinedMenuItem::separator(app)?;
    let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;

    let menu = Menu::with_items(app, &[
        &show_i, &new_chat_i, &sep1,
        &settings_i, &workspace_i, &sep2,
        &quit_i,
    ])?;

    let mut builder = TrayIconBuilder::with_id("main")
        .icon(load_tray_icon()?)
        .menu(&menu)
        .show_menu_on_left_click(false);

    #[cfg(target_os = "macos")]
    {
        builder = builder.icon_as_template(true);
    }

    builder
        .on_menu_event(|app, event| match event.id.as_ref() {
            "quit" => {
                let app_handle = app.clone();
                tauri::async_runtime::spawn(async move {
                    super::lifecycle::graceful_shutdown(app_handle.clone()).await;
                    app_handle.exit(0);
                });
            }
            "show" => show_main_window(app),
            "new_chat" => show_and_navigate(app, "tray:new_chat"),
            "settings" => show_and_navigate(app, "tray:settings"),
            "workspace" => show_and_navigate(app, "tray:workspace"),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event {
                show_main_window(tray.app_handle());
            }
        })
        .build(app)?;

    Ok(())
}

/// 根据 Agent 运行状态更新系统托盘图标与 tooltip。
/// 前端 `useTrayStatus` 在全局 liveness 状态变化时调用此命令。
#[tauri::command]
pub fn set_tray_status(app: AppHandle, status: String, tooltip: Option<String>) -> Result<(), String> {
    if let Some(tray) = app.tray_by_id("main") {
        let text = tooltip.unwrap_or_else(|| default_tray_tooltip(&status));
        tray.set_tooltip(Some(text))
            .map_err(|e| format!("Failed to set tray tooltip: {e}"))?;

        if let Ok(icon) = load_tray_icon_for_status(&status) {
            let _ = tray.set_icon(Some(icon));
        }
    }
    Ok(())
}

fn default_tray_tooltip(status: &str) -> String {
    match status {
        "busy" => "MyrmAgent - Running...".into(),
        "error" => "MyrmAgent - Error".into(),
        "idle" => "MyrmAgent - Idle".into(),
        _ => "MyrmAgent".into(),
    }
}

/// Update tray icon and tooltip from Rust (watchdog, sidecar startup failures).
pub fn update_native_tray_status(app: &AppHandle, status: &str, tooltip: &str) {
    let Some(tray) = app.tray_by_id("main") else {
        return;
    };
    let _ = tray.set_tooltip(Some(tooltip));

    if let Ok(icon) = load_tray_icon_for_status(status) {
        let _ = tray.set_icon(Some(icon));
    }
}
