//! 跨平台系统工具模块根。
//!
//! [INPUT]
//! - 平台原生 API（Win32 / Keychain / com.apple.quarantine）
//!
//! [OUTPUT]
//! - auth / process_tree / protocol_page / quarantine / screen_credential / screen_lock / updater_safety 子模块
//!
//! [POS]
//! 系统能力封装聚合；由 commands/ IPC 或 app/ 启动期调用。

pub mod auth;
pub mod process_tree;
pub mod protocol_page;
pub mod quarantine;
pub mod screen_credential;
pub mod screen_lock;
pub mod updater_safety;
