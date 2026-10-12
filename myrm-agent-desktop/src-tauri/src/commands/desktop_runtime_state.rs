//! Desktop runtime 能力桥：Sidecar 与 Tauri 共享的 `desktop_runtime.json`（静态能力开关）。
//!
//! [INPUT]
//! - tauri AppHandle (POS: app data 目录)
//! - SystemConfig.locked_use_enabled（POS: 离席授权唯一 UI 来源）
//!
//! [OUTPUT]
//! - DesktopRuntimeState / RUNTIME_STATE_FILE
//! - sync_locked_use_enabled: 原子写入 lockedUseEnabled（经 MYRM_DESKTOP_RUNTIME_FILE 交给 server）
//!
//! [POS]
//! 离席授权的运行时 SSOT（与 spawn-time env 互补：server 读文件即可在保存后即时生效，无需重启 Sidecar）。
//! 整文件原子替换，读者不会读到撕裂 JSON。

use std::fs;
use std::path::{Path, PathBuf};

use tauri::{AppHandle, Manager};

/// Runtime 能力桥文件名（server 侧经 MYRM_DESKTOP_RUNTIME_FILE 环境变量定位）。
pub const RUNTIME_STATE_FILE: &str = "desktop_runtime.json";

/// Server 读取的环境变量名（与 `curtain_bridge.DESKTOP_RUNTIME_FILE_ENV` 契约一致）。
pub const DESKTOP_RUNTIME_FILE_ENV: &str = "MYRM_DESKTOP_RUNTIME_FILE";

#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct DesktopRuntimeState {
    /// Computer Use 离席/代解锁用户授权（与 SystemConfig.locked_use_enabled 同步）。
    pub locked_use_enabled: bool,
}

pub fn runtime_state_path(app: &AppHandle) -> PathBuf {
    app.path()
        .app_data_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join(RUNTIME_STATE_FILE)
}

fn write_runtime_file(path: &Path, state: &DesktopRuntimeState) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("Failed to create runtime state dir: {e}"))?;
    }
    let content = serde_json::to_string_pretty(state)
        .map_err(|e| format!("Failed to serialize desktop runtime state: {e}"))?;
    let temp_path = path.with_extension("json.tmp");
    fs::write(&temp_path, content).map_err(|e| format!("Failed to write runtime state temp: {e}"))?;
    fs::rename(&temp_path, path).map_err(|e| {
        let _ = fs::remove_file(&temp_path);
        format!("Failed to commit runtime state file: {e}")
    })
}

/// 将离席授权开关写入 runtime 桥（保存设置或 Sidecar 启动前调用）。
pub fn sync_locked_use_enabled(app: &AppHandle, enabled: bool) -> Result<(), String> {
    let state = DesktopRuntimeState {
        locked_use_enabled: enabled,
    };
    write_runtime_file(&runtime_state_path(app), &state)
}

#[cfg(test)]
mod tests {
    use super::{write_runtime_file, DesktopRuntimeState, RUNTIME_STATE_FILE};

    #[test]
    fn runtime_state_roundtrips_camel_case_json() {
        let state = DesktopRuntimeState {
            locked_use_enabled: true,
        };
        let json = serde_json::to_string(&state).expect("serialize");
        assert!(json.contains("\"lockedUseEnabled\":true"));
        let parsed: DesktopRuntimeState = serde_json::from_str(&json).expect("deserialize");
        assert!(parsed.locked_use_enabled);
    }

    #[test]
    fn runtime_file_write_atomic_leaves_no_temp() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join(RUNTIME_STATE_FILE);
        write_runtime_file(
            &path,
            &DesktopRuntimeState {
                locked_use_enabled: false,
            },
        )
        .expect("write");
        assert!(path.exists());
        assert!(!path.with_extension("json.tmp").exists());
    }
}
