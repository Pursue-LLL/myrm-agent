//! 帷幕拉起 / 收起的固定顺序：窗口副作用与状态记录谁先谁后，没记下时怎么收敛。
//!
//! [INPUT]
//! - commands::privacy_curtain_state (POS: 帷幕状态桥，mutate_state 返回 false = 文件原样保留)
//!
//! [OUTPUT]
//! - raise_curtain: 窗口先落地、再记状态、没记下就撤销窗口
//! - record_release: 收起帷幕后记下状态
//! - state_unavailable: 状态读不到或没写进去时交给调用方的错误（`mutate_state` 的 false 在此转成它）
//!
//! [POS]
//! 手动命令（privacy_curtain.rs）与 watcher 共用同一套顺序，状态写入失败时两条路径的收敛行为因此一致：
//! 拉起撤销窗口、事实回到动作之前，由下个 tick / 用户重试整个重来；收起的窗口已经收了，只剩补记状态。

use tauri::AppHandle;

use crate::commands::privacy_curtain_state::mutate_state;

/// 状态文件读不到或没写进去时交给调用方的错误（会原样展示给用户，不含路径等内部细节）。
pub(crate) fn state_unavailable() -> String {
    "Privacy curtain state is temporarily unavailable, please try again".to_string()
}

/// `mutate_state` 返回 false（文件原样保留）= 动作没有记录下来：必须报错，不能假装成功。
fn ensure_recorded(recorded: bool) -> Result<(), String> {
    if recorded {
        Ok(())
    } else {
        Err(state_unavailable())
    }
}

/// 拉起帷幕的固定顺序：窗口先落地（遮蔽优先），再记状态；状态没记下就撤销刚落地的窗口。
/// 留着它会让窗口在而状态不认：设置页与托盘以为没有帷幕，自动拉起的帷幕在用户解锁后
/// 也不会被收起（auto_engaged 未置位）。撤销之后事实与动作发生前一致，自动拉起由下个 tick 照常重做。
pub(crate) fn raise_curtain(
    deploy: impl FnOnce() -> Result<(), String>,
    record: impl FnOnce() -> bool,
    undo: impl FnOnce(),
) -> Result<(), String> {
    deploy()?;
    let recorded = ensure_recorded(record());
    if recorded.is_err() {
        undo();
    }
    recorded
}

/// 收起帷幕后记下状态。`Err` = 没记下、文件原样保留：自动收起的决策在下个 tick 依旧成立，
/// 手动收起由用户重试补记（窗口早已不在，重试只剩记状态这一步）。
pub(crate) fn record_release(app: &AppHandle) -> Result<(), String> {
    ensure_recorded(mutate_state(app, |state| {
        state.active = false;
        state.auto_engaged = false;
    }))
}

#[cfg(test)]
mod tests {
    use super::{ensure_recorded, raise_curtain, state_unavailable};
    use std::cell::RefCell;

    /// 跑一遍 `raise_curtain`，返回结果与各步骤实际发生的顺序。
    fn raise(
        deployed: Result<(), String>,
        recorded: bool,
    ) -> (Result<(), String>, Vec<&'static str>) {
        let steps = RefCell::new(Vec::new());
        let result = raise_curtain(
            || {
                steps.borrow_mut().push("deploy");
                deployed
            },
            || {
                steps.borrow_mut().push("record");
                recorded
            },
            || steps.borrow_mut().push("undo"),
        );
        (result, steps.into_inner())
    }

    /// 拉起时状态没记下：窗口必须按「落地 → 记状态 → 撤销」的顺序被撤掉，错误交还调用方；
    /// 撤销后事实回到动作之前，自动拉起由下个 tick 重做。
    #[test]
    fn a_curtain_whose_state_was_not_recorded_is_withdrawn() {
        let (result, steps) = raise(Ok(()), false);
        assert_eq!(result, Err(state_unavailable()));
        assert_eq!(steps, ["deploy", "record", "undo"]);
    }

    #[test]
    fn a_recorded_curtain_stays_up() {
        let (result, steps) = raise(Ok(()), true);
        assert_eq!(result, Ok(()));
        assert_eq!(steps, ["deploy", "record"]);
    }

    /// 窗口没能落地时没有任何东西需要记录或撤销，也不能去碰状态文件。
    #[test]
    fn a_curtain_that_could_not_be_deployed_touches_no_state() {
        let (result, steps) = raise(Err("no monitors".to_string()), true);
        assert_eq!(result, Err("no monitors".to_string()));
        assert_eq!(steps, ["deploy"]);
    }

    #[test]
    fn an_unrecorded_action_is_an_error_for_the_caller() {
        assert_eq!(ensure_recorded(true), Ok(()));
        assert_eq!(ensure_recorded(false), Err(state_unavailable()));
    }
}
