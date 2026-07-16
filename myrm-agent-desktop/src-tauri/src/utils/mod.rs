//! 跨平台系统工具模块根。
//!
//! [INPUT]
//! - 平台原生 API（IOKit / Win32 / Keychain / com.apple.quarantine）
//!
//! [OUTPUT]
//! - auth / power / quarantine / screen_lock / updater_safety 子模块
//!
//! [POS]
//! 系统能力封装聚合；由 commands/ IPC 或 app/ 启动期调用。

pub mod auth;
pub mod power;
pub mod quarantine;
pub mod screen_lock;
pub mod updater_safety;
