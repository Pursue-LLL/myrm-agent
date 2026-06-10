//! 优雅停机与生命周期管理
//!
//! [INPUT]
//! - config::ConfigManager (POS: 配置管理)
//! - runtime::{PythonBackend, NextJSFrontend, stop_backend, stop_frontend} (POS: Sidecar 进程管理)
//!
//! [OUTPUT]
//! - graceful_shutdown: 完整优雅停机流程（防重入 + 5s timeout + 强制 kill 兜底）
//!
//! [POS]
//! 桌面端退出生命周期管理。协调后端、前端、隧道的有序关闭。

use std::sync::atomic::{AtomicBool, Ordering};
use std::time::Duration;

use tauri::{AppHandle, Manager};
use tokio::time::timeout;

use crate::{PythonBackend, NextJSFrontend, stop_backend, stop_frontend};
static SHUTDOWN_INITIATED: AtomicBool = AtomicBool::new(false);

/// 发送优雅停机信号给后端
async fn send_shutdown_signal(port: u16) -> Result<(), String> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| format!("Failed to create HTTP client: {}", e))?;

    let url = format!("http://127.0.0.1:{}/api/v1/system/shutdown", port);
    match client.post(&url).send().await {
        Ok(response) => {
            if response.status().is_success() {
                Ok(())
            } else {
                Err(format!("Shutdown signal failed with status: {}", response.status()))
            }
        }
        Err(e) => Err(format!("Shutdown request failed: {}", e)),
    }
}

/// 执行完整的优雅停机流程（防重入：多路径并发调用时仅首次生效）
pub async fn graceful_shutdown(app: AppHandle) {
    if SHUTDOWN_INITIATED.swap(true, Ordering::SeqCst) {
        println!("Shutdown already in progress, skipping duplicate call.");
        return;
    }
    println!("Initiating graceful shutdown...");
    
    let port = {
        let config_manager = app.state::<crate::config::ConfigManager>();
        let config = config_manager.load();
        config.api_port
    };

    println!("Sending shutdown signal to backend on port {}...", port);
    let _ = send_shutdown_signal(port).await;

    println!("Waiting for backend to gracefully exit...");
    let backend_state = app.state::<PythonBackend>();
    
    let wait_result = timeout(Duration::from_secs(5), async {
        loop {
            let is_running = {
                let process_guard = backend_state.process.lock().unwrap();
                process_guard.is_some()
            };
            if !is_running {
                break;
            }
            tokio::time::sleep(Duration::from_millis(500)).await;
        }
    }).await;

    if wait_result.is_err() {
        println!("Backend did not exit gracefully within timeout, forcing kill...");
    } else {
        println!("Backend exited gracefully.");
    }

    let _ = stop_backend(backend_state);
    
    let frontend_state = app.state::<NextJSFrontend>();
    let _ = stop_frontend(frontend_state);
    
    println!("Graceful shutdown complete.");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shutdown_initiated_prevents_reentry() {
        SHUTDOWN_INITIATED.store(false, Ordering::SeqCst);

        let first = SHUTDOWN_INITIATED.swap(true, Ordering::SeqCst);
        assert!(!first, "first call should proceed");

        let second = SHUTDOWN_INITIATED.swap(true, Ordering::SeqCst);
        assert!(second, "second call should be blocked");

        let third = SHUTDOWN_INITIATED.swap(true, Ordering::SeqCst);
        assert!(third, "third call should also be blocked");

        SHUTDOWN_INITIATED.store(false, Ordering::SeqCst);
    }

    #[test]
    fn concurrent_shutdown_only_one_proceeds() {
        SHUTDOWN_INITIATED.store(false, Ordering::SeqCst);

        let handles: Vec<_> = (0..10)
            .map(|_| {
                std::thread::spawn(|| SHUTDOWN_INITIATED.swap(true, Ordering::SeqCst))
            })
            .collect();

        let results: Vec<bool> = handles.into_iter().map(|h| h.join().unwrap()).collect();
        let proceeded_count = results.iter().filter(|&&v| !v).count();
        assert_eq!(proceeded_count, 1, "exactly one thread should proceed");

        SHUTDOWN_INITIATED.store(false, Ordering::SeqCst);
    }
}
