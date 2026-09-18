//! 系统配置相关的 Tauri 命令
//!
//! [INPUT]
//! - crate::config::{ConfigManager, SystemConfig} (POS: 桌面配置持久化管理)
//! - crate::commands::data_migration (POS: 数据目录迁移核心引擎)
//! - crate::runtime::{start_backend_with_config, stop_backend} (POS: Sidecar 生命周期编排)
//! - crate::ipc_security (POS: 敏感操作鉴权与确认弹窗)
//!
//! [OUTPUT]
//! - `load_system_config`: 加载系统运行时配置
//! - `save_system_config`: 保存系统配置并按需更新快捷键与自启
//! - `migrate_data_dir`: 迁移数据存储根目录并重启后端服务
//!
//! [POS]
//! 桌面端系统配置 IPC 命令接口。处理前端设置页面的读取、保存与数据存储路径迁移编排。

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

/// 重启应用（先触发受控优雅停机与进程树排空，确保零文件锁与端口释放）
#[tauri::command]
pub async fn restart_app(app: tauri::AppHandle) -> Result<(), String> {
    println!("🔄 Gracefully stopping sidecars before restart...");
    crate::app::lifecycle::graceful_shutdown(app.clone()).await;
    println!("🔄 Relaunching application...");
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

/// 迁移数据目录到新路径：前置路径与容量预检、意图确认、动态全量数据同步与自愈容灾
#[tauri::command]
pub async fn migrate_data_dir(
    app: tauri::AppHandle,
    new_dir: String,
    action_ticket: String,
    config_manager: State<'_, ConfigManager>,
    backend: State<'_, crate::runtime::PythonBackend>,
) -> Result<String, String> {
    // 0. 全局互斥锁，防止并发重复触发导致数据污染与竞态
    let _migration_guard = super::data_migration::acquire_migration_lock()?;

    let config = config_manager.load();
    let old_custom_data_dir = config.custom_data_dir.clone();
    let old_dir = old_custom_data_dir.clone().unwrap_or_else(|| {
        let home = std::env::var("HOME")
            .or_else(|_| std::env::var("USERPROFILE"))
            .unwrap_or_else(|_| ".".to_string());
        format!("{}/.myrm", home)
    });
    let old_path = Path::new(&old_dir);
    let new_path = Path::new(&new_dir);

    // 1. 目标路径合法性、防嵌套递归与同名冲突预检
    super::data_migration::validate_target_directory(old_path, new_path)?;

    // 2. 磁盘可用容量硬预检（安全阈值：1.2x 源数据量 + 500MB）
    let required_size = super::data_migration::calculate_dir_size(old_path);
    let safety_margin = (required_size as f64 * 1.2) as u64 + 500 * 1024 * 1024;
    if let Some(available_space) = super::data_migration::get_available_disk_space(new_path) {
        if available_space < safety_margin {
            return Err(format!(
                "Insufficient disk space on target partition: available {} MB, required {} MB (with safety margin)",
                available_space / (1024 * 1024),
                safety_margin / (1024 * 1024)
            ));
        }
    }

    // 3. 消费敏感操作票据并弹窗要求用户最终确认
    ipc_security::consume_sensitive_ticket(SensitiveAction::MigrateDataDir, &action_ticket)?;
    ipc_security::require_sensitive_action_confirmation(
        &app,
        SensitiveAction::MigrateDataDir,
        Some(&new_dir),
    )
    .await?;

    println!("📦 Migrating data: {:?} → {:?}", old_path, new_path);

    // 4. 优雅停止后端服务（stop_backend 内部确认进程真正退出后才返回）
    crate::runtime::stop_backend(app.clone(), backend.clone())?;

    // 5. 动态条目全量迁移（异常时自动清理半成品并重启恢复旧后端）
    // 复用预检已算出的源体积作进度分母，避免对大目录做第二次全树遍历
    let migration_res = super::data_migration::perform_data_migration_with_progress(
        old_path,
        new_path,
        required_size,
        &|progress| {
            use tauri::Emitter;
            let _ = app.emit(
                "data-migration-progress",
                serde_json::json!({
                    "done_entries": progress.done_entries,
                    "total_entries": progress.total_entries,
                    "current_entry": progress.current_entry,
                    "bytes_copied": progress.bytes_copied,
                    "bytes_total": progress.bytes_total,
                }),
            );
        },
    );
    let restart_old_backend = |app: &tauri::AppHandle, config: &crate::config::SystemConfig| {
        let old_backend_config = crate::config::BackendConfig::from_system_config(config);
        crate::runtime::start_backend_with_config(app.clone(), backend.clone(), old_backend_config)
    };
    let copied_entries = match migration_res {
        Ok(list) => list,
        Err(copy_err) => {
            println!(
                "⚠️ Data migration failed: {}. Restoring original backend...",
                copy_err
            );
            let restart_res = restart_old_backend(&app, &config).await;
            let restart_msg = match restart_res {
                Ok(_) => "Original backend successfully restored.".to_string(),
                Err(e) => format!("Failed to restore original backend: {}", e),
            };
            return Err(format!(
                "Data migration failed: {}. Rollback performed: {}",
                copy_err, restart_msg
            ));
        }
    };

    // 5b. 拷贝后体积对账：拦截静默损坏，不一致则清理并回滚旧后端
    // 仅清理本次复制的条目，绝不动目标盘原有文件
    if let Err(verify_err) =
        super::data_migration::verify_migrated_size(old_path, new_path)
    {
        println!("⚠️ {}", verify_err);
        super::data_migration::cleanup_migrated_entries(new_path, &copied_entries);
        let restart_res = restart_old_backend(&app, &config).await;
        let restart_msg = match restart_res {
            Ok(_) => "Original backend successfully restored.".to_string(),
            Err(e) => format!("Failed to restore original backend: {}", e),
        };
        return Err(format!("{}. Rollback performed: {}", verify_err, restart_msg));
    }

    // 6. 持久化新路径配置并拉起新后端服务
    let mut new_config = config;
    new_config.custom_data_dir = Some(new_dir.clone());
    config_manager.save(&new_config)?;

    println!("✅ Migration complete. Restarting backend with new data root...");

    let backend_config = crate::config::BackendConfig::from_system_config(&new_config);
    match crate::runtime::start_backend_with_config(app.clone(), backend.clone(), backend_config).await {
        Ok(msg) => Ok(format!("Migration complete, backend restarted: {}", msg)),
        Err(e) => {
            // 新后端健康门禁未过：配置自动指回旧目录并重启旧后端，避免断服悬空
            println!("⚠️ New backend failed health check: {}. Reverting...", e);
            let mut rollback_config = new_config;
            rollback_config.custom_data_dir = old_custom_data_dir;
            let _ = config_manager.save(&rollback_config);
            let old_backend_config =
                crate::config::BackendConfig::from_system_config(&rollback_config);
            let revert_res = crate::runtime::start_backend_with_config(
                app.clone(),
                backend,
                old_backend_config,
            )
            .await;
            let revert_msg = match revert_res {
                Ok(_) => "Reverted to original data directory and backend restored.".to_string(),
                Err(re) => format!("CRITICAL: revert also failed: {}. Original data untouched at {:?}; restart the app after fixing the cause.", re, old_path),
            };
            Err(format!(
                "Migration files copied, but new backend failed to start: {}. {}",
                e, revert_msg
            ))
        }
    }
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
