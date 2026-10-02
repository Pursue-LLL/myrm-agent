//! 桌面运行时：Sidecar 进程、全局快捷键、Setup Token 编排
//!
//! [INPUT]
//! - config::BackendConfig / FrontendConfig (POS: 系统与 Sidecar 配置)
//!
//! [OUTPUT]
//! - PythonBackend / NextJSFrontend 进程状态与 IPC 命令
//! - 全局快捷键处理（Appshot 截屏、Voice PTT、Inline Input、窗口 toggle）
//! - SetupTokenState / get_setup_token
//! - Inline Input: handle_inline_input_shortcut / paste_back / INLINE_INPUT_SHORTCUT_STR
//! - `.myrmtheme` open-file bridge via theme_package_open (emit theme-package-open)
//!
//! [POS]
//! Tauri 主进程内的 Sidecar 与系统运行时层，承接 Python/Next.js 进程生命周期。

mod appshot;
mod inline_input;
mod theme_package_open;
pub mod nextjs_frontend;
pub mod port;
pub mod remote_follow;
pub mod update_safety;
pub mod process_registry;
pub mod python_backend;
pub mod setup_token;
pub mod sidecar_version_manager;
pub mod survivor_diag;
pub mod watchdog;
pub mod wake;

#[allow(unused_imports)]
pub use process_registry::{ManagedProcessEntry, ProcessRegistry, ProcessRole, ProcessStatus};
pub use appshot::{
    force_capture, handle_appshot_shortcut, handle_toggle_window, handle_voice_ptt_start,
    handle_voice_ptt_stop, APPSHOT_SHORTCUT_STR, VOICE_PTT_SHORTCUT_STR,
};
pub use inline_input::{handle_inline_input_shortcut, paste_back, INLINE_INPUT_SHORTCUT_STR};
#[allow(unused_imports)]
pub use theme_package_open::{emit_theme_package_open, handle_open_urls, handle_startup_args};
pub use nextjs_frontend::{start_frontend, stop_frontend, NextJSFrontend};
pub use python_backend::{graceful_stop_backend, start_backend_with_config, stop_backend, PythonBackend};
pub use remote_follow::is_remote_follow_deferred;
pub use setup_token::SetupTokenState;
#[allow(unused_imports)]
pub use sidecar_version_manager::{SidecarVersionManager, SidecarVersionManifest};

use tauri::{AppHandle, Manager};

/// Spawn backend health monitors (watchdog + wake detector) and manage their handles.
///
/// Idempotent: replaces any previously managed monitors first, so the wake
/// detector always references the live watchdog's notify channel.
pub fn spawn_backend_monitors(app: &AppHandle, backend_port: u16) {
    stop_backend_monitors(app);
    let watchdog_handle = watchdog::spawn_watchdog(app, backend_port);
    let wake_handle = wake::spawn_wake_detector(
        app.clone(),
        watchdog_handle.wake_notify(),
        backend_port,
    );
    app.manage(watchdog_handle);
    app.manage(wake_handle);
}

/// Cancel and replace backend health monitors (watchdog + wake detector).
///
/// Safe when monitors were never spawned or already stopped. Prevents the
/// watchdog from resurrecting a backend that was stopped intentionally.
/// Cancelled handles stay managed until the next spawn overwrites them:
/// `unmanage` is deprecated (dangling `State` risk) and dropping a cancelled
/// handle is harmless (its task already observed the cancel).
pub fn stop_backend_monitors(app: &AppHandle) {
    if let Some(handle) = app.try_state::<watchdog::WatchdogHandle>() {
        handle.cancel();
    }
    if let Some(handle) = app.try_state::<wake::WakeDetectorHandle>() {
        handle.cancel();
    }
}

/// Host environment variables that must be stripped before spawning child processes.
///
/// Prevents host-machine pollution (conda PYTHONPATH, nvm NODE_OPTIONS, corporate
/// HTTP_PROXY, dynamic linker injection, etc.) from leaking into Myrm runtimes.
/// Mirrors the harness-layer blacklist in `myrm_agent_harness/.../blacklist.py`.
pub const TOXIC_ENV_VARS: &[&str] = &[
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONSTARTUP",
    "NODE_OPTIONS",
    "NODE_PATH",
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "LD_AUDIT",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH",
    "DYLD_FRAMEWORK_PATH",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "NODE_TLS_REJECT_UNAUTHORIZED",
    "NODE_EXTRA_CA_CERTS",
    "BASH_ENV",
    "ENV",
    "SSLKEYLOGFILE",
    "GCONV_PATH",
];

/// Windows: 设置 CREATE_NO_WINDOW 标志防止子进程弹出控制台窗口
#[allow(unused_variables)]
pub fn suppress_console_window(cmd: &mut std::process::Command) {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
}
