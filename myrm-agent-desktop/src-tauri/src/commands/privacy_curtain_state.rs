//! 帷幕状态桥：Tauri 帷幕状态机与 server 无人值守 watcher 共享的 `curtain_state.json`。
//!
//! [INPUT]
//! - tauri AppHandle (POS: app data 目录 / `curtain:state-changed` 事件)
//!
//! [OUTPUT]
//! - `CurtainState` / `read_state` / `mutate_state`（帷幕窗口层与 watcher 共用）
//! - `CURTAIN_STATE_FILE`（经 MYRM_CURTAIN_STATE_FILE 交给 server 定位）
//!
//! [POS]
//! 跨进程文件桥的 Tauri 侧唯一读写入口。整文件原子替换，另一进程的读者永远读到完整
//! 文档；读-改-写之间无文件锁，并发写入以后写者为准：被覆盖的租约清除只让帷幕多保持
//! （安全方向），被覆盖的租约置位会让帷幕提前放行，窗口仅限两侧同一毫秒写盘。

use std::fs;
use std::path::{Path, PathBuf};

use tauri::{AppHandle, Emitter, Manager};

/// 帷幕状态桥文件名（server 侧经 MYRM_CURTAIN_STATE_FILE 环境变量定位）。
pub const CURTAIN_STATE_FILE: &str = "curtain_state.json";

/// 文件桥状态：server 无人值守 watcher 与 Tauri 帷幕状态机的共享事实。
#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct CurtainState {
    /// 帷幕当前拉起。
    pub active: bool,
    /// 由锁屏 watcher 自动拉起（区别于手动拉起；解锁时仅 auto 帷幕自动收起）。
    pub auto_engaged: bool,
    /// 最近一次帷幕上物理输入的时间戳（server 静默期判定基准）。
    pub last_physical_input_ms: u64,
    /// 服务端代解锁租约（**电平**，服务端持有期间保持置位）：
    /// 置位时桌面壳持续遮蔽屏幕，仅在服务端确认回锁后清除；
    /// 若服务端中途退出，置位保持 → 帷幕保持（安全方向）。
    pub pending_auto_unlock: bool,
}

fn state_path(app: &AppHandle) -> PathBuf {
    app.path()
        .app_data_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join(CURTAIN_STATE_FILE)
}

pub(crate) fn read_state(app: &AppHandle) -> CurtainState {
    fs::read_to_string(state_path(app))
        .ok()
        .and_then(|content| serde_json::from_str(&content).ok())
        .unwrap_or_default()
}

fn write_state(app: &AppHandle, state: &CurtainState) {
    write_state_file(&state_path(app), state);
}

/// 整文件原子替换：server 并发读取，被截断的文档会被解析为空状态。
fn write_state_file(path: &Path, state: &CurtainState) {
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let Ok(content) = serde_json::to_string_pretty(state) else {
        return;
    };
    let temp_path = path.with_extension("json.tmp");
    if fs::write(&temp_path, content).is_ok() && fs::rename(&temp_path, path).is_err() {
        let _ = fs::remove_file(&temp_path);
    }
}

pub(crate) fn mutate_state(app: &AppHandle, apply: impl FnOnce(&mut CurtainState)) {
    let mut state = read_state(app);
    let before = state.active;
    apply(&mut state);
    write_state(app, &state);
    if before != state.active {
        let _ = app.emit("curtain:state-changed", state.clone());
    }
}

#[cfg(test)]
mod tests {
    use super::{write_state_file, CurtainState};
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::Arc;
    use std::thread;

    #[test]
    fn state_defaults_to_inactive() {
        let state = CurtainState::default();
        assert!(!state.active);
        assert!(!state.auto_engaged);
        assert!(!state.pending_auto_unlock);
        assert_eq!(state.last_physical_input_ms, 0);
    }

    #[test]
    fn state_roundtrips_through_camel_case_json() {
        let state = CurtainState {
            active: true,
            auto_engaged: true,
            last_physical_input_ms: 42,
            pending_auto_unlock: true,
        };
        let json = serde_json::to_string(&state).expect("serialize");
        assert!(json.contains("\"active\":true"));
        assert!(json.contains("\"lastPhysicalInputMs\":42"));
        let parsed: CurtainState = serde_json::from_str(&json).expect("deserialize");
        assert!(parsed.active && parsed.pending_auto_unlock);
    }

    #[test]
    fn partial_state_json_deserializes_with_defaults() {
        let parsed: CurtainState =
            serde_json::from_str("{\"active\":true}").expect("deserialize partial");
        assert!(parsed.active);
        assert!(!parsed.auto_engaged);
    }

    #[test]
    fn state_file_write_replaces_content_and_leaves_no_temp_file() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("curtain_state.json");

        for pending in [true, false] {
            let state = CurtainState {
                active: true,
                pending_auto_unlock: pending,
                ..CurtainState::default()
            };
            write_state_file(&path, &state);
            let parsed: CurtainState =
                serde_json::from_str(&std::fs::read_to_string(&path).expect("read"))
                    .expect("parse");
            assert_eq!(parsed.pending_auto_unlock, pending);
        }

        let entries: Vec<_> = std::fs::read_dir(dir.path())
            .expect("read_dir")
            .map(|entry| entry.expect("entry").file_name())
            .collect();
        assert_eq!(entries, ["curtain_state.json"]);
    }

    #[test]
    fn concurrent_reader_never_sees_a_torn_state_file() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("curtain_state.json");
        write_state_file(&path, &CurtainState::default());

        let stop = Arc::new(AtomicBool::new(false));
        let reader = {
            let (stop, path) = (Arc::clone(&stop), path.clone());
            thread::spawn(move || {
                let mut torn = 0_u32;
                while !stop.load(Ordering::Relaxed) {
                    let content = std::fs::read_to_string(&path).expect("file always present");
                    if serde_json::from_str::<CurtainState>(&content).is_err() {
                        torn += 1;
                    }
                }
                torn
            })
        };
        for round in 0..3000_u64 {
            let state = CurtainState {
                last_physical_input_ms: round,
                pending_auto_unlock: round % 2 == 0,
                ..CurtainState::default()
            };
            write_state_file(&path, &state);
        }
        stop.store(true, Ordering::Relaxed);

        assert_eq!(
            reader.join().expect("reader"),
            0,
            "reader saw a torn document"
        );
    }
}
