//! Tauri 应用构建与运行入口。

mod linux_gpu;
mod setup;
mod shortcut_handler;

use crate::lifecycle;
use crate::runtime;

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
        .invoke_handler(tauri::generate_handler![
            fix_quarantine_with_auth,
            inline_paste_back,
            crate::commands::config::load_system_config,
            crate::commands::config::save_system_config,
            crate::commands::config::reset_system_config,
            crate::commands::config::get_current_mode,
            crate::commands::config::restart_app,
            crate::commands::config::get_local_ip,
            crate::runtime::setup_token::get_setup_token,
            crate::commands::config::update_global_shortcut,
            crate::runtime::python_backend::start_backend,
            crate::runtime::python_backend::stop_backend,
            crate::runtime::python_backend::check_backend_health,
            crate::runtime::python_backend::get_backend_status,
            crate::runtime::nextjs_frontend::stop_frontend,
            crate::commands::agent::detect_agents,
            crate::commands::agent::list_agent_adapters,
            crate::commands::agent::get_agent_sidecar_status,
            crate::commands::agent::session::create_agent_session,
            crate::commands::agent::session::list_agent_sessions,
            crate::commands::agent::session::get_agent_session,
            crate::commands::agent::session::delete_agent_session,
            crate::commands::agent::session::resume_agent_session,
            crate::commands::agent::message::send_agent_message,
            crate::commands::agent::message::stop_agent_message,
            crate::commands::agent::permission::respond_agent_permission,
            crate::commands::agent::permission::get_permission_mode,
            crate::commands::agent::permission::set_permission_mode,
            crate::commands::agent::permission::cycle_permission_mode,
            crate::commands::power::power_lock_acquire,
            crate::commands::power::power_lock_release,
            crate::commands::power::power_lock_status,
            crate::commands::screen_lock::screen_is_locked,
            crate::commands::screen_lock::screen_unlock,
            crate::commands::screen_lock::screen_relock,
            crate::commands::screen_lock::screen_lock_store_password,
            crate::commands::screen_lock::screen_lock_has_password,
            crate::commands::screen_lock::screen_lock_delete_password,
            crate::commands::screen_lock::screen_lock_platform_support,
            crate::commands::visual_approval_overlay::show_visual_approval_overlay,
            crate::commands::visual_approval_overlay::hide_visual_approval_overlay,
            crate::commands::pet_overlay::show_pet_overlay,
            crate::commands::pet_overlay::hide_pet_overlay,
            crate::commands::pet_overlay::pet_overlay_set_row,
            crate::commands::session_window::open_session_window,
            crate::commands::session_window::close_session_window,
            crate::commands::config::force_appshot_capture,
            crate::commands::config::migrate_data_dir,
            crate::commands::recovery::export_local_sqlite,
            crate::commands::recovery::reveal_app_folder,
            crate::tray::set_tray_status
        ])
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
