//! Tauri 命令模块
//!
//! 导出所有 Tauri 命令供 main.rs 使用。

pub mod agent;
pub mod config;
pub mod pet_overlay;
pub mod power;
pub mod screen_lock;
pub mod visual_approval_overlay;

pub use agent::{
    detect_agents,
    get_agent_sidecar_status,
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
    check_accessibility_permission,
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
pub use pet_overlay::{hide_pet_overlay, pet_overlay_set_row, show_pet_overlay};
pub use visual_approval_overlay::{
    hide_visual_approval_overlay,
    show_visual_approval_overlay,
};
