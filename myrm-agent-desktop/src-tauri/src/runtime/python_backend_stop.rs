//! Python 后端优雅停机序列层
//!
//! [INPUT]
//! - config::ConfigManager (POS: 桌面端系统配置与后端绑定端口)
//! - runtime::PythonBackend (POS: Sidecar 子进程句柄)
//! - runtime::ProcessRegistry (POS: 桌面受管进程注册中心)
//! - runtime::stop_backend_monitors (POS: watchdog/wake 统一停挂)
//! - utils::process_tree::kill_process_tree (POS: 进程树强杀)
//!
//! [OUTPUT]
//! - graceful_stop_backend: 全部停机路径共享的优雅停序列（连接切换/配置迁移/应用退出）。
//!
//! [POS]
//! Python 后端停机序列单一职责层。停 monitors → 请求服务端 drain
//! （活跃 turns 完成 + WAL Checkpoint + 资源释放）→ 等待自退（reap 子进程）
//! → 兜底强杀进程树，保证任意停机路径下进程树必然干净退场。

use std::time::Duration;

use tauri::{AppHandle, Manager, State};

use crate::config::ConfigManager;
use crate::runtime::PythonBackend;
use crate::utils::process_tree::kill_process_tree;

/// Request the backend to drain and exit by itself via the server's
/// graceful shutdown endpoint (drains active turns, flushes WAL, closes
/// resources, then SIGTERMs itself).
async fn request_graceful_shutdown(port: u16) -> Result<(), String> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| format!("Failed to create HTTP client: {}", e))?;

    let url = format!("http://127.0.0.1:{}/api/v1/system/shutdown", port);
    match client.post(&url).send().await {
        Ok(response) if response.status().is_success() => Ok(()),
        Ok(response) => Err(format!(
            "Shutdown signal failed with status: {}",
            response.status()
        )),
        Err(e) => Err(format!("Shutdown request failed: {}", e)),
    }
}

/// Wait for the backend to exit by itself, reaping the child so the state
/// reflects reality. Returns true when the process exited within the budget.
async fn wait_for_graceful_exit(backend: &State<'_, PythonBackend>, budget: Duration) -> bool {
    let deadline = tokio::time::Instant::now() + budget;
    while tokio::time::Instant::now() < deadline {
        let exited = {
            let mut process_guard = backend.process.lock().unwrap();
            match process_guard.as_mut() {
                None => true,
                Some(child) => matches!(child.try_wait(), Ok(Some(_))),
            }
        };
        if exited {
            let mut process_guard = backend.process.lock().unwrap();
            *process_guard = None;
            return true;
        }
        tokio::time::sleep(Duration::from_millis(200)).await;
    }
    false
}

/// Graceful backend stop sequence shared by every stop path (connection
/// switch, config migration, app exit): stop monitors → request server-side
/// drain (drain turns, WAL checkpoint, close resources) → wait for
/// self-exit → force-kill the process tree as last resort.
///
/// Stopping the monitors first is what keeps the watchdog from resurrecting
/// a backend that was stopped intentionally.
pub async fn graceful_stop_backend(
    app: &AppHandle,
    backend: &State<'_, PythonBackend>,
) -> Result<String, String> {
    println!("Stopping Python backend (graceful)...");

    crate::runtime::stop_backend_monitors(app);

    // Best-effort drain request: the server may already be down or the
    // config state unavailable; the force path below still guarantees the
    // process tree is gone.
    if let Some(config_manager) = app.try_state::<ConfigManager>() {
        let port = config_manager.load().api_port;
        if port > 0 {
            let _ = request_graceful_shutdown(port).await;
            if wait_for_graceful_exit(backend, Duration::from_secs(5)).await {
                println!("Backend exited gracefully after shutdown signal");
                if let Some(registry) = app.try_state::<crate::runtime::ProcessRegistry>() {
                    let reg = registry.inner().clone();
                    tauri::async_runtime::spawn(async move {
                        reg.mark_stopped("sidecar:backend", Some(0)).await;
                    });
                }
                return Ok("Backend stopped gracefully".to_string());
            }
            println!("Backend did not self-exit in time, forcing kill...");
        }
    }

    let mut process_guard = backend.process.lock().unwrap();

    if let Some(mut child) = process_guard.take() {
        if let Some(registry) = app.try_state::<crate::runtime::ProcessRegistry>() {
            let reg = registry.inner().clone();
            tauri::async_runtime::spawn(async move {
                reg.mark_stopped("sidecar:backend", Some(0)).await;
            });
        }
        let pid = child.id();
        // 已自行退出的进程直接视为停止成功，避免误报阻断调用方
        if let Ok(Some(status)) = child.try_wait() {
            println!(
                "Backend already exited (root PID: {}, status: {})",
                pid, status
            );
            return Ok("Backend stopped successfully".to_string());
        }
        kill_process_tree(pid);
        if let Err(e) = child.kill() {
            // kill 失败但进程可能已死：再确认一次，确认已死即成功
            if let Ok(Some(status)) = child.try_wait() {
                println!(
                    "Backend exited during stop (root PID: {}, status: {})",
                    pid, status
                );
                return Ok("Backend stopped successfully".to_string());
            }
            return Err(format!("Failed to stop backend: {}", e));
        }
        // 确认进程真正退出后再返回：避免调用方在文件句柄未释放时即开始拷贝
        const EXIT_WAIT_ITERS: u32 = 100;
        for _ in 0..EXIT_WAIT_ITERS {
            match child.try_wait() {
                Ok(Some(status)) => {
                    println!(
                        "Backend process tree exited (root PID: {}, status: {})",
                        pid, status
                    );
                    return Ok("Backend stopped successfully".to_string());
                }
                Ok(None) => std::thread::sleep(std::time::Duration::from_millis(100)),
                Err(e) => {
                    return Err(format!("Failed to confirm backend exit: {}", e));
                }
            }
        }
        Err(format!(
            "Backend process (root PID: {}) did not exit within 10s after kill",
            pid
        ))
    } else {
        Ok("Backend is not running".to_string())
    }
}
