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
//! （shell、dialog、autostart、global-shortcut 等）、注册 IPC 命令、
//! 管理 Python/Agent Sidecar 进程生命周期。支持 CLI 可视化工具、
//! WebUI 远程访问模式和开机自启（tray-only daemon）。
//! Linux 平台下自动检测 NVIDIA GPU + Wayland 并应用 WebKitGTK 兼容性修复。

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
    start_backend_with_config, stop_backend, stop_frontend, APPSHOT_SHORTCUT_STR,
    INLINE_INPUT_SHORTCUT_STR, NextJSFrontend, PythonBackend, SetupTokenState,
    VOICE_PTT_SHORTCUT_STR,
};
pub use runtime::{
    handle_appshot_shortcut, handle_inline_input_shortcut, handle_toggle_window,
    handle_voice_ptt_start, handle_voice_ptt_stop,
};

/// WebKitGTK + NVIDIA GPU + Wayland = blank window / Error 71 crash.
/// Auto-detect and apply env-var workarounds before Tauri touches the display.
/// See: <https://v2.tauri.app/develop/debug/linux-graphics/>
#[cfg(target_os = "linux")]
fn apply_linux_gpu_workarounds() {
    use std::env;
    use std::path::Path;

    if env::var("MYRM_FORCE_GPU_ACCEL").as_deref() == Ok("1") {
        return;
    }
    if env::var("WEBKIT_DISABLE_DMABUF_RENDERER").is_ok() {
        return;
    }

    let is_nvidia = Path::new("/proc/driver/nvidia/version").exists();
    let is_wayland = env::var("WAYLAND_DISPLAY").is_ok()
        || env::var("XDG_SESSION_TYPE").as_deref() == Ok("wayland");

    if is_nvidia && is_wayland {
        env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "1");
        env::set_var("__NV_DISABLE_EXPLICIT_SYNC", "1");
        eprintln!(
            "⚠️ NVIDIA + Wayland detected — applied GPU compatibility workaround \
             (WEBKIT_DISABLE_DMABUF_RENDERER=1). Override with MYRM_FORCE_GPU_ACCEL=1"
        );
    } else if is_nvidia {
        env::set_var("__NV_DISABLE_EXPLICIT_SYNC", "1");
        eprintln!("ℹ️ NVIDIA GPU detected — applied __NV_DISABLE_EXPLICIT_SYNC=1");
    }
}

#[tauri::command]
async fn fix_quarantine_with_auth() -> Result<bool, String> {
    utils::auth::fix_quarantine_with_auth()
}

/// Inline Input: 将 AI 生成内容粘贴回触发时的原应用
#[tauri::command]
async fn inline_paste_back(app: tauri::AppHandle, content: String) -> Result<(), String> {
    runtime::paste_back(&app, content)
}

fn main() {
    #[cfg(target_os = "linux")]
    apply_linux_gpu_workarounds();

    tauri::Builder::default()
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
                    use tauri_plugin_global_shortcut::ShortcutState;

                    let shortcut_str = format!("{shortcut}");

                    let is_voice_ptt = VOICE_PTT_SHORTCUT_STR
                        .lock()
                        .map_or(false, |saved| !saved.is_empty() && *saved == shortcut_str);

                    if is_voice_ptt {
                        match event.state {
                            ShortcutState::Pressed => handle_voice_ptt_start(app),
                            ShortcutState::Released => handle_voice_ptt_stop(app),
                        }
                        return;
                    }

                    if event.state != ShortcutState::Pressed {
                        return;
                    }

                    let is_appshot = APPSHOT_SHORTCUT_STR
                        .lock()
                        .map_or(false, |saved| *saved == shortcut_str);

                    let is_inline_input = INLINE_INPUT_SHORTCUT_STR
                        .lock()
                        .map_or(false, |saved| !saved.is_empty() && *saved == shortcut_str);

                    if is_appshot {
                        handle_appshot_shortcut(app);
                    } else if is_inline_input {
                        handle_inline_input_shortcut(app);
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

            if !system_config.voice_ptt_shortcut.is_empty() {
                use std::str::FromStr;
                if let Ok(shortcut) =
                    tauri_plugin_global_shortcut::Shortcut::from_str(&system_config.voice_ptt_shortcut)
                {
                    if let Ok(mut guard) = VOICE_PTT_SHORTCUT_STR.lock() {
                        *guard = format!("{shortcut}");
                    }
                    if let Err(e) = app.global_shortcut().register(shortcut) {
                        println!("⚠️ Failed to register voice PTT shortcut: {}", e);
                    } else {
                        println!(
                            "🎤 Voice PTT shortcut registered: {}",
                            system_config.voice_ptt_shortcut
                        );
                    }
                } else {
                    println!(
                        "⚠️ Invalid voice PTT shortcut format: {}",
                        system_config.voice_ptt_shortcut
                    );
                }
            }

            if !system_config.inline_input_shortcut.is_empty() {
                use std::str::FromStr;
                if let Ok(shortcut) =
                    tauri_plugin_global_shortcut::Shortcut::from_str(&system_config.inline_input_shortcut)
                {
                    if let Ok(mut guard) = INLINE_INPUT_SHORTCUT_STR.lock() {
                        *guard = format!("{shortcut}");
                    }
                    if let Err(e) = app.global_shortcut().register(shortcut) {
                        println!("⚠️ Failed to register inline input shortcut: {}", e);
                    } else {
                        println!(
                            "✏️  Inline input shortcut registered: {}",
                            system_config.inline_input_shortcut
                        );
                    }
                } else {
                    println!(
                        "⚠️ Invalid inline input shortcut format: {}",
                        system_config.inline_input_shortcut
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

            let is_auto_launched = std::env::args().any(|a| a == "--auto-launched");
            if is_auto_launched {
                println!("🔄 Auto-launched at login, running in background (tray only)");
            }

            if system_config.auto_launch_at_login {
                use tauri_plugin_autostart::ManagerExt;
                if let Ok(autostart) = app.autolaunch().is_enabled() {
                    if !autostart {
                        let _ = app.autolaunch().enable();
                        println!("✅ Auto-launch enabled at login");
                    }
                }
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
                let backend_port = BackendConfig::from_system_config(&system_config_clone).port;
                match start_backend_with_config(
                    app_handle.clone(),
                    backend_state,
                    backend_config,
                )
                .await
                {
                    Ok(msg) => {
                        println!("✅ {}", msg);
                        let handle = runtime::watchdog::spawn_watchdog(&app_handle, backend_port);
                        app_handle.manage(handle);
                    }
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

            if let Some(window) = app.get_webview_window("main") {
                if is_auto_launched {
                    #[cfg(target_os = "macos")]
                    {
                        let _ = app
                            .handle()
                            .set_activation_policy(tauri::ActivationPolicy::Accessory);
                    }
                } else {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }

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
            open_session_window,
            close_session_window,
            force_appshot_capture,
            inline_paste_back,
            commands::config::migrate_data_dir,
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
