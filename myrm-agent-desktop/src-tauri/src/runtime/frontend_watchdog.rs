//! Next.js 前端 Sidecar 看护
//!
//! [INPUT]
//! - runtime::NextJSFrontend (POS: 前端子进程句柄)
//! - config::{ConfigManager, FrontendConfig} (POS: 重启时读取最新端口配置)
//!
//! [OUTPUT]
//! - spawn_frontend_watchdog / FrontendWatchdogHandle: 前端崩溃或假死后的指数退避重启
//! - 前端崩溃/恢复/崩溃循环事件（frontend-crash / frontend-restarted / frontend-crash-loop）
//!
//! [POS]
//! 桌面端前端进程的运行时看护。后端有 watchdog，前端此前只有启动时一次 try_wait：
//! 进程一旦退出或端口假死，WebView 就停在白屏/连接失败页，用户只能重启整个应用。
//! 这里补齐与后端同构的「检测 → 退避 → 重启」闭环，并在连续失败时交给托盘告警。

use std::time::{Duration, Instant};

use tauri::{async_runtime::JoinHandle, AppHandle, Emitter, Manager};
use tokio::sync::watch;

use crate::config::{ConfigManager, FrontendConfig};
use crate::runtime::NextJSFrontend;

const HEALTH_CHECK_INTERVAL: Duration = Duration::from_secs(10);
const HEALTH_TIMEOUT: Duration = Duration::from_secs(3);
const HUNG_CHECKS_BEFORE_RESTART: u8 = 3;
const RESTART_DELAYS: [Duration; 3] = [
    Duration::from_secs(5),
    Duration::from_secs(15),
    Duration::from_secs(60),
];
const RESTART_WINDOW: Duration = Duration::from_secs(300);
const MAX_RESTARTS_IN_WINDOW: usize = 3;

/// 前端看护任务句柄；停机前必须 cancel，避免把主动停止当成崩溃而重启。
pub struct FrontendWatchdogHandle {
    _task: JoinHandle<()>,
    cancel_tx: watch::Sender<bool>,
}

impl FrontendWatchdogHandle {
    pub fn cancel(&self) {
        let _ = self.cancel_tx.send(true);
    }
}

/// 启动前端看护；调用方保证同一时刻只有一个看护任务。
pub fn spawn_frontend_watchdog(
    app: &AppHandle,
    initial_config: FrontendConfig,
) -> FrontendWatchdogHandle {
    let app_handle = app.clone();
    let (cancel_tx, cancel_rx) = watch::channel(false);
    let task = tauri::async_runtime::spawn(async move {
        run_watchdog(app_handle, initial_config, cancel_rx).await;
    });
    FrontendWatchdogHandle {
        _task: task,
        cancel_tx,
    }
}

async fn run_watchdog(
    app: AppHandle,
    initial_config: FrontendConfig,
    mut cancel_rx: watch::Receiver<bool>,
) {
    let client = match reqwest::Client::builder().timeout(HEALTH_TIMEOUT).build() {
        Ok(client) => client,
        Err(error) => {
            eprintln!("[frontend-watchdog] Failed to build health client: {error}");
            return;
        }
    };
    let mut restart_timestamps: Vec<Instant> = Vec::new();
    let mut last_error = String::new();
    let mut hung_checks = 0u8;

    loop {
        tokio::select! {
            _ = tokio::time::sleep(HEALTH_CHECK_INTERVAL) => {}
            changed = cancel_rx.changed() => {
                if changed.is_err() || *cancel_rx.borrow_and_update() {
                    println!("[frontend-watchdog] Cancelled by graceful shutdown");
                    return;
                }
            }
        }

        if *cancel_rx.borrow() {
            return;
        }

        let config = current_config(&app, &initial_config);
        let alive = frontend_alive(&app);
        if alive && http_ready(&client, &config).await {
            hung_checks = 0;
            continue;
        }

        if alive {
            hung_checks += 1;
            if hung_checks < HUNG_CHECKS_BEFORE_RESTART {
                continue;
            }
            println!(
                "[frontend-watchdog] Frontend alive but unresponsive for {} checks; restarting",
                hung_checks
            );
        } else {
            println!("[frontend-watchdog] Frontend process exited unexpectedly");
        }
        hung_checks = 0;

        stop_frontend_tree(&app);
        update_tray_status(&app, "restarting");
        let _ = app.emit("frontend-crash", ());

        restart_timestamps.retain(|timestamp| timestamp.elapsed() < RESTART_WINDOW);
        if restart_timestamps.len() >= MAX_RESTARTS_IN_WINDOW {
            eprintln!(
                "[frontend-watchdog] Frontend crashed {} times in {:?}, giving up auto-restart",
                MAX_RESTARTS_IN_WINDOW, RESTART_WINDOW
            );
            update_tray_status(&app, "error");
            let _ = app.emit("frontend-crash-loop", &last_error);
            return;
        }

        let delay_idx = restart_timestamps.len().min(RESTART_DELAYS.len() - 1);
        let delay = RESTART_DELAYS[delay_idx];
        println!("[frontend-watchdog] Restarting frontend in {:?}...", delay);

        tokio::select! {
            _ = tokio::time::sleep(delay) => {}
            changed = cancel_rx.changed() => {
                if changed.is_err() || *cancel_rx.borrow_and_update() {
                    return;
                }
            }
        }
        if *cancel_rx.borrow() {
            return;
        }

        let frontend_state = app.state::<NextJSFrontend>();
        let frontend_port = config.port;
        match crate::runtime::start_frontend(app.clone(), frontend_state, config).await {
            Ok(_) => {
                println!("[frontend-watchdog] Frontend restarted successfully");
                // A restarted server does not revive the WebView by itself: it is still
                // showing the old connection-error page. Navigate back so recovery is
                // visible without asking the user to reload.
                if let Some(window) = app.get_webview_window("main") {
                    if let Ok(url) =
                        format!("http://127.0.0.1:{frontend_port}/").parse::<tauri::Url>()
                    {
                        if let Err(error) = window.navigate(url) {
                            eprintln!(
                                "[frontend-watchdog] Failed to navigate after restart: {error}"
                            );
                        }
                    }
                }
                restart_timestamps.push(Instant::now());
                last_error.clear();
                update_tray_status(&app, "idle");
                let _ = app.emit("frontend-restarted", ());
            }
            Err(error) => {
                eprintln!("[frontend-watchdog] Failed to restart frontend: {error}");
                last_error = error;
                restart_timestamps.push(Instant::now());
                update_tray_status(&app, "error");
            }
        }
    }
}

fn current_config(app: &AppHandle, fallback: &FrontendConfig) -> FrontendConfig {
    app.try_state::<ConfigManager>()
        .map(|manager| FrontendConfig::from_system_config(&manager.load()))
        .unwrap_or_else(|| fallback.clone())
}

fn frontend_alive(app: &AppHandle) -> bool {
    let frontend = app.state::<NextJSFrontend>();
    let mut guard = frontend.process.lock().unwrap();
    match guard.as_mut() {
        Some(child) => match child.try_wait() {
            Ok(None) => true,
            Ok(Some(_)) => {
                *guard = None;
                false
            }
            Err(_) => false,
        },
        None => false,
    }
}

fn stop_frontend_tree(app: &AppHandle) {
    let frontend = app.state::<NextJSFrontend>();
    let mut guard = frontend.process.lock().unwrap();
    if let Some(mut child) = guard.take() {
        let pid = child.id();
        crate::utils::process_tree::kill_process_tree(pid);
        let _ = child.kill();
        println!(
            "[frontend-watchdog] Stopped unresponsive frontend tree (PID: {})",
            pid
        );
    }
}

async fn http_ready(client: &reqwest::Client, config: &FrontendConfig) -> bool {
    // A wildcard bind is not a connectable address; probe loopback instead.
    let host = if config.host == "0.0.0.0" {
        "127.0.0.1"
    } else {
        config.host.as_str()
    };
    let url = format!("http://{}:{}/", host, config.port);
    matches!(client.get(&url).send().await, Ok(response) if response.status().is_success())
}

fn update_tray_status(app: &AppHandle, status: &str) {
    let tooltip = match status {
        "restarting" => "MyrmAgent - 界面重启中...",
        "error" => "MyrmAgent - 界面异常，请重启应用",
        "idle" => "MyrmAgent - 空闲",
        _ => "MyrmAgent",
    };
    crate::app::update_native_tray_status(app, status, tooltip);
}
