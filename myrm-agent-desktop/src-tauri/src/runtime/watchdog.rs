//! 后端 Sidecar 健康监控与崩溃自动恢复
//!
//! [INPUT]
//! - PythonBackend (POS: 后端进程引用)
//! - ConfigManager (POS: 端口配置)
//! - CancellationToken (用于 graceful_shutdown 协调)
//!
//! [OUTPUT]
//! - 周期性健康检查 (30s)
//! - 崩溃/假死/句柄压力检测 + 指数退避重启 (5s/15s/60s, 5min 内最多 3 次)
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
/// Consecutive failed health checks on a live process before it is treated as hung.
const HUNG_CHECKS_BEFORE_RESTART: u8 = 3;
/// A leaked-handle runaway shows up here long before EMFILE makes every request fail.
/// Restarting at this level turns an unusable process into a short recovery instead of
/// an outage; a healthy backend sits around a few hundred descriptors.
const FD_RESTART_THRESHOLD: u64 = 8192;

use std::sync::Arc;
use tokio::sync::Notify;

/// Watchdog handle returned to caller for lifecycle coordination.
pub struct WatchdogHandle {
    _task: JoinHandle<()>,
    cancel_tx: watch::Sender<bool>,
    wake_notify: Arc<Notify>,
}

impl WatchdogHandle {
    /// Cancel the watchdog (called during graceful shutdown).
    pub fn cancel(&self) {
        let _ = self.cancel_tx.send(true);
    }

    /// Obtain a handle to trigger immediate wake check.
    pub fn wake_notify(&self) -> Arc<Notify> {
        self.wake_notify.clone()
    }

    /// Trigger an immediate out-of-band health check.
    #[allow(dead_code)]
    pub fn trigger_check(&self) {
        self.wake_notify.notify_one();
    }
}

/// Spawn a watchdog task that monitors backend health and auto-restarts on crash.
pub fn spawn_watchdog(app: &AppHandle, port: u16) -> WatchdogHandle {
    let app_handle = app.clone();
    let (cancel_tx, cancel_rx) = watch::channel(false);
    let wake_notify = Arc::new(Notify::new());
    let wake_rx = wake_notify.clone();

    let task = tauri::async_runtime::spawn(async move {
        run_watchdog(app_handle, port, cancel_rx, wake_rx).await;
    });

    WatchdogHandle {
        _task: task,
        cancel_tx,
        wake_notify,
    }
}

async fn run_watchdog(
    app: AppHandle,
    port: u16,
    mut cancel_rx: watch::Receiver<bool>,
    wake_notify: Arc<Notify>,
) {
    let mut restart_timestamps: Vec<Instant> = Vec::new();
    let mut last_error = String::new();
    let mut hung_checks = 0u8;

    loop {
        tokio::select! {
            _ = tokio::time::sleep(HEALTH_CHECK_INTERVAL) => {}
            _ = wake_notify.notified() => {
                println!("[watchdog] Wake notification received, running 0-delay health check");
            }
            changed = cancel_rx.changed() => {
                // Err means the sender dropped without a stored cancel; that
                // is still terminal (monitor replaced) — exit either way
                // instead of busy-looping on a closed channel.
                if changed.is_err() || *cancel_rx.borrow_and_update() {
                    println!("[watchdog] Cancelled by graceful shutdown");
                    return;
                }
            }
        }

        if *cancel_rx.borrow() {
            return;
        }

        if is_backend_alive(&app) {
            let healthy = check_health(port).await;
            let fd_pressure = healthy && fd_pressure_exceeded(port).await;
            if healthy && !fd_pressure {
                hung_checks = 0;
                continue;
            }
            // The process exists but is not usable: a hung sidecar holds the port, and a
            // runaway descriptor count is one step away from EMFILE. Waiting forever (the
            // old behaviour) left the app unusable until a manual restart.
            hung_checks += 1;
            if hung_checks < HUNG_CHECKS_BEFORE_RESTART {
                continue;
            }
            let reason = if fd_pressure {
                "descriptor pressure"
            } else {
                "unresponsive health checks"
            };
            eprintln!(
                "[watchdog] Backend alive but {} for {} checks; killing it to restart",
                reason, hung_checks
            );
            hung_checks = 0;
            stop_backend_process(&app);
        } else {
            hung_checks = 0;
        }

        println!("[watchdog] Backend is not serving; restarting");
        if let Some(registry) = app.try_state::<crate::runtime::ProcessRegistry>() {
            let reg = registry.inner().clone();
            tauri::async_runtime::spawn(async move {
                reg.mark_crashed(
                    "sidecar:backend",
                    None,
                    Some("Unexpected process exit".to_string()),
                )
                .await;
                reg.record_restart("sidecar:backend").await;
            });
        }
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

/// Force-kill a hung backend child so the restart can bind its port.
fn stop_backend_process(app: &AppHandle) {
    let backend = app.state::<PythonBackend>();
    let mut guard = backend.process.lock().unwrap();
    if let Some(mut child) = guard.take() {
        let pid = child.id();
        crate::utils::process_tree::kill_process_tree(pid);
        let _ = child.kill();
        println!("[watchdog] Killed unresponsive backend tree (PID: {})", pid);
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

/// True when the sidecar reports a descriptor count at or above the restart threshold.
/// Any failure to read the probe is treated as "no pressure": the endpoint is a safety
/// net, not a second health gate, and a missing field must not trigger a restart.
async fn fd_pressure_exceeded(port: u16) -> bool {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(3))
        .build()
    {
        Ok(client) => client,
        Err(_) => return false,
    };
    let url = format!("http://127.0.0.1:{}/api/v1/health/pressure", port);
    let Ok(response) = client.get(&url).send().await else {
        return false;
    };
    let Ok(payload) = response.json::<serde_json::Value>().await else {
        return false;
    };
    fd_count_from_pressure(&payload)
        .map(|count| count >= FD_RESTART_THRESHOLD)
        .unwrap_or(false)
}

/// Extract `process.fd_count` from the pressure payload; unknown shapes yield `None`.
fn fd_count_from_pressure(payload: &serde_json::Value) -> Option<u64> {
    payload.get("process")?.get("fd_count")?.as_u64()
}

async fn restart_backend(app: &AppHandle) -> Result<(), String> {
    let config_manager = app.state::<ConfigManager>();
    let system_config = config_manager.load();
    let backend_config = BackendConfig::from_system_config(&system_config);

    let backend_state = app.state::<PythonBackend>();

    crate::runtime::start_backend_with_config(app.clone(), backend_state, backend_config)
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

#[cfg(test)]
mod tests {
    use super::{fd_count_from_pressure, FD_RESTART_THRESHOLD};
    use serde_json::json;

    #[test]
    fn reads_a_known_fd_count() {
        assert_eq!(
            fd_count_from_pressure(&json!({"process": {"fd_count": 255}})),
            Some(255)
        );
    }

    #[test]
    fn threshold_is_far_above_a_healthy_process() {
        assert!(FD_RESTART_THRESHOLD > 1_000);
    }

    #[test]
    fn missing_or_malformed_fields_do_not_trigger_a_restart() {
        assert_eq!(fd_count_from_pressure(&json!({})), None);
        assert_eq!(fd_count_from_pressure(&json!({"process": {}})), None);
        assert_eq!(
            fd_count_from_pressure(&json!({"process": {"fd_count": "high"}})),
            None
        );
        assert_eq!(
            fd_count_from_pressure(&json!({"process": {"fd_count": -1}})),
            None
        );
    }
}
