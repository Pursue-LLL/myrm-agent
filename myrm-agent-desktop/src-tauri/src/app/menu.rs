//! 原生应用主菜单与 Edit 快捷键桥接。
//!
//! [INPUT]
//! - tauri::AppHandle / tauri::App (POS: Tauri Builder 运行时)
//!
//! [OUTPUT]
//! - setup_app_menu: 构建并注册包含 App Menu 与 Edit Menu 的系统级原生菜单
//!
//! [POS]
//! 桌面端原生菜单与快捷键桥接模块。
//! 确保在 macOS / Windows / Linux 的无边框沉浸式窗口中，
//! 系统剪贴板与编辑快捷键（Cmd/Ctrl+C/V/X/A/Z）通过操作系统 Responder Chain 100% 坚如磐石。

use tauri::menu::{Menu, PredefinedMenuItem, Submenu};
use tauri::{AppHandle, Manager};

pub fn setup_app_menu(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let app_name = &app.package_info().name;

    // 1. 构建 Edit 菜单（撤销/重做/剪切/拷贝/粘贴/全选）
    let edit_submenu = Submenu::with_items(
        app,
        "Edit",
        true,
        &[
            &PredefinedMenuItem::undo(app, Some("Undo"))?,
            &PredefinedMenuItem::redo(app, Some("Redo"))?,
            &PredefinedMenuItem::separator(app)?,
            &PredefinedMenuItem::cut(app, Some("Cut"))?,
            &PredefinedMenuItem::copy(app, Some("Copy"))?,
            &PredefinedMenuItem::paste(app, Some("Paste"))?,
            &PredefinedMenuItem::select_all(app, Some("Select All"))?,
        ],
    )?;

    // 2. 在 macOS 上构建标准 App 顶级子菜单
    #[cfg(target_os = "macos")]
    {
        let app_submenu = Submenu::with_items(
            app,
            app_name,
            true,
            &[
                &PredefinedMenuItem::about(app, Some(&format!("About {}", app_name)), None)?,
                &PredefinedMenuItem::separator(app)?,
                &PredefinedMenuItem::services(app, Some("Services"))?,
                &PredefinedMenuItem::separator(app)?,
                &PredefinedMenuItem::hide(app, Some(&format!("Hide {}", app_name)))?,
                &PredefinedMenuItem::hide_others(app, Some("Hide Others"))?,
                &PredefinedMenuItem::show_all(app, Some("Show All"))?,
                &PredefinedMenuItem::separator(app)?,
                &PredefinedMenuItem::quit(app, Some(&format!("Quit {}", app_name)))?,
            ],
        )?;

        let menu = Menu::with_items(app, &[&app_submenu, &edit_submenu])?;
        app.set_menu(menu)?;
    }

    // 3. 在 Windows / Linux 上注册静默主菜单，为全局 WebView 注册 Accelerators
    #[cfg(not(target_os = "macos"))]
    {
        let menu = Menu::with_items(app, &[&edit_submenu])?;
        app.set_menu(menu)?;
    }

    Ok(())
}
