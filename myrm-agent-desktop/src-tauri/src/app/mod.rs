//! Tauri 应用构建与运行入口。
//!
//! [INPUT]
//! - commands / config / runtime / utils 各模块 (POS: IPC 与 Sidecar 编排)
//! - tauri::Builder 插件链 (shell, updater, global-shortcut, window-state 等)
//!
//! [OUTPUT]
//! - run(): 桌面应用主循环、统一 IPC sender gate、generate_handler IPC 注册表、帷幕看板与审批高亮的自定义协议注册
//!
//! [POS]
//! Tauri Builder 组装层唯一入口；main.rs 仅委托本模块。

pub(crate) mod lifecycle;
mod linux_gpu;
mod menu;
mod setup;
mod shortcut_handler;
mod tray;

include!("../../command_registry_macro.in");

pub(crate) use tray::update_native_tray_status;

use crate::commands::privacy_curtain_page as curtain_page;
use crate::commands::visual_approval_overlay_page as overlay_page;
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
        // 必须先于 deep-link 插件注册：Windows/Linux 热启动时深链以新进程 argv 到达，
        // single-instance 的 `deep-link` 特性负责把它转交给已运行实例的 deep-link 插件。
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            use tauri::Manager;
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_window_state::Builder::new().build())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
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
        // 窗口页面经自定义协议提供：data: URL 在本应用被 tauri 拒绝，且页内 IPC 属 Remote 来源。
        .register_uri_scheme_protocol(curtain_page::SCHEME, |_ctx, _request| {
            curtain_page::response()
        })
        .register_uri_scheme_protocol(overlay_page::SCHEME, |_ctx, request| {
            overlay_page::response(&request)
        })
        .setup(setup::on_setup)
        .on_window_event(setup::on_window_event)
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
        .run(|app_handle, event| match event {
            tauri::RunEvent::Opened { urls } => {
                runtime::handle_open_urls(app_handle, urls);
            }
            tauri::RunEvent::ExitRequested { api, .. } => {
                println!("🛑 Exit requested (e.g., Cmd+Q), initiating graceful shutdown...");
                api.prevent_exit();
                let app_handle_clone = app_handle.clone();
                tauri::async_runtime::spawn(async move {
                    lifecycle::graceful_shutdown(app_handle_clone.clone()).await;
                    app_handle_clone.exit(0);
                });
            }
            _ => {}
        });
}

#[cfg(test)]
mod tests {
    const CARGO_MANIFEST: &str = include_str!("../../Cargo.toml");

    /// Windows/Linux 热启动时深链以新进程 argv 到达：缺了 `deep-link` 特性，
    /// 单实例回调只会聚焦窗口，OAuth 回跳等深链被静默丢弃。
    #[test]
    fn single_instance_forwards_deep_links_to_the_running_instance() {
        let line = CARGO_MANIFEST
            .lines()
            .find(|l| l.trim_start().starts_with("tauri-plugin-single-instance"))
            .expect("single-instance dependency must be declared");
        assert!(
            line.contains("\"deep-link\""),
            "single-instance must enable the deep-link feature: {line}"
        );
    }
}
