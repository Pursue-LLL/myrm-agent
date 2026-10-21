//! Remote Profile 跟随标记：Remote 激活时本地 Python 后端 defer 依据。
//!
//! [INPUT]
//! - Tauri AppHandle app_data_dir (POS: 桌面端应用数据目录)
//! - config::{BackendConfig, ConfigManager} (POS: 切回本地时按系统配置重启后端)
//! - runtime::{graceful_stop_backend, start_backend_with_config, spawn_backend_monitors} (POS: 后端生命周期编排)
//!
//! [OUTPUT]
//! - get_remote_follow / switch_remote_follow IPC
//! - is_remote_follow_deferred: setup 期同步判定
//!
//! [POS]
//! 连接态持久化（localStorage roster 在前端，defer 标记在 Rust 侧文件）。
//! 仅存布尔意图，不存 URL/token，避免密钥落盘。
//! switch_remote_follow 是切换唯一入口：切 remote 优雅停本地后端（含 watchdog/wake 停止），
//! 切回本地重启后端并重挂健康监控；编排成功才落 flag（失败零 flag 副作用，flag 与
//! 真实进程态永不不一致），随后广播 `app:connections-changed` 驱动全窗口 reload。

use std::fs;
use std::path::PathBuf;

use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager, State};

use crate::config::{BackendConfig, ConfigManager};
use crate::runtime::{
    graceful_stop_backend, spawn_backend_monitors, start_backend_with_config, PythonBackend,
};

const REMOTE_FOLLOW_FILE: &str = "remote_follow.json";

/// 广播给前端的连接态变更事件 payload（驱动全窗口统一 reload）。
#[derive(Serialize, Clone)]
pub struct ConnectionsChanged {
    pub remote: bool,
}

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

fn write_follow_deferred(app: &AppHandle, deferred: bool) -> Result<(), String> {
    let path = follow_path(app);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("Failed to create app data dir: {e}"))?;
    }
    let payload = serde_json::json!({ "deferred": deferred });
    let content = serde_json::to_string_pretty(&payload)
        .map_err(|e| format!("Failed to serialize flag: {e}"))?;
    fs::write(&path, content).map_err(|e| format!("Failed to write remote follow flag: {e}"))?;
    Ok(())
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

/// 切换 Remote 跟随态并编排本地后端生命周期（切换连接档案的唯一 Rust 入口）。
///
/// deferred=true（切向 remote）：优雅停本地后端（先停 watchdog/wake，再请求
/// 服务端 drain 后自退，兜底强杀），确保 remote_follow 省内存设计不被复活破坏。
/// deferred=false（切回本地）：按当前系统配置重启后端并重挂健康监控。
/// 生命周期编排成功后才落 flag（失败路径零 flag 副作用，flag 文件与真实
/// 进程态永不不一致），随后广播 `app:connections-changed` 驱动全窗口 reload。
#[tauri::command]
pub async fn switch_remote_follow(
    app: AppHandle,
    backend: State<'_, PythonBackend>,
    deferred: bool,
) -> Result<(), String> {
    if deferred {
        graceful_stop_backend(&app, &backend)
            .await
            .map_err(|e| format!("Failed to stop local backend for remote follow: {e}"))?;
        write_follow_deferred(&app, true)?;
    } else {
        let config_manager = app.state::<ConfigManager>();
        let system_config = config_manager.load();
        let backend_config = BackendConfig::from_system_config(&system_config);
        let port = backend_config.port;

        start_backend_with_config(app.clone(), backend, backend_config)
            .await
            .map_err(|e| format!("Failed to restart local backend: {e}"))?;
        spawn_backend_monitors(&app, port);
        write_follow_deferred(&app, false)?;
    }

    let _ = app.emit(
        "app:connections-changed",
        ConnectionsChanged { remote: deferred },
    );
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
