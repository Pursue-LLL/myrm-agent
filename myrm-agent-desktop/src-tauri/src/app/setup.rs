//! Tauri `setup` 钩子：配置管理、快捷键注册、Sidecar 自启动（Python + Next 始终）。

use std::sync::{Arc, Mutex};
use std::time::Duration;

use tauri::{Emitter, Manager};
use tauri_plugin_global_shortcut::GlobalShortcutExt;

use crate::commands::agent::AgentSystemState;
use crate::config::{BackendConfig, ConfigManager, FrontendConfig};
use crate::runtime::{
    bootstrap_agent_runner, resolve_agent_runner_path, start_backend_with_config, start_frontend,
    APPSHOT_SHORTCUT_STR, INLINE_INPUT_SHORTCUT_STR, NextJSFrontend, PythonBackend,
    SetupTokenState, VOICE_PTT_SHORTCUT_STR,
};
use crate::{commands, lifecycle, runtime, tray, utils};

pub fn on_setup(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
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

    let config_manager = ConfigManager::new(app.handle()).expect("Failed to initialize config manager");

    let system_config = config_manager.load();
    println!("📋 Loaded config: {:?}", system_config);

    register_shortcut_from_config(app, &system_config.global_shortcut, "Global", None)?;
    register_shortcut_from_config(
        app,
        &system_config.appshot_shortcut,
        "Appshot",
        Some(&APPSHOT_SHORTCUT_STR),
    )?;
    register_shortcut_from_config(
        app,
        &system_config.voice_ptt_shortcut,
        "Voice PTT",
        Some(&VOICE_PTT_SHORTCUT_STR),
    )?;
    register_shortcut_from_config(
        app,
        &system_config.inline_input_shortcut,
        "Inline input",
        Some(&INLINE_INPUT_SHORTCUT_STR),
    )?;

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

    app.manage(PythonBackend::new());
    app.manage(NextJSFrontend::new());

    if let Err(e) = tray::setup_tray(&app.handle().clone()) {
        println!("⚠️ Failed to setup tray: {e}");
    }

    let sidecar_path = resolve_agent_runner_path(&app.handle().clone());
    println!("📦 Agent sidecar path: {}", sidecar_path);

    let app_data_dir = app.path().app_data_dir().ok();
    if let Some(ref dir) = app_data_dir {
        println!("📂 App data dir: {:?}", dir);
    }

    let agent_system = Arc::new(AgentSystemState::new(sidecar_path, app_data_dir));
    bootstrap_agent_runner(agent_system.clone(), &app.handle().clone());

    app.manage(agent_system);
    println!("🤖 Agent system initialized");

    let backend_config = BackendConfig::from_system_config(&system_config);

    let app_handle = app.handle().clone();
    let system_config_clone = system_config.clone();
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(Duration::from_millis(500)).await;

        let backend_state = app_handle.state::<PythonBackend>();
        let backend_port = BackendConfig::from_system_config(&system_config_clone).port;
        match start_backend_with_config(app_handle.clone(), backend_state, backend_config).await {
            Ok(msg) => {
                println!("✅ {}", msg);
                let handle = runtime::watchdog::spawn_watchdog(&app_handle, backend_port);
                app_handle.manage(handle);
            }
            Err(e) => {
                eprintln!("❌ Failed to auto-start backend: {}", e);
                let tooltip = "MyrmAgent - Backend failed to start. Restart the app or check Settings.";
                tray::update_native_tray_status(&app_handle, "error", tooltip);
                let _ = app_handle.emit("backend-start-failed", e.clone());
            }
        }

        // Release WebView loads frontend-shell → polls Next standalone; always start Next.
        // enable_webui_mode only affects backend bind/port (see BackendConfig), not UI startup.
        println!("🌐 Starting Next.js Server...");
        tokio::time::sleep(Duration::from_millis(1000)).await;

        let frontend_config = FrontendConfig::from_system_config(&system_config_clone);
        let frontend_state = app_handle.state::<NextJSFrontend>();

        match start_frontend(app_handle.clone(), frontend_state, frontend_config).await {
            Ok(msg) => println!("✅ {}", msg),
            Err(e) => {
                eprintln!("❌ Failed to auto-start frontend: {}", e);
                let tooltip = format!("MyrmAgent - UI failed to start. Restart the app or change the WebUI port in Settings.");
                tray::update_native_tray_status(&app_handle, "error", &tooltip);
                let _ = app_handle.emit("frontend-start-failed", e.clone());
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
}

fn register_shortcut_from_config(
    app: &mut tauri::App,
    shortcut_config: &str,
    label: &str,
    store: Option<&std::sync::Mutex<String>>,
) -> Result<(), Box<dyn std::error::Error>> {
    if shortcut_config.is_empty() {
        return Ok(());
    }
    use std::str::FromStr;
    match tauri_plugin_global_shortcut::Shortcut::from_str(shortcut_config) {
        Ok(shortcut) => {
            if let Some(mutex) = store {
                if let Ok(mut guard) = mutex.lock() {
                    *guard = format!("{shortcut}");
                }
            }
            if let Err(e) = app.global_shortcut().register(shortcut) {
                println!("⚠️ Failed to register {label} shortcut: {}", e);
            } else {
                println!("{label} shortcut registered: {shortcut_config}");
            }
        }
        Err(_) => {
            println!("⚠️ Invalid {label} shortcut format: {shortcut_config}");
        }
    }
    Ok(())
}

pub fn on_window_event(window: &tauri::Window, event: &tauri::WindowEvent) {
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
}
