//! 桌面端进程注册表 IPC 命令
//!
//! [INPUT]
//! - crate::runtime::{ProcessRegistry, ManagedProcessEntry}
//!
//! [OUTPUT]
//! - `get_desktop_process_registry`: 获取当前受管进程清单
//! - `kill_desktop_process`: 定向终止指定子进程及其进程树
//!
//! [POS]
//! 供前端 Doctor 面板、诊断设置及进程监视器调用的 IPC 接口。

use tauri::{AppHandle, Manager, State};

use crate::runtime::{ManagedProcessEntry, ProcessRegistry};

/// 获取桌面端所有受管进程列表快照
#[tauri::command]
pub async fn get_desktop_process_registry(
    registry: State<'_, ProcessRegistry>,
) -> Result<Vec<ManagedProcessEntry>, String> {
    Ok(registry.snapshot_all().await)
}

/// 定向终止指定受管进程（级联销毁整棵子孙进程树）
#[tauri::command]
pub async fn kill_desktop_process(
    app: AppHandle,
    process_id: String,
    registry: State<'_, ProcessRegistry>,
) -> Result<String, String> {
    println!("🛑 Received request to kill managed process: {}", process_id);

    registry.kill_managed_process(&process_id).await?;

    // 广播进程被终止事件
    use tauri::Emitter;
    let _ = app.emit("desktop:process-killed", &process_id);

    Ok(format!("Managed process '{}' killed successfully", process_id))
}
