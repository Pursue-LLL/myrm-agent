//! 后端 Sidecar 健康监控与崩溃自动恢复
//!
//! [INPUT]
//! - PythonBackend (POS: 后端进程引用)
//! - ConfigManager (POS: 端口配置)
//! - CancellationToken (用于 graceful_shutdown 协调)
//!
//! [OUTPUT]
//! - 周期性健康检查 (30s)
//! - 崩溃检测 + 指数退避重启 (5s/15s/60s, 5min 内最多 3 次)
//! - Tray tooltip 状态更新 + 前端事件通知 (backend-crash-loop 携带错误消息 payload)
//!
//! [POS]
//! 确保后端 Sidecar 在意外崩溃后自动恢复，用户无感知。
//! 仅在进程意外退出时触发，不干预正常的 graceful_shutdown。

use std::time::{Duration, Instant};

use tauri::{async_runtime::JoinHandle, AppHandle, Emitter, Manager};
use tokio::sync::watch;

use crate::config::{BackendConfig, ConfigManager};
use crate::runtime::PythonBackend;

const HEALTH_CHECK_INTERVAL: Duration = Duration::from_secs(30);
const RESTART_DELAYS: [Duration; 3] = [
    Duration::from_secs(5),
    Duration::from_secs(15),
    Duration::from_secs(60),
];
const RESTART_WINDOW: Duration = Duration::from_secs(300);
const MAX_RESTARTS_IN_WINDOW: usize = 3;

/// Watchdog handle returned to caller for lifecycle coordination.
pub struct WatchdogHandle {
    _task: JoinHandle<()>,
    cancel_tx: watch::Sender<bool>,
}

impl WatchdogHandle {
    /// Cancel the watchdog (called during graceful shutdown).
    pub fn cancel(&self) {
        let _ = self.cancel_tx.send(true);
    }
}

/// Spawn a watchdog task that monitors backend health and auto-restarts on crash.
pub fn spawn_watchdog(app: &AppHandle, port: u16) -> WatchdogHandle {
    let app_handle = app.clone();
    let (cancel_tx, cancel_rx) = watch::channel(false);

    let task = tauri::async_runtime::spawn(async move {
        run_watchdog(app_handle, port, cancel_rx).await;
    });

    WatchdogHandle {
        _task: task,
        cancel_tx,
    }
}

async fn run_watchdog(app: AppHandle, port: u16, mut cancel_rx: watch::Receiver<bool>) {
    let mut restart_timestamps: Vec<Instant> = Vec::new();
    let mut last_error = String::new();

    loop {
        tokio::select! {
            _ = tokio::time::sleep(HEALTH_CHECK_INTERVAL) => {}
            _ = cancel_rx.changed() => {
                if *cancel_rx.borrow() {
                    println!("[watchdog] Cancelled by graceful shutdown");
                    return;
                }
            }
        }

        if *cancel_rx.borrow() {
            return;
        }

        if is_backend_alive(&app) && check_health(port).await {
            continue;
        }

        if is_backend_alive(&app) {
            continue;
        }

        println!("[watchdog] Backend process exited unexpectedly");
        update_tray_status(&app, "restarting");
        let _ = app.emit("backend-crash", ());

        restart_timestamps.retain(|t| t.elapsed() < RESTART_WINDOW);

        if restart_timestamps.len() >= MAX_RESTARTS_IN_WINDOW {
            eprintln!(
                "[watchdog] Backend crashed {} times in {:?}, giving up auto-restart",
                MAX_RESTARTS_IN_WINDOW, RESTART_WINDOW
            );
            update_tray_status(&app, "error");
            let _ = app.emit("backend-crash-loop", &last_error);
            return;
        }

        let delay_idx = restart_timestamps.len().min(RESTART_DELAYS.len() - 1);
        let delay = RESTART_DELAYS[delay_idx];

        println!("[watchdog] Restarting backend in {:?}...", delay);

        tokio::select! {
            _ = tokio::time::sleep(delay) => {}
            _ = cancel_rx.changed() => {
                if *cancel_rx.borrow() {
                    return;
                }
            }
        }

        if *cancel_rx.borrow() {
            return;
        }

        match restart_backend(&app).await {
            Ok(_) => {
                println!("[watchdog] Backend restarted successfully");
                restart_timestamps.push(Instant::now());
                last_error.clear();
                update_tray_status(&app, "idle");
                let _ = app.emit("backend-restarted", ());
            }
            Err(e) => {
                eprintln!("[watchdog] Failed to restart backend: {}", e);
                last_error = e;
                restart_timestamps.push(Instant::now());
                update_tray_status(&app, "error");
            }
        }
    }
}

fn is_backend_alive(app: &AppHandle) -> bool {
    let backend = app.state::<PythonBackend>();
    let mut guard = backend.process.lock().unwrap();
    if let Some(ref mut child) = *guard {
        match child.try_wait() {
            Ok(None) => true,
            Ok(Some(_)) => {
                *guard = None;
                false
            }
            Err(_) => false,
        }
    } else {
        false
    }
}

async fn check_health(port: u16) -> bool {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(5))
        .build();

    let Ok(client) = client else { return false };

    let url = format!("http://127.0.0.1:{}/health", port);
    matches!(client.get(&url).send().await, Ok(resp) if resp.status().is_success())
}

async fn restart_backend(app: &AppHandle) -> Result<(), String> {
    let config_manager = app.state::<ConfigManager>();
    let system_config = config_manager.load();
    let backend_config = BackendConfig::from_system_config(&system_config);

    let backend_state = app.state::<PythonBackend>();

    crate::runtime::start_backend_with_config(
        app.clone(),
        backend_state,
        backend_config,
    )
    .await
    .map(|_| ())
}

fn update_tray_status(app: &AppHandle, status: &str) {
    let tooltip = match status {
        "restarting" => "MyrmAgent - 服务重启中...",
        "error" => "MyrmAgent - 服务异常，请重启应用",
        "idle" => "MyrmAgent - 空闲",
        _ => "MyrmAgent",
    };
    crate::app::update_native_tray_status(app, status, tooltip);
}
