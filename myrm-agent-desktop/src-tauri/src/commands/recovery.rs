//! 崩溃恢复 IPC 命令
//!
//! [INPUT]
//! - ConfigManager (POS: 读取 custom_data_dir 配置)
//! - crate::utils::data_dir (POS: 与后端同一个数据根目录的解析)
//!
//! [OUTPUT]
//! - `export_local_sqlite`: 无需 Python 后端即可导出本地 SQLite 数据库
//! - `reveal_app_folder`: 在系统文件管理器中打开数据/日志目录
//!
//! [POS]
//! 当 Python 后端彻底崩溃(watchdog 放弃重启)时，前端通过这些 IPC
//! 命令实现无后端的数据保全和故障排查。

use std::path::{Path, PathBuf};
use std::process::Command;

use tauri::State;

use crate::config::ConfigManager;
use crate::ipc_security::{self, SensitiveAction};
use crate::utils::data_dir;

/// 服务端主库文件名（会话、消息等用户数据所在；与 `DatabaseSettings.sqlite_path` 一致）。
const DATABASE_FILE: &str = "data.db";

/// WAL 模式下未检查点的写入只存在于 `-wal` 文件，缺了它导出的库会丢最近的数据。
const DATABASE_FILE_SUFFIXES: [&str; 3] = ["", "-wal", "-shm"];

fn resolve_data_dir(config_manager: &ConfigManager) -> PathBuf {
    data_dir::effective_dir(config_manager.load().custom_data_dir.as_deref())
}

fn resolve_logs_dir(config_manager: &ConfigManager) -> PathBuf {
    resolve_data_dir(config_manager).join("logs")
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

/// 把主库及其 WAL/SHM 复制到 `target`，返回实际复制的文件数。
fn copy_database_files(data_dir: &Path, target: &Path) -> Result<u32, String> {
    let mut copied_count = 0u32;
    for suffix in DATABASE_FILE_SUFFIXES {
        let file_name = format!("{DATABASE_FILE}{suffix}");
        let src = data_dir.join(&file_name);
        if src.exists() {
            std::fs::copy(&src, target.join(&file_name))
                .map_err(|e| format!("Failed to copy {}: {}", file_name, e))?;
            copied_count += 1;
        }
    }
    Ok(copied_count)
}

/// 将本地 SQLite 数据库文件（含 WAL）导出到用户指定目录。
/// 需要先通过高敏操作意图票据校验；无需 Python 后端即可执行。
#[tauri::command]
pub async fn export_local_sqlite(
    app: tauri::AppHandle,
    target_dir: String,
    action_ticket: String,
    config_manager: State<'_, ConfigManager>,
) -> Result<String, String> {
    let data_dir = resolve_data_dir(&config_manager);
    let db_path = data_dir.join(DATABASE_FILE);

    if !db_path.exists() {
        return Err("Database file not found".to_string());
    }

    let target = PathBuf::from(&target_dir);
    if !target.is_dir() {
        return Err("Target directory does not exist".to_string());
    }

    ipc_security::consume_sensitive_ticket(SensitiveAction::ExportLocalSqlite, &action_ticket)?;
    ipc_security::require_sensitive_action_confirmation(
        &app,
        SensitiveAction::ExportLocalSqlite,
        Some(&target_dir),
    )
    .await?;

    let copied_count = copy_database_files(&data_dir, &target)?;

    Ok(format!(
        "Exported {} file(s) to {}",
        copied_count, target_dir
    ))
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
        std::fs::create_dir_all(&path).map_err(|e| format!("Failed to create directory: {}", e))?;
    }

    reveal_in_file_manager(&path)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn write(dir: &Path, name: &str, contents: &str) {
        std::fs::write(dir.join(name), contents).unwrap();
    }

    #[test]
    fn the_export_copies_the_servers_database_with_its_wal_and_shm() {
        let data = tempfile::tempdir().unwrap();
        let target = tempfile::tempdir().unwrap();
        write(data.path(), "data.db", "main");
        write(data.path(), "data.db-wal", "recent writes");
        write(data.path(), "data.db-shm", "index");

        assert_eq!(copy_database_files(data.path(), target.path()), Ok(3));
        for (name, contents) in [
            ("data.db", "main"),
            ("data.db-wal", "recent writes"),
            ("data.db-shm", "index"),
        ] {
            assert_eq!(
                std::fs::read_to_string(target.path().join(name)).unwrap(),
                contents
            );
        }
    }

    #[test]
    fn the_export_copies_only_the_files_that_exist() {
        let data = tempfile::tempdir().unwrap();
        let target = tempfile::tempdir().unwrap();
        write(data.path(), "data.db", "main");

        assert_eq!(copy_database_files(data.path(), target.path()), Ok(1));
        assert!(!target.path().join("data.db-wal").exists());
    }

    #[test]
    fn the_export_ignores_files_that_are_not_the_servers_database() {
        let data = tempfile::tempdir().unwrap();
        let target = tempfile::tempdir().unwrap();
        write(data.path(), "myrm.db", "not the server database");
        write(data.path(), "checkpoints.db", "agent checkpoints");

        assert_eq!(copy_database_files(data.path(), target.path()), Ok(0));
        assert_eq!(std::fs::read_dir(target.path()).unwrap().count(), 0);
    }

    #[test]
    fn a_failed_copy_names_the_file_that_failed() {
        let data = tempfile::tempdir().unwrap();
        write(data.path(), "data.db", "main");
        let missing_target = data.path().join("no-such-directory");

        let error = copy_database_files(data.path(), &missing_target).unwrap_err();
        assert!(error.starts_with("Failed to copy data.db:"), "{error}");
    }
}
