//! 帷幕状态桥：Tauri 帷幕状态机与 server 无人值守 watcher 共享的 `curtain_state.json`。
//!
//! [INPUT]
//! - tauri AppHandle (POS: app data 目录 / `curtain:state-changed` 事件)
//! - commands::privacy_curtain_state_io (POS: 带重试的读取与原子整文件替换)
//!
//! [OUTPUT]
//! - CurtainState: 文件桥状态结构（帷幕拉起 / 自动拉起 / 最近物理输入 / 代解锁租约电平）
//! - try_read_state: 读状态；读不到（瞬时错误重试耗尽）返回 None，由调用方决定怎么办
//! - mutate_state: 读-改-写；读不到或写不进去时返回 false 且不写任何东西（active 变化时广播 `curtain:state-changed`）
//! - reset_state: 整文件重置为全清状态（启动清理在读不到时的唯一出路）
//! - CURTAIN_STATE_FILE: 状态文件名（经 MYRM_CURTAIN_STATE_FILE 交给 server 定位）
//!
//! [POS]
//! 帷幕状态桥，`curtain_state.json` 的 Tauri 侧唯一读写入口。「读不到」与「没有状态」是两回事：
//! 文件不存在或内容无效 = 默认状态；瞬时错误重试耗尽 = 未知。读-改-写在未知时放弃本次写入
//! （与 server 侧 `_write_pending_flag` 同一立场），绝不拿默认值覆盖一个读不出来的真实状态——
//! 那会清掉 server 的租约位与静默期基准，让帷幕在 server 仍在代为操作时提前放行。
//! 进程内的读-改-写由一把锁串行化；跨进程无文件锁，并发写入以后写者为准：被覆盖的租约清除
//! 只让帷幕多保持（安全方向），被覆盖的租约置位会让帷幕提前放行，窗口仅限两侧同一毫秒写盘。

use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, PoisonError};
use std::time::Duration;

use tauri::{AppHandle, Emitter, Manager};

use crate::commands::privacy_curtain_state_io::{
    read_document, replace_document, Document, IO_RETRY_PAUSE,
};

/// 帷幕状态桥文件名（server 侧经 MYRM_CURTAIN_STATE_FILE 环境变量定位）。
pub const CURTAIN_STATE_FILE: &str = "curtain_state.json";

/// 进程内读-改-写的串行化：各写者共用同一个临时文件名，交错执行会把写了一半的临时文件换成正式文件。
static MUTATE_LOCK: Mutex<()> = Mutex::new(());

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

/// `None` = 读不到；文件不存在或内容无效（含不是合法 JSON）= 默认状态。
fn load_with(read: impl FnMut() -> io::Result<String>, pause: Duration) -> Option<CurtainState> {
    match read_document(read, pause) {
        Document::Text(text) => Some(serde_json::from_str(&text).unwrap_or_default()),
        Document::Empty => Some(CurtainState::default()),
        Document::Unreadable => None,
    }
}

fn load_state(path: &Path) -> Option<CurtainState> {
    load_with(|| fs::read_to_string(path), IO_RETRY_PAUSE)
}

/// 返回是否真的落盘。
fn store_state(path: &Path, state: &CurtainState, pause: Duration) -> bool {
    serde_json::to_string_pretty(state).is_ok_and(|content| replace_document(path, &content, pause))
}

/// 一次落盘成功的读-改-写：改前是否 active，以及改后的完整状态。
struct Mutation {
    was_active: bool,
    state: CurtainState,
}

/// 读-改-写的核心：读不到（`load` 返回 None）时既不应用修改也不写盘。
fn mutate_with(
    load: impl FnOnce() -> Option<CurtainState>,
    store: impl FnOnce(&CurtainState) -> bool,
    apply: impl FnOnce(&mut CurtainState),
) -> Option<Mutation> {
    let _serial = MUTATE_LOCK.lock().unwrap_or_else(PoisonError::into_inner);
    let mut state = load()?;
    let was_active = state.active;
    apply(&mut state);
    store(&state).then_some(Mutation { was_active, state })
}

fn state_path(app: &AppHandle) -> PathBuf {
    app.path()
        .app_data_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join(CURTAIN_STATE_FILE)
}

/// 读状态。`None` = 读不到：调用方不能把它当成「没有状态」去决策或写回。
pub(crate) fn try_read_state(app: &AppHandle) -> Option<CurtainState> {
    load_state(&state_path(app))
}

/// 读-改-写。返回 `false` = 状态读不到或没能落盘，此时文件原样保留、不广播事件；
/// 调用方必须决定怎么收敛（报错给用户 / 撤销刚做的副作用 / 下个 tick 重做）。
#[must_use = "false means the state file was left untouched"]
pub(crate) fn mutate_state(app: &AppHandle, apply: impl FnOnce(&mut CurtainState)) -> bool {
    let path = state_path(app);
    let Some(mutation) = mutate_with(
        || load_state(&path),
        |state| store_state(&path, state, IO_RETRY_PAUSE),
        apply,
    ) else {
        return false;
    };
    if mutation.was_active != mutation.state.active {
        let _ = app.emit("curtain:state-changed", mutation.state);
    }
    true
}

/// 整文件重置为全清状态（含静默期基准）。只用于启动清理读不到状态时：新进程里所有声明
/// 按定义都是过期事实，重写文件是持续读不到时唯一能自愈的路径。
pub(crate) fn reset_state(app: &AppHandle) -> bool {
    let path = state_path(app);
    let stored = {
        let _serial = MUTATE_LOCK.lock().unwrap_or_else(PoisonError::into_inner);
        store_state(&path, &CurtainState::default(), IO_RETRY_PAUSE)
    };
    if stored {
        let _ = app.emit("curtain:state-changed", CurtainState::default());
    }
    stored
}

#[cfg(test)]
mod tests {
    use super::{load_state, load_with, mutate_with, store_state, CurtainState};
    use std::cell::Cell;
    use std::io;
    use std::sync::Arc;
    use std::thread;
    use std::time::Duration;

    /// 注入错误的测试不需要等待。
    const NO_PAUSE: Duration = Duration::ZERO;
    /// 真实文件的写入：无错误时重试从不睡眠，这个间隔只在 Windows 出现瞬时拒绝时才花时间。
    const BRIEF_PAUSE: Duration = Duration::from_millis(5);

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
    fn a_stored_state_is_read_back_from_disk() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("curtain_state.json");
        let state = CurtainState {
            active: true,
            pending_auto_unlock: true,
            last_physical_input_ms: 7,
            ..CurtainState::default()
        };
        assert!(store_state(&path, &state, BRIEF_PAUSE));

        let loaded = load_state(&path).expect("readable");
        assert!(loaded.active && loaded.pending_auto_unlock);
        assert_eq!(loaded.last_physical_input_ms, 7);
    }

    /// 没有可用内容（文件不存在 / 不是合法 JSON）是确定的默认状态：下一次写入会把坏文件修好。
    #[test]
    fn missing_or_invalid_content_is_the_default_state() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("curtain_state.json");
        assert!(!load_state(&path).expect("missing file").active);

        std::fs::write(&path, "not json").expect("write");
        assert!(!load_state(&path).expect("invalid json").pending_auto_unlock);
    }

    /// 读不到才是未知：不能被当成默认状态。
    #[test]
    fn an_unreadable_file_is_unknown_not_the_default_state() {
        let unreadable = load_with(
            || Err(io::Error::from(io::ErrorKind::PermissionDenied)),
            NO_PAUSE,
        );
        assert!(unreadable.is_none());
    }

    /// 回归：读-改-写只改它要改的字段，别的字段（server 的租约位、静默期基准）原样保留。
    #[test]
    fn a_mutation_keeps_the_fields_it_does_not_touch() {
        let dir = tempfile::tempdir().expect("tempdir");
        let path = dir.path().join("curtain_state.json");
        let lease_held = CurtainState {
            last_physical_input_ms: 7,
            pending_auto_unlock: true,
            ..CurtainState::default()
        };
        assert!(store_state(&path, &lease_held, BRIEF_PAUSE));

        let mutation = mutate_with(
            || load_state(&path),
            |state| store_state(&path, state, BRIEF_PAUSE),
            |state| state.active = true,
        )
        .expect("mutated");

        assert!(!mutation.was_active && mutation.state.active);
        let stored = load_state(&path).expect("readable");
        assert!(stored.active);
        assert!(
            stored.pending_auto_unlock,
            "the server's lease bit survives"
        );
        assert_eq!(stored.last_physical_input_ms, 7);
    }

    /// 回归：读不到真实状态时不能拿默认值去覆盖它——不应用修改、不写盘。
    #[test]
    fn an_unreadable_state_is_never_overwritten() {
        let applied = Cell::new(false);
        let mutation = mutate_with(
            || None,
            |_| panic!("an unreadable state must not be written"),
            |_| applied.set(true),
        );
        assert!(mutation.is_none());
        assert!(!applied.get());
    }

    #[test]
    fn a_mutation_that_did_not_reach_the_disk_reports_nothing() {
        let mutation = mutate_with(
            || Some(CurtainState::default()),
            |_| false,
            |state| state.active = true,
        );
        assert!(mutation.is_none());
    }

    /// 进程内的读-改-写互相串行化：并发递增不丢更新，共用的临时文件也不会被交错写成撕裂文档。
    #[test]
    fn concurrent_mutations_lose_no_update() {
        const THREADS: u64 = 4;
        const ROUNDS: u64 = 60;
        let dir = tempfile::tempdir().expect("tempdir");
        let path = Arc::new(dir.path().join("curtain_state.json"));

        let workers: Vec<_> = (0..THREADS)
            .map(|_| {
                let path = Arc::clone(&path);
                thread::spawn(move || {
                    for _ in 0..ROUNDS {
                        let mutation = mutate_with(
                            || load_state(&path),
                            |state| store_state(&path, state, BRIEF_PAUSE),
                            |state| state.last_physical_input_ms += 1,
                        );
                        assert!(mutation.is_some());
                    }
                })
            })
            .collect();
        for worker in workers {
            worker.join().expect("worker");
        }

        let stored = load_state(&path).expect("readable");
        assert_eq!(stored.last_physical_input_ms, THREADS * ROUNDS);
    }
}
