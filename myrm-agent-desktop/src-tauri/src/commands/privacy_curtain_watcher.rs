//! 工位防窥帷幕——锁屏 watcher 状态机。
//!
//! 独立线程 1s tick：锁屏即自动拉帷幕、用户解锁即自动收（auto 帷幕）、
//! server 持有代解锁租约（pending 电平）期间保持帷幕续跑、显示器热插拔幂等重建
//! （锁屏态与持租约态均跟随，后者屏幕已解锁，漏盖一块显示器即是裸露）。
//! 配置开关缓存 30s 刷新（ConfigManager::load 每次读盘并打日志，
//! 每 tick 调用会造成秒级日志刷屏）。每个 tick 的决策是纯函数 `decide`（见 privacy_curtain_decision.rs），
//! 副作用（窗口/状态文件）由循环按决策结果执行，状态机因此可脱离 Tauri 单测。
//!
//! [INPUT]
//! - tauri AppHandle (POS: 窗口/事件/app data 目录)
//! - commands::privacy_curtain_state (POS: 帷幕状态桥，curtain_state.json 的 Tauri 侧唯一读写入口)
//! - commands::privacy_curtain_state_changes (POS: 状态的具名迁移：自动拉起 / 启动清理过期声明)
//! - commands::privacy_curtain_decision (POS: 每个 tick 的纯决策表)
//! - commands::privacy_curtain_transition (POS: 拉起 / 收起帷幕时窗口与状态的固定顺序及其失败收敛)
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
    audit_result, close_curtain_windows, curtain_windows, deploy_curtain_windows, log_audit,
};
use crate::commands::privacy_curtain_decision::{
    decide, needs_monitor_count, TickAction, TickFacts,
};
use crate::commands::privacy_curtain_state::{
    mutate_state, reset_state, try_read_state, CurtainState,
};
use crate::commands::privacy_curtain_transition::{raise_curtain, record_release};
use crate::utils::screen_lock;

const WATCHER_TICK_MS: u64 = 1000;
/// 配置开关缓存刷新间隔（tick 数）：30s 内开关变更生效。
const CONFIG_REFRESH_TICKS: u64 = 30;

fn curtain_enabled(app: &AppHandle) -> bool {
    app.try_state::<crate::config::ConfigManager>()
        .map(|manager| manager.load().privacy_curtain_enabled)
        .unwrap_or(false)
}

/// 全新进程没有任何帷幕窗口：上一进程遗留的 active/auto/pending 声明都是过期事实。
/// 不清掉则 active 残留会阻断下次自动拉起，pending 残留会让用户本人的解锁
/// 永远无法收起帷幕。
fn reset_stale_state(app: &AppHandle) {
    let Some(state) = try_read_state(app) else {
        // 读不到就无从知道哪些声明过期；新进程里它们按定义全是过期事实，
        // 整文件重写是文件持续读不到时唯一能自愈的路径。
        log_audit("boot_reset", reset_state(app), "state file unreadable");
        return;
    };
    if state.has_stale_claims() {
        let cleared = mutate_state(app, CurtainState::clear_stale_claims);
        log_audit("boot_reset", cleared, "stale state from previous run");
    }
}

pub fn spawn_privacy_curtain_watcher(app: AppHandle) {
    std::thread::spawn(move || {
        reset_stale_state(&app);
        let mut cached_enabled = curtain_enabled(&app);
        let mut tick: u64 = 0;
        let mut state_unreadable = false;
        loop {
            std::thread::sleep(std::time::Duration::from_millis(WATCHER_TICK_MS));
            tick = tick.wrapping_add(1);
            if tick.is_multiple_of(CONFIG_REFRESH_TICKS) {
                cached_enabled = curtain_enabled(&app);
            }

            let Some(state) = try_read_state(&app) else {
                // 读不到就没有事实可依：拿默认值决策会收起一个真实存在的帷幕。决策表是电平触发的，
                // 状态恢复可读后的下一个 tick 自然补做；持续读不到时只在首个 tick 记审计，免得每秒刷屏。
                if !state_unreadable {
                    log_audit(
                        "state_read",
                        false,
                        "curtain state unreadable, ticks skipped",
                    );
                }
                state_unreadable = true;
                continue;
            };
            state_unreadable = false;
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

/// 执行一个 tick 的决策。任何动作的状态没记下时文件都原样保留，决策又只取决于文件与外部事实，
/// 所以失败的动作下个 tick 会被同样的决策重做：收起类已先收窗口，只剩补记状态；
/// 拉起类已撤销窗口，整个动作重来。
fn apply(app: &AppHandle, action: &TickAction) {
    match action {
        TickAction::Idle => {}
        TickAction::ReleaseDisabled => {
            close_curtain_windows(app);
            audit_result("auto_release", "curtain disabled", &record_release(app));
        }
        TickAction::Engage => {
            let raised = raise_curtain(
                || deploy_curtain_windows(app),
                || mutate_state(app, CurtainState::engage_automatically),
                || close_curtain_windows(app),
            );
            audit_result("auto_engage", "screen locked", &raised);
        }
        TickAction::ReleaseOnUserUnlock => {
            close_curtain_windows(app);
            audit_result("auto_release", "user unlocked", &record_release(app));
        }
        TickAction::Rebuild => match deploy_curtain_windows(app) {
            Ok(()) => log_audit("rebuild", true, "display layout changed"),
            Err(reason) => log_audit("rebuild", false, &reason),
        },
    }
}
