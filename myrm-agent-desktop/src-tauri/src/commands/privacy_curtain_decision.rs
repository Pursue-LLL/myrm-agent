//! 工位防窥帷幕——锁屏 watcher 的纯决策表。
//!
//! [INPUT]
//! - commands::privacy_curtain_state::CurtainState (POS: 帷幕状态桥的状态结构)
//!
//! [OUTPUT]
//! - TickFacts / TickAction / decide: 一个 tick 观测到的外部事实 → 应执行的动作
//! - needs_monitor_count: 显示器数量的查询条件
//!
//! [POS]
//! 纯函数、不依赖 Tauri：状态机因此可脱离窗口与状态文件单测。副作用（窗口 / 状态文件）
//! 由 privacy_curtain_watcher.rs 的循环按决策结果执行；决策只取决于文件与外部事实、不带任何
//! 记忆，所以状态没记下的动作下个 tick 会被同样的决策重做。

use crate::commands::privacy_curtain_state::CurtainState;

/// 一个 tick 观测到的全部外部事实（[`decide`] 的唯一输入）。
pub(super) struct TickFacts<'a> {
    pub(super) enabled: bool,
    pub(super) locked: bool,
    pub(super) state: &'a CurtainState,
    pub(super) window_count: usize,
    pub(super) monitor_count: usize,
}

/// 一个 tick 应执行的动作；纯数据，副作用留给调用方。
#[derive(Debug, PartialEq, Eq)]
pub(super) enum TickAction {
    Idle,
    /// 开关已关：收起残留帷幕与状态。
    ReleaseDisabled,
    /// 锁屏且帷幕未拉：自动拉起。
    Engage,
    /// 屏幕已解锁且无人持有租约：用户本人解锁，收起 auto 帷幕。
    ReleaseOnUserUnlock,
    /// 帷幕在且显示器数量变化：幂等重建。
    Rebuild,
}

/// 锁屏触发的帷幕状态机（1s tick）：
/// - 开关关闭 → 收起残留；
/// - locked 且帷幕未拉 → 自动拉起；
/// - unlocked 且 pending_auto_unlock → server 持有代解锁租约（**电平**，
///   由 server 在确认回锁后清除，壳不消费），保持帷幕；
/// - unlocked 且 auto 帷幕在（租约已交还）→ 用户本人解锁，收起帷幕；
/// - 手动帷幕（auto_engaged=false）不干涉；
/// - locked 或持有租约时帷幕在、显示器数量变化 → 幂等重建（热插拔跟随）：
///   持租约期间屏幕是解锁的，帷幕是唯一遮蔽，新接入的显示器必须立即被盖住。
pub(super) fn decide(facts: &TickFacts) -> TickAction {
    let state = facts.state;
    if !facts.enabled {
        return if state.active || facts.window_count > 0 {
            TickAction::ReleaseDisabled
        } else {
            TickAction::Idle
        };
    }
    if facts.locked && !state.active && facts.window_count == 0 {
        return TickAction::Engage;
    }
    if !facts.locked && !state.pending_auto_unlock {
        return if state.auto_engaged {
            TickAction::ReleaseOnUserUnlock
        } else {
            TickAction::Idle
        };
    }
    if facts.window_count > 0 && facts.window_count != facts.monitor_count {
        return TickAction::Rebuild;
    }
    TickAction::Idle
}

/// 本 tick 是否需要比对显示器数量：只有重建会用到，且仅在 locked 或持租约时可能触发。
pub(super) fn needs_monitor_count(locked: bool, state: &CurtainState, window_count: usize) -> bool {
    window_count > 0 && (locked || state.pending_auto_unlock)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn facts(state: &CurtainState) -> TickFacts<'_> {
        TickFacts {
            enabled: true,
            locked: false,
            state,
            window_count: 0,
            monitor_count: 0,
        }
    }

    fn auto_curtain(pending: bool) -> CurtainState {
        CurtainState {
            active: true,
            auto_engaged: true,
            pending_auto_unlock: pending,
            ..CurtainState::default()
        }
    }

    #[test]
    fn disabled_with_nothing_up_is_idle() {
        let state = CurtainState::default();
        let mut f = facts(&state);
        f.enabled = false;
        assert_eq!(decide(&f), TickAction::Idle);
    }

    #[test]
    fn disabled_releases_active_state() {
        let state = auto_curtain(false);
        let mut f = facts(&state);
        f.enabled = false;
        assert_eq!(decide(&f), TickAction::ReleaseDisabled);
    }

    #[test]
    fn disabled_releases_orphan_windows_even_if_state_is_clear() {
        let state = CurtainState::default();
        let mut f = facts(&state);
        f.enabled = false;
        f.window_count = 2;
        assert_eq!(decide(&f), TickAction::ReleaseDisabled);
    }

    #[test]
    fn locked_screen_without_curtain_engages() {
        let state = CurtainState::default();
        let mut f = facts(&state);
        f.locked = true;
        assert_eq!(decide(&f), TickAction::Engage);
    }

    #[test]
    fn locked_screen_with_matching_windows_is_idle() {
        let state = auto_curtain(false);
        let mut f = facts(&state);
        f.locked = true;
        f.window_count = 2;
        f.monitor_count = 2;
        assert_eq!(decide(&f), TickAction::Idle);
    }

    #[test]
    fn display_layout_change_rebuilds() {
        let state = auto_curtain(false);
        let mut f = facts(&state);
        f.locked = true;
        f.window_count = 1;
        f.monitor_count = 2;
        assert_eq!(decide(&f), TickAction::Rebuild);
    }

    #[test]
    fn user_unlock_releases_auto_curtain() {
        let state = auto_curtain(false);
        assert_eq!(decide(&facts(&state)), TickAction::ReleaseOnUserUnlock);
    }

    /// 持租约期间屏幕是解锁的、帷幕是唯一遮蔽：此时接入新显示器必须立刻重建补上。
    #[test]
    fn display_hotplug_during_held_lease_rebuilds_curtain() {
        let state = auto_curtain(true);
        let mut f = facts(&state);
        f.window_count = 1;
        f.monitor_count = 2;
        assert_eq!(decide(&f), TickAction::Rebuild);
    }

    #[test]
    fn matching_layout_during_held_lease_stays_idle() {
        let state = auto_curtain(true);
        let mut f = facts(&state);
        f.window_count = 2;
        f.monitor_count = 2;
        assert_eq!(decide(&f), TickAction::Idle);
    }

    /// 租约已交还时用户本人解锁优先：收起帷幕，不为即将消失的帷幕重建。
    #[test]
    fn returned_lease_prefers_release_over_rebuild_when_unlocked() {
        let state = auto_curtain(false);
        let mut f = facts(&state);
        f.window_count = 1;
        f.monitor_count = 2;
        assert_eq!(decide(&f), TickAction::ReleaseOnUserUnlock);
    }

    /// 用户在场时的手动帷幕不受 watcher 干涉，显示器变化也不重建。
    #[test]
    fn manual_curtain_ignores_layout_change_while_unlocked() {
        let state = CurtainState {
            active: true,
            auto_engaged: false,
            ..CurtainState::default()
        };
        let mut f = facts(&state);
        f.window_count = 1;
        f.monitor_count = 2;
        assert_eq!(decide(&f), TickAction::Idle);
    }

    #[test]
    fn monitor_count_is_only_queried_when_a_rebuild_is_possible() {
        let held = auto_curtain(true);
        let returned = auto_curtain(false);
        assert!(needs_monitor_count(true, &returned, 1));
        assert!(needs_monitor_count(false, &held, 1));
        assert!(!needs_monitor_count(false, &returned, 1));
        assert!(!needs_monitor_count(true, &held, 0));
    }

    /// 租约是电平：server 持有期间屏幕处于解锁态，每个 tick 都必须保持帷幕，
    /// 不能像脉冲那样被首个 tick 消费后收起（屏幕内容裸奔）。
    #[test]
    fn held_lease_keeps_curtain_on_every_unlocked_tick() {
        let state = auto_curtain(true);
        for _ in 0..100 {
            assert_eq!(decide(&facts(&state)), TickAction::Idle);
        }
    }

    /// 租约交还（server 确认回锁后清位）后屏幕若处于解锁态，即用户本人解锁。
    #[test]
    fn returned_lease_then_unlocked_screen_means_user_unlock() {
        let state = auto_curtain(false);
        assert_eq!(decide(&facts(&state)), TickAction::ReleaseOnUserUnlock);
    }

    #[test]
    fn manual_curtain_is_never_released_by_unlock() {
        let state = CurtainState {
            active: true,
            auto_engaged: false,
            ..CurtainState::default()
        };
        assert_eq!(decide(&facts(&state)), TickAction::Idle);
    }

    #[test]
    fn unlocked_screen_without_curtain_is_idle() {
        let state = CurtainState::default();
        assert_eq!(decide(&facts(&state)), TickAction::Idle);
    }

    /// 状态没记下时文件原样保留，副作用要么已完成（窗口已收起）要么已撤销（窗口已撤）：
    /// 下个 tick 的事实让 decide 再次选中同一个动作，失败因此在下一轮自动补做，apply 不需要重试记忆。
    #[test]
    fn an_action_whose_state_was_not_recorded_is_decided_again_next_tick() {
        let still_claims_curtain = auto_curtain(false);
        let untouched = CurtainState::default();
        let cases = [
            (
                TickAction::ReleaseDisabled,
                false,
                false,
                &still_claims_curtain,
            ),
            (
                TickAction::ReleaseOnUserUnlock,
                true,
                false,
                &still_claims_curtain,
            ),
            (TickAction::Engage, true, true, &untouched),
        ];
        for (action, enabled, locked, state) in cases {
            let mut next_tick = facts(state);
            next_tick.enabled = enabled;
            next_tick.locked = locked;
            assert_eq!(decide(&next_tick), action);
        }
    }
}
