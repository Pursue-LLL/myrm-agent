//! Tauri 命令模块
//!
//! IPC 命令按子模块组织；`app/mod.rs` 的 `generate_handler` 使用叶子模块路径注册。

pub mod agent;
pub mod config;
pub mod pet_overlay;
pub mod power;
pub mod recovery;
pub mod screen_lock;
pub mod session_window;
pub mod visual_approval_overlay;
