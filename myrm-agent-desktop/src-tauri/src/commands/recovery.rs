//! 崩溃恢复 IPC 命令
//!
//! [INPUT]
//! - ConfigManager (POS: 读取 custom_data_dir 配置)
//!
//! [OUTPUT]
//! - `export_local_sqlite`: 无需 Python 后端即可导出本地 SQLite 数据库
//! - `reveal_app_folder`: 在系统文件管理器中打开数据/日志目录
//!
//! [POS]
//! 当 Python 后端彻底崩溃(watchdog 放弃重启)时，前端通过这些 IPC
//! 命令实现无后端的数据保全和故障排查。

use std::path::PathBuf;
use std::process::Command;

use tauri::State;

use crate::config::ConfigManager;

fn resolve_data_dir(config_manager: &ConfigManager) -> PathBuf {
    let config = config_manager.load();
    if let Some(ref custom) = config.custom_data_dir {
        PathBuf::from(custom)
    } else {
        home_dir().join(".myrm")
    }
}

fn resolve_logs_dir(config_manager: &ConfigManager) -> PathBuf {
    resolve_data_dir(config_manager).join("logs")
}

fn home_dir() -> PathBuf {
    std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
}

fn reveal_in_file_manager(path: &std::path::Path) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(path)
            .spawn()
            .map_err(|e| format!("Failed to open folder: {}", e))?;
    }
    #[cfg(target_os = "windows")]
    {
        Command::new("explorer")
            .arg(path)
            .spawn()
            .map_err(|e| format!("Failed to open folder: {}", e))?;
    }
    #[cfg(target_os = "linux")]
    {
        Command::new("xdg-open")
            .arg(path)
            .spawn()
            .map_err(|e| format!("Failed to open folder: {}", e))?;
    }
    Ok(())
}

/// 将本地 SQLite 数据库文件（含 WAL）导出到用户指定目录。
/// 无需 Python 后端即可执行，利用 Rust 直接操作文件系统。
#[tauri::command]
pub async fn export_local_sqlite(
    target_dir: String,
    config_manager: State<'_, ConfigManager>,
) -> Result<String, String> {
    let data_dir = resolve_data_dir(&config_manager);
    let db_path = data_dir.join("myrm.db");

    if !db_path.exists() {
        return Err("Database file not found".to_string());
    }

    let target = PathBuf::from(&target_dir);
    if !target.is_dir() {
        return Err("Target directory does not exist".to_string());
    }

    let extensions = ["", "-wal", "-shm"];
    let mut copied_count = 0u32;

    for ext in &extensions {
        let src = data_dir.join(format!("myrm.db{}", ext));
        if src.exists() {
            let dst = target.join(format!("myrm.db{}", ext));
            std::fs::copy(&src, &dst).map_err(|e| format!("Failed to copy {}: {}", ext, e))?;
            copied_count += 1;
        }
    }

    Ok(format!("Exported {} file(s) to {}", copied_count, target_dir))
}

/// 在系统文件管理器中打开指定类型的应用目录。
#[tauri::command]
pub async fn reveal_app_folder(
    folder_type: String,
    config_manager: State<'_, ConfigManager>,
) -> Result<(), String> {
    let path = match folder_type.as_str() {
        "data" => resolve_data_dir(&config_manager),
        "logs" => resolve_logs_dir(&config_manager),
        _ => return Err(format!("Unknown folder type: {}", folder_type)),
    };

    if !path.exists() {
        std::fs::create_dir_all(&path)
            .map_err(|e| format!("Failed to create directory: {}", e))?;
    }

    reveal_in_file_manager(&path)
}
