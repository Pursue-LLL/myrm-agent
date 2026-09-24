//! Remote Profile 跟随标记：Remote 激活时本地 Python 后端 defer 依据。
//!
//! [INPUT]
//! - Tauri AppHandle app_data_dir (POS: 桌面端应用数据目录)
//!
//! [OUTPUT]
//! - get_remote_follow / set_remote_follow IPC
//! - is_remote_follow_deferred: setup 期同步判定
//!
//! [POS]
//! 连接态持久化（localStorage roster 在前端，defer 标记在 Rust 侧文件）。
//! 仅存布尔意图，不存 URL/token，避免密钥落盘。

use std::fs;
use std::path::PathBuf;

use tauri::{AppHandle, Manager};

const REMOTE_FOLLOW_FILE: &str = "remote_follow.json";

fn follow_path(app: &AppHandle) -> PathBuf {
    app.path()
        .app_data_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join(REMOTE_FOLLOW_FILE)
}

fn read_deferred(path: &PathBuf) -> bool {
    fs::read_to_string(path)
        .ok()
        .and_then(|content| serde_json::from_str::<serde_json::Value>(&content).ok())
        .and_then(|value| value.get("deferred").and_then(|v| v.as_bool()))
        .unwrap_or(false)
}

/// setup 期同步判定：Remote 跟随时跳过本地 Python 后端自启。
pub fn is_remote_follow_deferred(app: &AppHandle) -> bool {
    read_deferred(&follow_path(app))
}

/// 查询当前是否处于 Remote 跟随态。
#[tauri::command]
pub fn get_remote_follow(app: AppHandle) -> Result<bool, String> {
    Ok(read_deferred(&follow_path(&app)))
}

/// 设置 Remote 跟随态（前端切换连接档案时调用）。
#[tauri::command]
pub fn set_remote_follow(app: AppHandle, deferred: bool) -> Result<(), String> {
    let path = follow_path(&app);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("Failed to create app data dir: {e}"))?;
    }
    let payload = serde_json::json!({ "deferred": deferred });
    let content =
        serde_json::to_string_pretty(&payload).map_err(|e| format!("Failed to serialize flag: {e}"))?;
    fs::write(&path, content).map_err(|e| format!("Failed to write remote follow flag: {e}"))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::path::PathBuf;

    #[test]
    fn missing_file_means_not_deferred() {
        let path = PathBuf::from("/nonexistent-remote-follow-flag.json");
        assert!(!super::read_deferred(&path));
    }

    #[test]
    fn malformed_file_means_not_deferred() {
        let dir = std::env::temp_dir();
        let path = dir.join("myrm-remote-follow-malformed.json");
        let _ = std::fs::write(&path, "not-json");
        assert!(!super::read_deferred(&path));
        let _ = std::fs::remove_file(&path);
    }
}
