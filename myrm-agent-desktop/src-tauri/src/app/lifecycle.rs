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
static SHUTDOWN_COMPLETED: AtomicBool = AtomicBool::new(false);

/// 优雅停机是否已发起
pub fn is_shutdown_initiated() -> bool {
    SHUTDOWN_INITIATED.load(Ordering::SeqCst)
}

/// 优雅停机与资源释放是否已彻底完成
pub fn is_shutdown_completed() -> bool {
    SHUTDOWN_COMPLETED.load(Ordering::SeqCst)
}

/// 标记停机完成（包含「优雅流程超时、由兜底物理退出接手」的路径）。
pub fn mark_shutdown_completed() {
    SHUTDOWN_COMPLETED.store(true, Ordering::SeqCst);
}

/// 统一的「停机 + 退出」入口：先给优雅流程一个有界预算，再确保没有子进程被遗留，最后退出。
///
/// 顺序不可颠倒：壳一旦先退出，Python/Next 会被 reparent 到 init 继续占端口与 CPU
/// （用户看到的下一次启动失败、风扇狂转都源自这里）。
pub async fn shutdown_and_exit(app: AppHandle, exit_code: i32) {
    let graceful = tokio::time::timeout(
        std::time::Duration::from_secs(15),
        graceful_shutdown(app.clone()),
    )
    .await;
    if graceful.is_err() {
        eprintln!("⚠️ Graceful shutdown exceeded its budget; falling back to forced child cleanup");
        mark_shutdown_completed();
    }
    let reaped = crate::runtime::child_reaper::reap_recorded_children_now(&app);
    if reaped > 0 {
        println!(
            "🧹 Reaped {} surviving child process(es) before exit",
            reaped
        );
    }
    app.exit(exit_code);
    // 兜底：Tauri 事件循环若被残留原生线程拖住，2 秒后物理退出（子进程已在上面回收）。
    std::thread::spawn(move || {
        std::thread::sleep(std::time::Duration::from_secs(2));
        std::process::exit(exit_code);
    });
}

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
    // Cancel first: the watchdog must not treat the intentional stop below as a crash
    // and resurrect the frontend while the shell is shutting down.
    crate::runtime::stop_frontend_monitor(&app);
    let _ = stop_frontend(app.clone(), frontend_state);

    SHUTDOWN_COMPLETED.store(true, Ordering::SeqCst);
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
