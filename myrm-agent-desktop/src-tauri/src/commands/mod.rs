//! Tauri 命令模块
//!
//! [INPUT]
//! - runtime / agent_runner_rpc / sessions / permissions / config / utils 各子模块
//!
//! [OUTPUT]
//! - 子模块 IPC 命令聚合（由 app/mod.rs generate_handler 注册叶子路径）
//!
//! [POS]
//! Tauri invoke 命令层模块根；叶子清单见 `_ARCH.md` 与各子目录 _ARCH。

pub mod agent;
pub mod config;
pub mod pet_overlay;
pub mod power;
pub mod recovery;
pub mod screen_lock;
pub mod session_window;
pub mod visual_approval_overlay;
