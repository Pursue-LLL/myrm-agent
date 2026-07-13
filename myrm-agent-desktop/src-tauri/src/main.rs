//! Tauri 桌面应用入口
//!
//! [INPUT]
//! - app::run (POS: Tauri Builder 组装与插件注册)
//! - commands / config / runtime / lifecycle / tray 各模块
//!
//! [OUTPUT]
//! - 进程入口 `main()`
//!
//! [POS]
//! 桌面应用二进制入口。仅委托 `app` 模块启动，不含业务逻辑。

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod app;
mod cli_agent_types;
mod commands;
mod config;
mod lifecycle;
mod permissions;
mod runtime;
mod sessions;
mod sidecar;
mod tray;
mod utils;

fn main() {
    app::run();
}
