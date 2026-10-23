//! Tauri 应用构建与运行入口。
//!
//! [INPUT]
//! - commands / config / runtime / utils 各模块 (POS: IPC 与 Sidecar 编排)
//! - chain (POS: 官方插件与窗口页自定义协议的 Builder 片段)
//! - tauri::Builder 插件 (single-instance, window-state, global-shortcut)
//!
//! [OUTPUT]
//! - run(): 桌面应用主循环、统一 IPC sender gate、generate_handler IPC 注册表
//!
//! [POS]
//! Tauri Builder 组装层唯一入口；main.rs 仅委托本模块。

pub(crate) mod chain;
pub(crate) mod lifecycle;
mod linux_gpu;
mod menu;
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

    let builder = tauri::Builder::default()
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
        .plugin(tauri_plugin_window_state::Builder::new().build());

    chain::with_page_protocols(chain::with_product_plugins(builder))
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, shortcut, event| {
                    shortcut_handler::handle_global_shortcut(app, shortcut, event);
                })
                .build(),
        )
        .setup(setup::on_setup)
        .on_page_load(|_webview, payload| {
            println!("DESKTOP_PAGE_LOAD: {}", payload.url());
        })
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
            tauri::RunEvent::ExitRequested { api, code, .. } => {
                if lifecycle::is_shutdown_completed() {
                    println!("✅ Graceful shutdown completed, allowing application exit.");
                    return;
                }
                if lifecycle::is_shutdown_initiated() {
                    api.prevent_exit();
                    return;
                }
                println!("🛑 Exit requested (e.g., Cmd+Q), initiating graceful shutdown...");
                api.prevent_exit();
                let app_handle_clone = app_handle.clone();
                let exit_code = code.unwrap_or(0);
                tauri::async_runtime::spawn(async move {
                    lifecycle::graceful_shutdown(app_handle_clone).await;
                    tokio::time::sleep(std::time::Duration::from_millis(200)).await;
                    std::process::exit(exit_code);
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
