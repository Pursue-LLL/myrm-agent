//! 桌面端受管进程注册表模块根
//!
//! [INPUT]
//! - types::{ManagedProcessEntry, ProcessRole, ProcessStatus}
//! - registry::ProcessRegistry
//!
//! [OUTPUT]
//! - ProcessRegistry, ManagedProcessEntry, ProcessRole, ProcessStatus
//!
//! [POS]
//! Tauri 运行时全局进程注册与生命周期可观测中心。

mod registry;
mod types;

pub use registry::ProcessRegistry;
pub use types::{ManagedProcessEntry, ProcessRole, ProcessStatus};
