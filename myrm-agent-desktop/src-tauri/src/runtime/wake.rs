//! 桌面端系统休眠与唤醒侦测与会话重连自愈协调器
//!
//! [INPUT]
//! - Tauri AppHandle (用于事件广播与状态访问)
//! - WatchdogHandle (用于触发 0-delay 快速健康检查)
//!
//! [OUTPUT]
//! - 广播 `app:system-wake` (Phase 1: "waking" -> Phase 2: "ready")
//! - 触发 Watchdog 快速健康检查
//!
//! [POS]
//! 捕获系统睡眠/唤醒（Sleep/Wake），解决合盖开盖后 30s 假死与半开死连接。

use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde::Serialize;
use tauri::{AppHandle, Emitter};
use tokio::sync::Notify;

const DRIFT_CHECK_INTERVAL: Duration = Duration::from_millis(1000);
const DRIFT_THRESHOLD: Duration = Duration::from_millis(3000);
const DEBOUNCE_WINDOW_MS: u64 = 4000;
const PHASE2_NETWORK_SETTLE_DELAY: Duration = Duration::from_millis(800);

#[derive(Debug, Clone, Serialize)]
pub struct WakeEventPayload {
    pub phase: &'static str,
    pub timestamp: u64,
    pub sidecar_alive: Option<bool>,
    pub reason: &'static str,
}

#[allow(dead_code)]
pub struct WakeDetectorHandle {
    cancel_notify: Arc<Notify>,
}

impl WakeDetectorHandle {
    #[allow(dead_code)]
    pub fn cancel(&self) {
        self.cancel_notify.notify_waiters();
    }
}

/// 启动休眠唤醒侦测任务
pub fn spawn_wake_detector(
    app: AppHandle,
    wake_notify: Arc<Notify>,
    backend_port: u16,
) -> WakeDetectorHandle {
    let cancel_notify = Arc::new(Notify::new());
    let cancel_rx = cancel_notify.clone();

    tauri::async_runtime::spawn(async move {
        run_wake_detector(app, wake_notify, backend_port, cancel_rx).await;
    });

    WakeDetectorHandle { cancel_notify }
}

async fn run_wake_detector(
    app: AppHandle,
    wake_notify: Arc<Notify>,
    backend_port: u16,
    cancel_notify: Arc<Notify>,
) {
    let last_wake_ts = Arc::new(AtomicU64::new(0));
    let is_recovering = Arc::new(AtomicBool::new(false));

    loop {
        let tick_start = Instant::now();

        tokio::select! {
            _ = tokio::time::sleep(DRIFT_CHECK_INTERVAL) => {}
            _ = cancel_notify.notified() => {
                println!("[wake_detector] Cancelled by application lifecycle");
                return;
            }
        }

        let elapsed = tick_start.elapsed();
        if elapsed >= DRIFT_THRESHOLD {
            println!(
                "[wake_detector] Detected system sleep/wake drift: elapsed {:?} >= threshold {:?}",
                elapsed, DRIFT_THRESHOLD
            );
            handle_wake_transition(
                &app,
                &wake_notify,
                backend_port,
                &last_wake_ts,
                &is_recovering,
                "wall_clock_drift",
            )
            .await;
        }
    }
}

async fn handle_wake_transition(
    app: &AppHandle,
    wake_notify: &Arc<Notify>,
    backend_port: u16,
    last_wake_ts: &Arc<AtomicU64>,
    is_recovering: &Arc<AtomicBool>,
    reason: &'static str,
) {
    let now_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64;

    let prev_ts = last_wake_ts.load(Ordering::Relaxed);
    if now_ms.saturating_sub(prev_ts) < DEBOUNCE_WINDOW_MS {
        println!("[wake_detector] Wake event debounced within {}ms", DEBOUNCE_WINDOW_MS);
        return;
    }
    last_wake_ts.store(now_ms, Ordering::Relaxed);

    if is_recovering.swap(true, Ordering::SeqCst) {
        println!("[wake_detector] Already in recovery transition, skipping concurrent run");
        return;
    }

    let app_handle = app.clone();
    let wake_notify_clone = wake_notify.clone();
    let recovering_flag = is_recovering.clone();

    tauri::async_runtime::spawn(async move {
        // Phase 1: 即刻向前端广播唤醒通知（0ms），UI 瞬间解除假死状态
        let phase1_payload = WakeEventPayload {
            phase: "waking",
            timestamp: now_ms,
            sidecar_alive: None,
            reason,
        };
        let _ = app_handle.emit("app:system-wake", &phase1_payload);
        println!("[wake_detector] Phase 1 emitted: waking (reason: {})", reason);

        // 触发 Watchdog 即刻打断 30s 沉睡，发起快速健康探针
        wake_notify_clone.notify_one();

        // Phase 2: 等待 800ms 防抖让系统网络栈就绪，并检查 Sidecar 探活
        tokio::time::sleep(PHASE2_NETWORK_SETTLE_DELAY).await;

        let alive = check_sidecar_quick(backend_port).await;
        let phase2_payload = WakeEventPayload {
            phase: "ready",
            timestamp: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64,
            sidecar_alive: Some(alive),
            reason,
        };
        let _ = app_handle.emit("app:system-wake", &phase2_payload);
        println!("[wake_detector] Phase 2 emitted: ready (sidecar_alive: {})", alive);

        recovering_flag.store(false, Ordering::SeqCst);
    });
}

async fn check_sidecar_quick(port: u16) -> bool {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_millis(1500))
        .build();

    let Ok(client) = client else { return false };
    let url = format!("http://127.0.0.1:{}/health", port);

    for _ in 0..3 {
        if let Ok(resp) = client.get(&url).send().await {
            if resp.status().is_success() {
                return true;
            }
        }
        tokio::time::sleep(Duration::from_millis(300)).await;
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_wake_payload_serialization() {
        let payload = WakeEventPayload {
            phase: "waking",
            timestamp: 1727712345678,
            sidecar_alive: None,
            reason: "test_reason",
        };
        let json = serde_json::to_string(&payload).expect("Serialization failed");
        assert!(json.contains("\"phase\":\"waking\""));
        assert!(json.contains("\"reason\":\"test_reason\""));
        assert!(json.contains("\"timestamp\":1727712345678"));
        assert!(json.contains("\"sidecar_alive\":null"));

        let ready_payload = WakeEventPayload {
            phase: "ready",
            timestamp: 1727712346678,
            sidecar_alive: Some(true),
            reason: "test_ready",
        };
        let ready_json = serde_json::to_string(&ready_payload).expect("Serialization failed");
        assert!(ready_json.contains("\"phase\":\"ready\""));
        assert!(ready_json.contains("\"sidecar_alive\":true"));
    }

    #[test]
    fn test_debounce_logic_threshold() {
        let last_wake_ts = Arc::new(AtomicU64::new(10_000));
        let debounce_window = 4000;

        let incoming_ts_blocked = 12_000;
        assert!(incoming_ts_blocked - last_wake_ts.load(Ordering::Relaxed) < debounce_window);

        let incoming_ts_allowed = 15_000;
        assert!(incoming_ts_allowed - last_wake_ts.load(Ordering::Relaxed) >= debounce_window);
    }

    #[test]
    fn test_drift_threshold_logic() {
        let short_sleep = Duration::from_millis(1050);
        assert!(short_sleep < DRIFT_THRESHOLD);

        let suspended_drift = Duration::from_millis(3500);
        assert!(suspended_drift >= DRIFT_THRESHOLD);
    }

    #[tokio::test]
    async fn test_watchdog_wake_notify_channel() {
        let notify = Arc::new(Notify::new());
        let notify_clone = notify.clone();

        let handle = tokio::spawn(async move {
            notify_clone.notified().await;
            true
        });

        notify.notify_one();
        let received = handle.await.expect("Task failed");
        assert!(received);
    }
}

