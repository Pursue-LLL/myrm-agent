//! Tauri 应用构建与运行入口。
//!
//! [INPUT]
//! - commands / config / runtime / utils 各模块 (POS: IPC 与 Sidecar 编排)
//! - tauri::Builder 插件链 (shell, updater, global-shortcut, window-state 等)
//!
//! [OUTPUT]
//! - run(): 桌面应用主循环、统一 IPC sender gate、generate_handler IPC 注册表
//!
//! [POS]
//! Tauri Builder 组装层唯一入口；main.rs 仅委托本模块。

mod lifecycle;
mod linux_gpu;
mod setup;
mod shortcut_handler;
mod tray;

include!("../../command_registry_macro.in");

pub(crate) use tray::update_native_tray_status;

use crate::runtime;

macro_rules! command_handler_list {
    ($(($name:literal, $handler:path)),* $(,)?) => {
        tauri::generate_handler![$($handler),*]
    };
}

#[tauri::command]
async fn fix_quarantine_with_auth() -> Result<bool, String> {
    crate::utils::auth::fix_quarantine_with_auth()
}

#[tauri::command]
async fn inline_paste_back(app: tauri::AppHandle, content: String) -> Result<(), String> {
    runtime::paste_back(&app, content)
}

pub fn run() {
    linux_gpu::apply_linux_gpu_workarounds();

    let invoke_handler: Box<dyn Fn(tauri::ipc::Invoke) -> bool + Send + Sync> =
        Box::new(tauri_command_registry!(command_handler_list));

    tauri::Builder::default()
        .plugin(tauri_plugin_window_state::Builder::new().build())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(
            tauri_plugin_autostart::Builder::new()
                .args(["--auto-launched"])
                .build(),
        )
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, shortcut, event| {
                    shortcut_handler::handle_global_shortcut(app, shortcut, event);
                })
                .build(),
        )
        .setup(|app| setup::on_setup(app))
        .on_window_event(|window, event| setup::on_window_event(window, event))
        .invoke_handler(move |invoke: tauri::ipc::Invoke| {
            match crate::ipc_security::authorize_invoke(&invoke) {
                Ok(()) => invoke_handler(invoke),
                Err(denied) => {
                    crate::ipc_security::handle_denied_invoke(invoke, denied);
                    true
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::ExitRequested { api, .. } = event {
                println!("🛑 Exit requested (e.g., Cmd+Q), initiating graceful shutdown...");
                api.prevent_exit();
                let app_handle_clone = app_handle.clone();
                tauri::async_runtime::spawn(async move {
                    lifecycle::graceful_shutdown(app_handle_clone.clone()).await;
                    app_handle_clone.exit(0);
                });
            }
        });
}
