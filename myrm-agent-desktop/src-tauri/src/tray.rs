//! 系统托盘初始化与状态管理
//!
//! [INPUT]
//! - lifecycle::graceful_shutdown (POS: 优雅停机)
//! - 前端 useTrayEvents.ts 监听 tray:new_chat / tray:settings / tray:workspace 事件
//!
//! [OUTPUT]
//! - setup_tray: 初始化 Tray 菜单（Show / New Chat / Settings / Workspace / Quit）
//! - set_tray_status: IPC 命令，前端同步 Agent 运行状态到 tooltip
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
    Ok(Image::from_bytes(include_bytes!("../icons/tray_icon@2x.png"))?)
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
                    crate::lifecycle::graceful_shutdown(app_handle.clone()).await;
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

/// 根据 Agent 运行状态更新系统托盘 tooltip。
/// 前端 useTrayStatus hook 在 loading 状态变化时调用此命令。
#[tauri::command]
pub fn set_tray_status(app: AppHandle, status: String) -> Result<(), String> {
    if let Some(tray) = app.tray_by_id("main") {
        let tooltip = match status.as_str() {
            "busy" => "MyrmAgent - 任务执行中...",
            "error" => "MyrmAgent - 发生错误",
            "idle" => "MyrmAgent - 空闲",
            _ => "MyrmAgent",
        };
        tray.set_tooltip(Some(tooltip))
            .map_err(|e| format!("Failed to set tray tooltip: {e}"))?;
    }
    Ok(())
}
