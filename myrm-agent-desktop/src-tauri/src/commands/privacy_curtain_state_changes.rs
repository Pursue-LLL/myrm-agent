//! 帷幕状态的迁移：每种迁移一个具名方法，只改它负责的字段。
//!
//! [INPUT]
//! - commands::privacy_curtain_state::CurtainState (POS: 帷幕状态桥的状态结构)
//!
//! [OUTPUT]
//! - CurtainState::engage_manually / engage_automatically: 手动 / 锁屏触发的拉起
//! - CurtainState::release: 收起（手动与自动共用）
//! - CurtainState::release_lease: 回锁确认后交还代解锁租约位
//! - CurtainState::record_physical_input: 帷幕上的物理输入刷新静默期基准
//! - CurtainState::has_stale_claims / clear_stale_claims: 上一进程遗留的声明及其清除
//!
//! [POS]
//! 状态文件由壳与 server 两个进程共写：租约位由 server 置位、回锁经系统确认后才清除，
//! 静默期基准只记录帷幕上真实的物理输入。
//! 调用点（IPC 命令、watcher、启动清理）只说「发生了什么」，字段怎么变写在这里；迁移不依赖 Tauri，
//! 因此每个迁移都能连同它**没有**改动的字段一起单测。

use crate::commands::privacy_curtain_state::CurtainState;

impl CurtainState {
    /// 手动拉起：不是 auto 帷幕（用户解锁时 watcher 不会替它收起），拉起时刻记作静默期基准
    /// （用户此刻在机前操作）。租约位不动：server 持有期间拉起帷幕只是多一层遮蔽。
    pub(crate) fn engage_manually(&mut self, now_ms: u64) {
        self.active = true;
        self.auto_engaged = false;
        self.last_physical_input_ms = now_ms;
    }

    /// 锁屏触发的自动拉起。刻意不碰静默期基准：它只记录帷幕上真实的物理输入，锁屏本身不是输入——
    /// 人是否还在机前由 server 的硬件输入空闲探针判定。
    pub(crate) fn engage_automatically(&mut self) {
        self.active = true;
        self.auto_engaged = true;
    }

    /// 收起帷幕（手动与自动共用）。收起窗口不等于租约已交还：租约位只在回锁确认后才清除。
    pub(crate) fn release(&mut self) {
        self.active = false;
        self.auto_engaged = false;
    }

    /// 回锁经系统确认后交还代解锁租约位，其余字段原样保留。
    pub(crate) fn release_lease(&mut self) {
        self.pending_auto_unlock = false;
    }

    /// 帷幕上的物理输入：只刷新静默期基准。
    pub(crate) fn record_physical_input(&mut self, now_ms: u64) {
        self.last_physical_input_ms = now_ms;
    }

    /// 是否留着上一进程的声明：新进程没有任何帷幕窗口，active / auto / 租约位都是过期事实。
    /// 静默期基准是时间戳而不是声明，不算。
    pub(crate) fn has_stale_claims(&self) -> bool {
        self.active || self.auto_engaged || self.pending_auto_unlock
    }

    /// 清掉全部过期声明，静默期基准原样保留。
    pub(crate) fn clear_stale_claims(&mut self) {
        self.release();
        self.release_lease();
    }
}

#[cfg(test)]
mod tests {
    use super::CurtainState;

    const NOW: u64 = 1_000;

    /// 迁移前的两种极性：声明位全置 / 全清，静默期基准都取与 `NOW` 不同的值。
    /// 迁移多碰任何一个字段（无论改成真还是改成假），总有一个起点会在整体比较里露出来。
    fn both_polarities() -> [CurtainState; 2] {
        [
            CurtainState {
                active: true,
                auto_engaged: true,
                last_physical_input_ms: 7,
                pending_auto_unlock: true,
            },
            CurtainState {
                active: false,
                auto_engaged: false,
                last_physical_input_ms: 7,
                pending_auto_unlock: false,
            },
        ]
    }

    /// 对每个起点施加 `transition`，断言结果恰好是「只有 `changed` 描述的字段变了」。
    fn assert_changes_only(
        transition: impl Fn(&mut CurtainState),
        changed: impl Fn(CurtainState) -> CurtainState,
    ) {
        for before in both_polarities() {
            let mut after = before.clone();
            transition(&mut after);
            assert_eq!(after, changed(before.clone()), "from {before:?}");
        }
    }

    #[test]
    fn a_manual_engage_is_not_an_auto_curtain_and_leaves_the_lease_alone() {
        assert_changes_only(
            |state| state.engage_manually(NOW),
            |before| CurtainState {
                active: true,
                auto_engaged: false,
                last_physical_input_ms: NOW,
                ..before
            },
        );
    }

    /// 锁屏不是帷幕上的物理输入：自动拉起若把它记成静默期起点，锁屏后 5 分钟内
    /// 手机派发的任务都会被挡在屏幕外。
    #[test]
    fn an_automatic_engage_keeps_the_physical_input_timestamp_and_the_lease() {
        assert_changes_only(CurtainState::engage_automatically, |before| CurtainState {
            active: true,
            auto_engaged: true,
            ..before
        });
    }

    /// 租约位是屏幕被 server 解锁期间让帷幕续跑的电平，只在回锁确认后由 `release_lease` 清除；
    /// 收起时顺手清掉，会让帷幕在 server 仍在代为操作时被提前放行。
    #[test]
    fn a_release_keeps_the_lease_and_the_physical_input_timestamp() {
        assert_changes_only(CurtainState::release, |before| CurtainState {
            active: false,
            auto_engaged: false,
            ..before
        });
    }

    #[test]
    fn releasing_the_lease_touches_nothing_else() {
        assert_changes_only(CurtainState::release_lease, |before| CurtainState {
            pending_auto_unlock: false,
            ..before
        });
    }

    #[test]
    fn a_physical_input_only_moves_the_timestamp() {
        assert_changes_only(
            |state| state.record_physical_input(NOW),
            |before| CurtainState {
                last_physical_input_ms: NOW,
                ..before
            },
        );
    }

    /// 过期声明恰是三个声明位；静默期基准是时间戳，留着它不算过期声明。
    #[test]
    fn stale_claims_are_the_three_claim_flags_and_not_the_timestamp() {
        assert!(!CurtainState::default().has_stale_claims());
        assert!(!CurtainState {
            last_physical_input_ms: NOW,
            ..CurtainState::default()
        }
        .has_stale_claims());
        for claimed in [
            CurtainState {
                active: true,
                ..CurtainState::default()
            },
            CurtainState {
                auto_engaged: true,
                ..CurtainState::default()
            },
            CurtainState {
                pending_auto_unlock: true,
                ..CurtainState::default()
            },
        ] {
            assert!(claimed.has_stale_claims(), "{claimed:?}");
        }
    }

    #[test]
    fn clearing_stale_claims_keeps_the_physical_input_timestamp() {
        assert_changes_only(CurtainState::clear_stale_claims, |before| CurtainState {
            active: false,
            auto_engaged: false,
            pending_auto_unlock: false,
            ..before
        });
        for mut state in both_polarities() {
            state.clear_stale_claims();
            assert!(!state.has_stale_claims());
        }
    }
}
