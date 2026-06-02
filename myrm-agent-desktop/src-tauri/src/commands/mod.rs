//! Tauri 命令模块
//!
//! 导出所有 Tauri 命令供 main.rs 使用。

pub mod agent;
pub mod config;
pub mod power;
pub mod screen_lock;

pub use agent::{
    detect_agents,
    list_agent_adapters,
    create_agent_session,
    list_agent_sessions,
    get_agent_session,
    delete_agent_session,
    resume_agent_session,
    send_agent_message,
    stop_agent_message,
    respond_agent_permission,
    get_permission_mode,
    set_permission_mode,
    cycle_permission_mode,
};
pub use config::*;
pub use power::{power_lock_acquire, power_lock_release, power_lock_status};
pub use screen_lock::{
    screen_is_locked,
    screen_unlock,
    screen_relock,
    screen_lock_store_password,
    screen_lock_has_password,
    screen_lock_delete_password,
    screen_lock_platform_support,
};
