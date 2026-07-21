//! 系统配置相关的 Tauri 命令
//!
//! 提供前端调用的系统配置相关命令。

use std::path::Path;

use crate::config::{ConfigManager, SystemConfig};
use crate::ipc_security::{self, SensitiveAction};
use tauri::State;

/// 加载系统配置
#[tauri::command]
pub async fn load_system_config(
    config_manager: State<'_, ConfigManager>,
) -> Result<SystemConfig, String> {
    Ok(config_manager.load())
}

/// 保存系统配置
#[tauri::command]
pub async fn save_system_config(
    app: tauri::AppHandle,
    config: SystemConfig,
    config_manager: State<'_, ConfigManager>,
) -> Result<(), String> {
    use tauri_plugin_autostart::ManagerExt;

    let should_enable = config.auto_launch_at_login;
    config_manager.save(&config)?;

    if let Ok(currently_enabled) = app.autolaunch().is_enabled() {
        if should_enable && !currently_enabled {
            let _ = app.autolaunch().enable();
            println!("✅ Auto-launch enabled");
        } else if !should_enable && currently_enabled {
            let _ = app.autolaunch().disable();
            println!("✅ Auto-launch disabled");
        }
    }

    Ok(())
}

/// 重置为默认配置（同步 OS 级别 autolaunch 状态）
#[tauri::command]
pub async fn reset_system_config(
    app: tauri::AppHandle,
    config_manager: State<'_, ConfigManager>,
) -> Result<SystemConfig, String> {
    config_manager.reset()?;
    let config = config_manager.load();

    use tauri_plugin_autostart::ManagerExt;
    if let Ok(currently_enabled) = app.autolaunch().is_enabled() {
        if config.auto_launch_at_login && !currently_enabled {
            let _ = app.autolaunch().enable();
        } else if !config.auto_launch_at_login && currently_enabled {
            let _ = app.autolaunch().disable();
        }
    }

    Ok(config)
}

/// 获取当前运行模式
#[tauri::command]
pub async fn get_current_mode(config_manager: State<'_, ConfigManager>) -> Result<String, String> {
    let config = config_manager.load();
    Ok(if config.enable_webui_mode {
        "webui".to_string()
    } else {
        "desktop".to_string()
    })
}

/// 重启应用
#[tauri::command]
pub async fn restart_app(app: tauri::AppHandle) -> Result<(), String> {
    println!("🔄 Restarting application...");
    app.restart();
}

/// 获取本地 IP 地址
#[tauri::command]
pub async fn get_local_ip() -> Result<String, String> {
    use local_ip_address::local_ip;

    match local_ip() {
        Ok(ip) => Ok(ip.to_string()),
        Err(e) => Err(format!("Failed to get local IP: {}", e)),
    }
}

/// 绕过隐私黑名单强制截屏（用户点击 "Continue Anyway" 时触发）
#[tauri::command]
pub async fn force_appshot_capture(app: tauri::AppHandle) -> Result<(), String> {
    use crate::runtime::force_capture;
    force_capture(&app);
    Ok(())
}

/// 动态更新全局快捷键（注销所有旧快捷键后重新注册 toggle + appshot + voice PTT + inline input）。
/// 注册失败时自动回滚到旧配置，保证原子性。
#[tauri::command]
pub fn update_global_shortcut(
    app: tauri::AppHandle,
    shortcut: String,
    appshot_shortcut: Option<String>,
    voice_ptt_shortcut: Option<String>,
    inline_input_shortcut: Option<String>,
) -> Result<(), String> {
    use tauri::Manager;
    use tauri_plugin_global_shortcut::GlobalShortcutExt;

    let old_config = app.state::<ConfigManager>().load();

    if let Err(e) = app.global_shortcut().unregister_all() {
        eprintln!("Failed to unregister old shortcuts: {}", e);
    }

    let result = register_shortcuts(
        &app,
        &shortcut,
        &appshot_shortcut,
        &voice_ptt_shortcut,
        &inline_input_shortcut,
    );

    if let Err(ref err_msg) = result {
        eprintln!("Shortcut registration failed: {err_msg}, rolling back to old config");
        let _ = app.global_shortcut().unregister_all();
        let _ = register_shortcuts(
            &app,
            &old_config.global_shortcut,
            &Some(old_config.appshot_shortcut),
            &Some(old_config.voice_ptt_shortcut),
            &Some(old_config.inline_input_shortcut),
        );
    }

    result
}

/// 迁移数据目录到新路径：先校验意图票据，再停止后端、复制数据、更新配置并重启
#[tauri::command]
pub async fn migrate_data_dir(
    app: tauri::AppHandle,
    new_dir: String,
    action_ticket: String,
    config_manager: State<'_, ConfigManager>,
    backend: State<'_, crate::runtime::PythonBackend>,
) -> Result<String, String> {
    let new_path = Path::new(&new_dir);

    if !new_path.exists() {
        std::fs::create_dir_all(new_path)
            .map_err(|e| format!("Failed to create target directory: {}", e))?;
    }

    if !new_path.is_dir() {
        return Err("Target path is not a directory".to_string());
    }

    let test_file = new_path.join(".myrm_write_test");
    std::fs::write(&test_file, b"test")
        .map_err(|_| "Target directory is not writable".to_string())?;
    let _ = std::fs::remove_file(&test_file);

    ipc_security::consume_sensitive_ticket(SensitiveAction::MigrateDataDir, &action_ticket)?;
    ipc_security::require_sensitive_action_confirmation(
        &app,
        SensitiveAction::MigrateDataDir,
        Some(&new_dir),
    )
    .await?;

    let config = config_manager.load();
    let old_dir = config.custom_data_dir.clone().unwrap_or_else(|| {
        let home = std::env::var("HOME")
            .or_else(|_| std::env::var("USERPROFILE"))
            .unwrap_or_else(|_| ".".to_string());
        format!("{}/.myrm", home)
    });
    let old_path = Path::new(&old_dir);

    println!("📦 Migrating data: {:?} → {:?}", old_path, new_path);

    crate::runtime::stop_backend(backend.clone())?;
    tokio::time::sleep(std::time::Duration::from_secs(2)).await;

    if old_path.exists() {
        let items = [
            "data.db",
            "checkpoints.db",
            "qdrant",
            "harness",
            "event_logs",
            "memory",
        ];
        for item in &items {
            let src = old_path.join(item);
            let dst = new_path.join(item);
            if !src.exists() {
                continue;
            }
            if src.is_dir() {
                copy_dir_recursive(&src, &dst)?;
            } else {
                if let Some(parent) = dst.parent() {
                    let _ = std::fs::create_dir_all(parent);
                }
                std::fs::copy(&src, &dst).map_err(|e| format!("Failed to copy {}: {}", item, e))?;
            }
            println!("  ✅ Copied: {}", item);
        }
    }

    let mut new_config = config;
    new_config.custom_data_dir = Some(new_dir.clone());
    config_manager.save(&new_config)?;

    println!("✅ Migration complete. Restarting backend...");

    let backend_config = crate::config::BackendConfig::from_system_config(&new_config);
    match crate::runtime::start_backend_with_config(app.clone(), backend, backend_config).await {
        Ok(msg) => Ok(format!("Migration complete, backend restarted: {}", msg)),
        Err(e) => Err(format!(
            "Migration complete but backend restart failed: {}. Please restart the app.",
            e
        )),
    }
}

fn copy_dir_recursive(src: &Path, dst: &Path) -> Result<(), String> {
    std::fs::create_dir_all(dst).map_err(|e| format!("Failed to create dir {:?}: {}", dst, e))?;
    for entry in
        std::fs::read_dir(src).map_err(|e| format!("Failed to read dir {:?}: {}", src, e))?
    {
        let entry = entry.map_err(|e| format!("Dir entry error: {}", e))?;
        let src_path = entry.path();
        let dst_path = dst.join(entry.file_name());
        if src_path.is_dir() {
            copy_dir_recursive(&src_path, &dst_path)?;
        } else {
            std::fs::copy(&src_path, &dst_path)
                .map_err(|e| format!("Failed to copy {:?}: {}", src_path, e))?;
        }
    }
    Ok(())
}

fn register_shortcuts(
    app: &tauri::AppHandle,
    shortcut: &str,
    appshot_shortcut: &Option<String>,
    voice_ptt_shortcut: &Option<String>,
    inline_input_shortcut: &Option<String>,
) -> Result<(), String> {
    use std::str::FromStr;
    use tauri_plugin_global_shortcut::GlobalShortcutExt;

    if !shortcut.is_empty() {
        if let Ok(s) = tauri_plugin_global_shortcut::Shortcut::from_str(shortcut) {
            if let Err(e) = app.global_shortcut().register(s) {
                return Err(format!("Failed to register global shortcut: {}", e));
            }
        } else {
            return Err(format!("Invalid shortcut format: {}", shortcut));
        }
    }

    if let Some(ref appshot) = appshot_shortcut {
        if !appshot.is_empty() {
            if let Ok(s) = tauri_plugin_global_shortcut::Shortcut::from_str(appshot) {
                if let Err(e) = app.global_shortcut().register(s) {
                    return Err(format!("Failed to register appshot shortcut: {}", e));
                }
                if let Ok(mut guard) = crate::runtime::APPSHOT_SHORTCUT_STR.lock() {
                    *guard = format!("{s}");
                }
            } else {
                return Err(format!("Invalid appshot shortcut format: {}", appshot));
            }
        }
    }

    if let Some(ref voice_ptt) = voice_ptt_shortcut {
        if !voice_ptt.is_empty() {
            if let Ok(s) = tauri_plugin_global_shortcut::Shortcut::from_str(voice_ptt) {
                if let Err(e) = app.global_shortcut().register(s) {
                    return Err(format!("Failed to register voice PTT shortcut: {}", e));
                }
                if let Ok(mut guard) = crate::runtime::VOICE_PTT_SHORTCUT_STR.lock() {
                    *guard = format!("{s}");
                }
            } else {
                return Err(format!("Invalid voice PTT shortcut format: {}", voice_ptt));
            }
        }
    }

    if let Some(ref inline_input) = inline_input_shortcut {
        if !inline_input.is_empty() {
            if let Ok(s) = tauri_plugin_global_shortcut::Shortcut::from_str(inline_input) {
                if let Err(e) = app.global_shortcut().register(s) {
                    return Err(format!("Failed to register inline input shortcut: {}", e));
                }
                if let Ok(mut guard) = crate::runtime::INLINE_INPUT_SHORTCUT_STR.lock() {
                    *guard = format!("{s}");
                }
            } else {
                return Err(format!(
                    "Invalid inline input shortcut format: {}",
                    inline_input
                ));
            }
        }
    }

    Ok(())
}
