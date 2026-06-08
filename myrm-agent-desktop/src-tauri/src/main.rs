//! Tauri 桌面应用入口
//!
//! ⚠️ 自更新提示：一旦我被更新，务必更新：
//! 1. 本文件的 INPUT/OUTPUT/POS 注释
//! 2. 所属文件夹的 _ARCH.md
//!
//! [INPUT]
//! - cli_agent_types: CLI 可视化共享类型
//! - commands: Tauri IPC 命令实现
//! - config: 配置管理（后端地址、WebUI 模式）
//! - runtime: Python/Next.js Sidecar、Appshot、Setup Token
//! - permissions: 权限管理（Explore/Ask/Auto）
//! - sessions: CLI 会话生命周期管理
//! - lifecycle: 优雅停机与生命周期管理
//! - tray: 系统托盘与状态管理
//!
//! [OUTPUT]
//! - Tauri 应用实例
//! - IPC 命令注册（start_backend, stop_backend, check_backend_health 等）
//! - Agent 系统命令（create_session, send_message 等）
//!
//! [POS]
//! Tauri 桌面应用的入口点。负责初始化 Tauri 应用、注册插件
//! （shell、dialog）、注册 IPC 命令、管理 Python/Agent Sidecar
//! 进程生命周期。支持 CLI 可视化工具和 WebUI 远程访问模式。

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod cli_agent_types;
mod commands;
mod config;
mod lifecycle;
mod permissions;
mod runtime;
mod sessions;
mod sidecar;
mod tray;
mod tunnel;
mod utils;

use std::sync::{Arc, Mutex};
use std::time::Duration;

use tauri::{Emitter, Manager};
use tauri_plugin_global_shortcut::GlobalShortcutExt;

use commands::agent::AgentSystemState;
use commands::*;
use config::{BackendConfig, ConfigManager, FrontendConfig};

pub use runtime::{
    check_backend_health, get_backend_status, get_setup_token, start_backend,
    start_backend_with_config, stop_backend, stop_frontend, APPSHOT_SHORTCUT_STR, NextJSFrontend,
    PythonBackend, SetupTokenState,
};
pub use runtime::{handle_appshot_shortcut, handle_toggle_window};

#[tauri::command]
async fn fix_quarantine_with_auth() -> Result<bool, String> {
    utils::auth::fix_quarantine_with_auth()
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, shortcut, event| {
                    if event.state != tauri_plugin_global_shortcut::ShortcutState::Pressed {
                        return;
                    }

                    let shortcut_str = format!("{shortcut}");
                    let is_appshot = APPSHOT_SHORTCUT_STR
                        .lock()
                        .map_or(false, |saved| *saved == shortcut_str);

                    if is_appshot {
                        handle_appshot_shortcut(app);
                    } else {
                        handle_toggle_window(app);
                    }
                })
                .build(),
        )
        .setup(|app| {
            println!("🚀 Initializing MyrmAgent...");

            match utils::updater_safety::check_updater_pubkey_safety() {
                utils::updater_safety::UpdaterPubkeySafety::Safe => {
                    println!("🔐 Updater pubkey verified, OTA channel is secure");
                }
                utils::updater_safety::UpdaterPubkeySafety::PlaceholderDev => {}
                utils::updater_safety::UpdaterPubkeySafety::PlaceholderProd => {
                    eprintln!("🚫 Production OTA disabled due to placeholder pubkey");
                }
                utils::updater_safety::UpdaterPubkeySafety::Invalid(reason) => {
                    eprintln!("🚫 Updater config invalid: {reason}");
                }
            }

            let app_handle = app.handle().clone();
            std::thread::spawn(move || {
                if utils::quarantine::scan_and_silent_heal() {
                    println!("⚠️ 检测到 com.apple.quarantine 属性且静默移除失败，需要提权修复");
                    let _ = app_handle.emit("quarantine-detected", ());
                } else {
                    println!("✅ 隔离属性检测通过或已静默修复");
                }
            });

            let config_manager = ConfigManager::new(app.handle())
                .expect("Failed to initialize config manager");

            let system_config = config_manager.load();
            println!("📋 Loaded config: {:?}", system_config);

            if !system_config.global_shortcut.is_empty() {
                use std::str::FromStr;

                if let Ok(shortcut) =
                    tauri_plugin_global_shortcut::Shortcut::from_str(&system_config.global_shortcut)
                {
                    if let Err(e) = app.global_shortcut().register(shortcut) {
                        println!("⚠️ Failed to register global shortcut: {}", e);
                    } else {
                        println!(
                            "⌨️  Global shortcut registered: {}",
                            system_config.global_shortcut
                        );
                    }
                } else {
                    println!(
                        "⚠️ Invalid global shortcut format: {}",
                        system_config.global_shortcut
                    );
                }
            }

            if !system_config.appshot_shortcut.is_empty() {
                use std::str::FromStr;
                if let Ok(shortcut) =
                    tauri_plugin_global_shortcut::Shortcut::from_str(&system_config.appshot_shortcut)
                {
                    if let Ok(mut guard) = APPSHOT_SHORTCUT_STR.lock() {
                        *guard = format!("{shortcut}");
                    }
                    if let Err(e) = app.global_shortcut().register(shortcut) {
                        println!("Failed to register appshot shortcut: {}", e);
                    } else {
                        println!(
                            "Appshot shortcut registered: {}",
                            system_config.appshot_shortcut
                        );
                    }
                } else {
                    println!(
                        "Invalid appshot shortcut format: {}",
                        system_config.appshot_shortcut
                    );
                }
            }

            if system_config.enable_webui_mode {
                if system_config.enable_remote_access {
                    println!("🌐 Running in WebUI Remote mode");
                } else {
                    println!("🔒 Running in WebUI Local mode");
                }
            } else {
                println!("🖥️  Running in Desktop mode");
            }

            app.manage(config_manager);

            app.manage(SetupTokenState {
                token: Mutex::new(None),
            });

            app.manage(commands::power::PowerState::new());
            app.manage(commands::screen_lock::ScreenLockState::new());

            let backend = PythonBackend::new();
            app.manage(backend);

            let frontend = NextJSFrontend::new();
            app.manage(frontend);

            if let Err(e) = tray::setup_tray(&app.handle().clone()) {
                println!("⚠️ Failed to setup tray: {e}");
            }

            let sidecar_path = runtime::resolve_agent_runner_path(&app.handle().clone());
            println!("📦 Agent sidecar path: {}", sidecar_path);

            let app_data_dir = app.path().app_data_dir().ok();
            if let Some(ref dir) = app_data_dir {
                println!("📂 App data dir: {:?}", dir);
            }

            let agent_system = Arc::new(AgentSystemState::new(sidecar_path, app_data_dir));
            runtime::bootstrap_agent_runner(agent_system.clone(), &app.handle().clone());

            app.manage(agent_system);
            println!("🤖 Agent system initialized");

            let backend_config = BackendConfig::from_system_config(&system_config);

            let app_handle = app.handle().clone();
            let system_config_clone = system_config.clone();
            tauri::async_runtime::spawn(async move {
                tokio::time::sleep(Duration::from_millis(500)).await;

                let backend_state = app_handle.state::<PythonBackend>();
                match start_backend_with_config(
                    app_handle.clone(),
                    backend_state,
                    backend_config,
                )
                .await
                {
                    Ok(msg) => println!("✅ {}", msg),
                    Err(e) => eprintln!("❌ Failed to auto-start backend: {}", e),
                }

                if system_config_clone.enable_webui_mode {
                    println!("🌐 WebUI mode enabled, starting Next.js Server...");
                    tokio::time::sleep(Duration::from_millis(1000)).await;

                    let frontend_config =
                        FrontendConfig::from_system_config(&system_config_clone);
                    let frontend_state = app_handle.state::<NextJSFrontend>();

                    match runtime::start_frontend(
                        app_handle.clone(),
                        frontend_state,
                        frontend_config,
                    )
                    .await
                    {
                        Ok(msg) => println!("✅ {}", msg),
                        Err(e) => eprintln!("❌ Failed to auto-start frontend: {}", e),
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            match event {
                tauri::WindowEvent::CloseRequested { api, .. } => {
                    let config_manager = window.app_handle().state::<ConfigManager>();
                    let config = config_manager.load();

                    if config.close_to_tray {
                        let _ = window.hide();
                        api.prevent_close();

                        #[cfg(target_os = "macos")]
                        {
                            let _ = window
                                .app_handle()
                                .set_activation_policy(tauri::ActivationPolicy::Accessory);
                        }
                    }
                }
                tauri::WindowEvent::Destroyed => {
                    let app_handle = window.app_handle().clone();
                    tauri::async_runtime::spawn(async move {
                        lifecycle::graceful_shutdown(app_handle).await;
                    });
                }
                _ => {}
            }
        })
        .invoke_handler(tauri::generate_handler![
            fix_quarantine_with_auth,
            load_system_config,
            save_system_config,
            reset_system_config,
            get_current_mode,
            restart_app,
            get_local_ip,
            get_setup_token,
            update_global_shortcut,
            start_backend,
            stop_backend,
            check_backend_health,
            get_backend_status,
            stop_frontend,
            detect_agents,
            list_agent_adapters,
            get_agent_sidecar_status,
            create_agent_session,
            list_agent_sessions,
            get_agent_session,
            delete_agent_session,
            resume_agent_session,
            send_agent_message,
            stop_agent_message,
            respond_agent_permission,
            get_permission_mode,
            set_permission_mode,
            cycle_permission_mode,
            power_lock_acquire,
            power_lock_release,
            power_lock_status,
            screen_is_locked,
            screen_unlock,
            screen_relock,
            screen_lock_store_password,
            screen_lock_has_password,
            screen_lock_delete_password,
            screen_lock_platform_support,
            show_visual_approval_overlay,
            hide_visual_approval_overlay,
            show_pet_overlay,
            hide_pet_overlay,
            pet_overlay_set_row,
            tray::set_tray_status
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
