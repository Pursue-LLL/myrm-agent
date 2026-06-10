//! 桌面运行时：Sidecar 进程、Appshot、Setup Token、Agent Runner 编排
//!
//! [INPUT]
//! - config::BackendConfig / FrontendConfig (POS: 系统与 Sidecar 配置)
//! - sidecar::SidecarManager (POS: Agent Runner JSON-RPC 进程管理)
//!
//! [OUTPUT]
//! - PythonBackend / NextJSFrontend 进程状态与 IPC 命令
//! - Appshot 全局快捷键处理
//! - SetupTokenState / get_setup_token
//! - bootstrap_agent_runner / resolve_agent_runner_path
//!
//! [POS]
//! Tauri 主进程内的 Sidecar 与系统运行时层，承接 Python/Next.js/Agent Runner 进程生命周期。

mod agent_runner;
mod appshot;
mod nextjs_frontend;
mod port;
mod python_backend;
mod setup_token;

pub use agent_runner::{bootstrap_agent_runner, resolve_agent_runner_path};
pub use appshot::{handle_appshot_shortcut, handle_toggle_window, APPSHOT_SHORTCUT_STR};
pub use nextjs_frontend::{start_frontend, NextJSFrontend, stop_frontend};
pub use python_backend::{
    check_backend_health, get_backend_status, start_backend, start_backend_with_config,
    stop_backend, PythonBackend,
};
pub use setup_token::{get_setup_token, SetupTokenState};
