//! 桌面运行时：Sidecar 进程、全局快捷键、Setup Token、Agent Runner 编排
//!
//! [INPUT]
//! - config::BackendConfig / FrontendConfig (POS: 系统与 Sidecar 配置)
//! - sidecar::SidecarManager (POS: Agent Runner JSON-RPC 进程管理)
//!
//! [OUTPUT]
//! - PythonBackend / NextJSFrontend 进程状态与 IPC 命令
//! - 全局快捷键处理（Appshot 截屏、Voice PTT、Inline Input、窗口 toggle）
//! - SetupTokenState / get_setup_token
//! - bootstrap_agent_runner / resolve_agent_runner_path
//! - Inline Input: handle_inline_input_shortcut / paste_back / INLINE_INPUT_SHORTCUT_STR
//!
//! [POS]
//! Tauri 主进程内的 Sidecar 与系统运行时层，承接 Python/Next.js/Agent Runner 进程生命周期。

mod agent_runner;
mod appshot;
mod inline_input;
mod nextjs_frontend;
mod port;
mod python_backend;
mod setup_token;
pub mod watchdog;

pub use agent_runner::{bootstrap_agent_runner, resolve_agent_runner_path};
pub use appshot::{
    force_capture, handle_appshot_shortcut, handle_toggle_window, handle_voice_ptt_start,
    handle_voice_ptt_stop, APPSHOT_SHORTCUT_STR, VOICE_PTT_SHORTCUT_STR,
};
pub use inline_input::{handle_inline_input_shortcut, paste_back, INLINE_INPUT_SHORTCUT_STR};
pub use nextjs_frontend::{start_frontend, NextJSFrontend, stop_frontend};
pub use python_backend::{
    check_backend_health, get_backend_status, start_backend, start_backend_with_config,
    stop_backend, PythonBackend,
};
pub use setup_token::{get_setup_token, SetupTokenState};

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
