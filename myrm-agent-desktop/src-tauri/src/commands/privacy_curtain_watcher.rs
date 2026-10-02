//! 工位防窥帷幕——锁屏 watcher 状态机。
//!
//! 独立线程 1s tick：锁屏即自动拉帷幕、用户解锁即自动收（auto 帷幕）、
//! server 代解锁（pending 标记）保持帷幕续跑、显示器热插拔幂等重建。
//! 配置开关缓存 30s 刷新（ConfigManager::load 每次读盘并打日志，
//! 每 tick 调用会造成秒级日志刷屏）。
//!
//! [INPUT]
//! - tauri AppHandle (POS: 窗口/事件/app data 目录)
//! - commands::privacy_curtain 内部状态桥与窗口 API (POS: 状态读写/窗口重建)
//! - utils::screen_lock (POS: 锁屏检测)
//! - config::ConfigManager (POS: privacy_curtain_enabled 开关)
//!
//! [OUTPUT]
//! - spawn_privacy_curtain_watcher（app/setup.rs 启动时 spawn 一次）
//!
//! [POS]
//! watcher 是帷幕状态流转的唯一驱动者，但绝不干涉手动帷幕
//! （auto_engaged=false 仅显式命令收起，见 commands/privacy_curtain.rs）。

use tauri::{AppHandle, Manager};

use crate::commands::privacy_curtain::{
    close_curtain_windows, curtain_windows, deploy_curtain_windows, log_audit, mutate_state,
    now_ms, read_state,
};
use crate::utils::screen_lock;

const WATCHER_TICK_MS: u64 = 1000;
/// 配置开关缓存刷新间隔（tick 数）：30s 内开关变更生效。
const CONFIG_REFRESH_TICKS: u64 = 30;

fn curtain_enabled(app: &AppHandle) -> bool {
    app.try_state::<crate::config::ConfigManager>()
        .map(|manager| manager.load().privacy_curtain_enabled)
        .unwrap_or(false)
}

/// 锁屏触发的帷幕状态机（1s tick）：
/// - locked 且帷幕未拉 → 自动拉起（auto_engaged=true，静默期基准初始化）；
/// - unlocked 且 pending_auto_unlock → server 代解锁，保持帷幕并消费标记；
/// - unlocked 且 auto 帷幕在（无 pending）→ 用户本人解锁，收起帷幕；
/// - 手动帷幕（auto_engaged=false）与未启用开关时不干涉；
/// - 帷幕在且显示器数量变化 → 幂等重建（热插拔跟随）。
pub fn spawn_privacy_curtain_watcher(app: AppHandle) {
    std::thread::spawn(move || {
        let mut cached_enabled = curtain_enabled(&app);
        let mut tick: u64 = 0;
        loop {
            std::thread::sleep(std::time::Duration::from_millis(WATCHER_TICK_MS));
            tick = tick.wrapping_add(1);
            if tick % CONFIG_REFRESH_TICKS == 0 {
                cached_enabled = curtain_enabled(&app);
            }

            let enabled = cached_enabled;
            let state = read_state(&app);
            let windows = curtain_windows(&app);

            if !enabled {
                if state.active || !windows.is_empty() {
                    close_curtain_windows(&app);
                    mutate_state(&app, |s| {
                        s.active = false;
                        s.auto_engaged = false;
                    });
                    log_audit("auto_release", true, "curtain disabled");
                }
                continue;
            }

            let locked = screen_lock::is_screen_locked();

            if locked && !state.active && windows.is_empty() {
                match deploy_curtain_windows(&app) {
                    Ok(()) => {
                        mutate_state(&app, |s| {
                            s.active = true;
                            s.auto_engaged = true;
                            s.last_physical_input_ms = now_ms();
                        });
                        log_audit("auto_engage", true, "screen locked");
                    }
                    Err(reason) => log_audit("auto_engage", false, &reason),
                }
                continue;
            }

            if !locked {
                if state.pending_auto_unlock {
                    mutate_state(&app, |s| {
                        s.pending_auto_unlock = false;
                    });
                    log_audit("keep_on_unlock", true, "server-initiated unlock");
                } else if state.auto_engaged {
                    close_curtain_windows(&app);
                    mutate_state(&app, |s| {
                        s.active = false;
                        s.auto_engaged = false;
                    });
                    log_audit("auto_release", true, "user unlocked");
                }
                continue;
            }

            // locked 且帷幕已拉：显示器热插拔跟随（数量不一致才重建，避免闪烁）。
            let monitor_count = app
                .available_monitors()
                .map(|monitors| monitors.len())
                .unwrap_or(windows.len());
            if !windows.is_empty() && windows.len() != monitor_count {
                match deploy_curtain_windows(&app) {
                    Ok(()) => log_audit("rebuild", true, "display layout changed"),
                    Err(reason) => log_audit("rebuild", false, &reason),
                }
            }
        }
    });
}
