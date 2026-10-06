//! 工位防窥帷幕——锁屏 watcher 状态机。
//!
//! 独立线程 1s tick：锁屏即自动拉帷幕、用户解锁即自动收（auto 帷幕）、
//! server 持有代解锁租约（pending 电平）期间保持帷幕续跑、显示器热插拔幂等重建
//! （锁屏态与持租约态均跟随，后者屏幕已解锁，漏盖一块显示器即是裸露）。
//! 配置开关缓存 30s 刷新（ConfigManager::load 每次读盘并打日志，
//! 每 tick 调用会造成秒级日志刷屏）。每个 tick 的决策是纯函数 [`decide`]，
//! 副作用（窗口/状态文件）由循环按决策结果执行，状态机因此可脱离 Tauri 单测。
//!
//! [INPUT]
//! - tauri AppHandle (POS: 窗口/事件/app data 目录)
//! - commands::privacy_curtain_state (POS: 帷幕状态桥，curtain_state.json 的 Tauri 侧唯一读写入口)
//! - commands::privacy_curtain 窗口 API (POS: 帷幕窗口重建/销毁)
//! - utils::screen_lock (POS: 锁屏检测)
//! - config::ConfigManager (POS: privacy_curtain_enabled 开关)
//!
//! [OUTPUT]
//! - spawn_privacy_curtain_watcher（app/setup.rs 启动时 spawn 一次）
//!
//! [POS]
//! watcher 是帷幕状态流转的唯一驱动者，但绝不干涉手动帷幕
//! （auto_engaged=false 仅显式命令收起，见 commands/privacy_curtain.rs）。
//! 全新进程没有任何帷幕窗口，启动时清掉上一进程遗留的状态声明。

use tauri::{AppHandle, Manager};

use crate::commands::privacy_curtain::{
    close_curtain_windows, curtain_windows, deploy_curtain_windows, log_audit, now_ms,
};
use crate::commands::privacy_curtain_state::{mutate_state, read_state, CurtainState};
use crate::utils::screen_lock;

const WATCHER_TICK_MS: u64 = 1000;
/// 配置开关缓存刷新间隔（tick 数）：30s 内开关变更生效。
const CONFIG_REFRESH_TICKS: u64 = 30;

fn curtain_enabled(app: &AppHandle) -> bool {
    app.try_state::<crate::config::ConfigManager>()
        .map(|manager| manager.load().privacy_curtain_enabled)
        .unwrap_or(false)
}

/// 一个 tick 观测到的全部外部事实（[`decide`] 的唯一输入）。
struct TickFacts<'a> {
    enabled: bool,
    locked: bool,
    state: &'a CurtainState,
    window_count: usize,
    monitor_count: usize,
}

/// 一个 tick 应执行的动作；纯数据，副作用留给调用方。
#[derive(Debug, PartialEq, Eq)]
enum TickAction {
    Idle,
    /// 开关已关：收起残留帷幕与状态。
    ReleaseDisabled,
    /// 锁屏且帷幕未拉：自动拉起（静默期基准初始化）。
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
fn decide(facts: &TickFacts) -> TickAction {
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
fn needs_monitor_count(locked: bool, state: &CurtainState, window_count: usize) -> bool {
    window_count > 0 && (locked || state.pending_auto_unlock)
}

/// 全新进程没有任何帷幕窗口：上一进程遗留的 active/auto/pending 声明都是过期事实。
/// 不清掉则 active 残留会阻断下次自动拉起，pending 残留会让用户本人的解锁
/// 永远无法收起帷幕。
fn reset_stale_state(app: &AppHandle) {
    let state = read_state(app);
    if state.active || state.auto_engaged || state.pending_auto_unlock {
        mutate_state(app, |s| {
            s.active = false;
            s.auto_engaged = false;
            s.pending_auto_unlock = false;
        });
        log_audit("boot_reset", true, "stale state from previous run");
    }
}

pub fn spawn_privacy_curtain_watcher(app: AppHandle) {
    std::thread::spawn(move || {
        reset_stale_state(&app);
        let mut cached_enabled = curtain_enabled(&app);
        let mut tick: u64 = 0;
        loop {
            std::thread::sleep(std::time::Duration::from_millis(WATCHER_TICK_MS));
            tick = tick.wrapping_add(1);
            if tick.is_multiple_of(CONFIG_REFRESH_TICKS) {
                cached_enabled = curtain_enabled(&app);
            }

            let state = read_state(&app);
            let window_count = curtain_windows(&app).len();
            // 开关关闭时不探测（探测只为帷幕服务）；显示器数量仅在需要比对时查询。
            let locked = cached_enabled && screen_lock::is_screen_locked();
            let monitor_count = if needs_monitor_count(locked, &state, window_count) {
                app.available_monitors()
                    .map(|monitors| monitors.len())
                    .unwrap_or(window_count)
            } else {
                window_count
            };

            let action = decide(&TickFacts {
                enabled: cached_enabled,
                locked,
                state: &state,
                window_count,
                monitor_count,
            });
            apply(&app, &action);
        }
    });
}

fn apply(app: &AppHandle, action: &TickAction) {
    match action {
        TickAction::Idle => {}
        TickAction::ReleaseDisabled => {
            close_curtain_windows(app);
            mutate_state(app, |s| {
                s.active = false;
                s.auto_engaged = false;
            });
            log_audit("auto_release", true, "curtain disabled");
        }
        TickAction::Engage => match deploy_curtain_windows(app) {
            Ok(()) => {
                mutate_state(app, |s| {
                    s.active = true;
                    s.auto_engaged = true;
                    s.last_physical_input_ms = now_ms();
                });
                log_audit("auto_engage", true, "screen locked");
            }
            Err(reason) => log_audit("auto_engage", false, &reason),
        },
        TickAction::ReleaseOnUserUnlock => {
            close_curtain_windows(app);
            mutate_state(app, |s| {
                s.active = false;
                s.auto_engaged = false;
            });
            log_audit("auto_release", true, "user unlocked");
        }
        TickAction::Rebuild => match deploy_curtain_windows(app) {
            Ok(()) => log_audit("rebuild", true, "display layout changed"),
            Err(reason) => log_audit("rebuild", false, &reason),
        },
    }
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
}
