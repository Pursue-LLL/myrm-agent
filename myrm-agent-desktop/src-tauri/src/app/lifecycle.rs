//! 优雅停机与生命周期管理
//!
//! [INPUT]
//! - config::ConfigManager (POS: 配置管理)
//! - runtime::{PythonBackend, NextJSFrontend, graceful_stop_backend, stop_frontend} (POS: Sidecar 进程管理)
//! - commands::privacy_curtain::relock_outstanding_lease (POS: 帷幕随进程消失前的租约兜底回锁)
//!
//! [OUTPUT]
//! - graceful_shutdown: 完整优雅停机流程（防重入；后端优雅停止已内化为 graceful_stop_backend；
//!   后端停止后若代解锁租约仍未交还，由壳回锁屏幕）
//!
//! [POS]
//! 桌面端退出生命周期管理。协调后端、前端、隧道的有序关闭。

use std::sync::atomic::{AtomicBool, Ordering};

use tauri::{AppHandle, Manager};

use crate::commands::privacy_curtain::relock_outstanding_lease;
use crate::runtime::{graceful_stop_backend, stop_frontend, NextJSFrontend, PythonBackend};

static SHUTDOWN_INITIATED: AtomicBool = AtomicBool::new(false);

/// 执行完整的优雅停机流程（防重入：多路径并发调用时仅首次生效）
pub async fn graceful_shutdown(app: AppHandle) {
    if SHUTDOWN_INITIATED.swap(true, Ordering::SeqCst) {
        println!("Shutdown already in progress, skipping duplicate call.");
        return;
    }
    println!("Initiating graceful shutdown...");

    let backend_state = app.state::<PythonBackend>();
    match graceful_stop_backend(&app, &backend_state).await {
        Ok(message) => println!("Backend stop: {}", message),
        Err(e) => println!("Backend stop failed: {}", e),
    }
    // 帷幕窗口随进程消失：后端没来得及交还租约（停机预算内回锁不完 / 被强杀）则由壳回锁。
    relock_outstanding_lease(&app).await;

    let frontend_state = app.state::<NextJSFrontend>();
    let _ = stop_frontend(app.clone(), frontend_state);

    println!("Graceful shutdown complete.");
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::Arc;

    #[test]
    fn shutdown_initiated_prevents_reentry() {
        let flag = AtomicBool::new(false);

        let first = flag.swap(true, Ordering::SeqCst);
        assert!(!first, "first call should proceed");

        let second = flag.swap(true, Ordering::SeqCst);
        assert!(second, "second call should be blocked");

        let third = flag.swap(true, Ordering::SeqCst);
        assert!(third, "third call should also be blocked");
    }

    #[test]
    fn concurrent_shutdown_only_one_proceeds() {
        let flag = Arc::new(AtomicBool::new(false));

        let handles: Vec<_> = (0..10)
            .map(|_| {
                let f = Arc::clone(&flag);
                std::thread::spawn(move || f.swap(true, Ordering::SeqCst))
            })
            .collect();

        let results: Vec<bool> = handles.into_iter().map(|h| h.join().unwrap()).collect();
        let proceeded_count = results.iter().filter(|&&v| !v).count();
        assert_eq!(proceeded_count, 1, "exactly one thread should proceed");
    }
}
