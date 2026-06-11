//! 系统配置相关的 Tauri 命令
//!
//! 提供前端调用的系统配置相关命令。

use tauri::State;
use crate::config::{ConfigManager, SystemConfig};

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
    config: SystemConfig,
    config_manager: State<'_, ConfigManager>,
) -> Result<(), String> {
    config_manager.save(&config)?;
    Ok(())
}

/// 重置为默认配置
#[tauri::command]
pub async fn reset_system_config(
    config_manager: State<'_, ConfigManager>,
) -> Result<SystemConfig, String> {
    config_manager.reset()?;
    Ok(config_manager.load())
}

/// 获取当前运行模式
#[tauri::command]
pub async fn get_current_mode(
    config_manager: State<'_, ConfigManager>,
) -> Result<String, String> {
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

/// 动态更新全局快捷键（注销所有旧快捷键后重新注册 toggle + appshot）
#[tauri::command]
pub fn update_global_shortcut(
    app: tauri::AppHandle,
    shortcut: String,
    appshot_shortcut: Option<String>,
) -> Result<(), String> {
    use tauri_plugin_global_shortcut::GlobalShortcutExt;
    use std::str::FromStr;

    if let Err(e) = app.global_shortcut().unregister_all() {
        eprintln!("Failed to unregister old shortcuts: {}", e);
    }

    if !shortcut.is_empty() {
        if let Ok(s) = tauri_plugin_global_shortcut::Shortcut::from_str(&shortcut) {
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
                if let Ok(mut guard) = crate::runtime::APPSHOT_SHORTCUT_STR.lock() {
                    *guard = format!("{s}");
                }
                if let Err(e) = app.global_shortcut().register(s) {
                    return Err(format!("Failed to register appshot shortcut: {}", e));
                }
            } else {
                return Err(format!("Invalid appshot shortcut format: {}", appshot));
            }
        }
    }

    Ok(())
}
