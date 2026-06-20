//! Agent Runner Sidecar 自动启动与事件转发
//!
//! [INPUT]
//! - sidecar::SidecarManager (POS: Agent Runner JSON-RPC 进程管理)
//! - commands::agent::AgentSystemState (POS: Agent IPC 状态容器)
//!
//! [OUTPUT]
//! - resolve_agent_runner_path: 开发/生产 Sidecar 路径解析
//! - bootstrap_agent_runner: 启动 Sidecar 并将事件转发到 Tauri emit
//!
//! [POS]
//! 桌面启动时 Agent Runner 的生命周期编排与 Sidecar 事件桥接。

use std::sync::Arc;
use std::time::Duration;

use tauri::{AppHandle, Emitter, Manager};

use crate::commands::agent::{AgentSystemState, SidecarStatus};
use crate::sidecar;

/// 解析 Agent Runner 可执行路径（开发：dist/index.js；生产：bundled 二进制）
pub fn resolve_agent_runner_path(app: &AppHandle) -> String {
    if cfg!(debug_assertions) {
        let tauri_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| ".".to_string());
        let project_root = std::path::Path::new(&tauri_dir)
            .parent()
            .and_then(|p| p.parent())
            .map(|p| p.to_path_buf())
            .unwrap_or_default();
        return project_root
            .join("myrm-agent-desktop/sidecar/agent-runner/src/index.ts")
            .to_string_lossy()
            .to_string();
    }

    let binary_name = if cfg!(target_os = "windows") {
        "binaries/agent-runner.exe"
    } else {
        "binaries/agent-runner"
    };
    app.path()
        .resolve(binary_name, tauri::path::BaseDirectory::Resource)
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_default()
}

/// 延迟启动 Agent Runner，并将 Sidecar 事件桥接到 Tauri 前端
pub fn bootstrap_agent_runner(agent_system: Arc<AgentSystemState>, app: &AppHandle) {
    let sidecar = agent_system.sidecar.clone();
    let sidecar_path = agent_system.sidecar_path.clone();
    let app_handle = app.clone();

    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(Duration::from_millis(1000)).await;

        let mut sidecar_guard = sidecar.lock().await;
        match sidecar_guard.start(&sidecar_path).await {
            Ok(_) => {
                println!("✅ Agent sidecar started");
                agent_system
                    .set_sidecar_status(SidecarStatus::Ready)
                    .await;
                let _ = app_handle.emit("agent-sidecar-ready", ());

                let mut event_rx = sidecar_guard.subscribe_events();
                drop(sidecar_guard);

                tokio::spawn(async move {
                    while let Ok(event) = event_rx.recv().await {
                        forward_sidecar_event(&app_handle, &event);
                    }
                });
            }
            Err(e) => {
                let msg = e.clone();
                eprintln!("⚠️  Agent sidecar not started: {}", msg);
                agent_system
                    .set_sidecar_status(SidecarStatus::Failed(msg.clone()))
                    .await;
                let _ = app_handle.emit("agent-sidecar-error", msg);
            }
        }
    });
}

fn forward_sidecar_event(app: &AppHandle, event: &sidecar::SidecarEvent) {
    match event {
        sidecar::SidecarEvent::AgentMessage { session_id, message } => {
            let event_name = format!("agent:message:{}", session_id);
            let _ = app.emit(&event_name, message);
        }
        sidecar::SidecarEvent::PermissionRequest { session_id, .. } => {
            let event_name = format!("agent:permission:{}", session_id);
            let _ = app.emit(&event_name, event);
        }
        sidecar::SidecarEvent::SessionStatus {
            session_id,
            status,
            error,
        } => {
            let event_name = format!("agent:status:{}", session_id);
            let _ = app.emit(&event_name, event);

            if status == "completed" || status == "error" {
                notify_task_finished_if_hidden(app, session_id, status, error.as_deref());
            }

            update_tray_tooltip(app, status);
        }
        sidecar::SidecarEvent::Error { message } => {
            let _ = app.emit("agent:error", message);
        }
    }
}

fn notify_task_finished_if_hidden(
    app: &AppHandle,
    session_id: &str,
    status: &str,
    error: Option<&str>,
) {
    let Some(window) = app.get_webview_window("main") else {
        return;
    };
    let is_visible = window.is_visible().unwrap_or(true);
    let is_minimized = window.is_minimized().unwrap_or(false);
    if is_visible && !is_minimized {
        return;
    }

    use tauri_plugin_notification::NotificationExt;
    let title = match status {
        "completed" => "任务已完成",
        "error" => "任务出错",
        _ => "MyrmAgent 通知",
    };
    let body = if let Some(e) = error {
        format!("会话: {}\n错误: {}", session_id, e)
    } else {
        format!("会话: {}", session_id)
    };
    let _ = app.notification().builder().title(title).body(body).show();
}

fn update_tray_tooltip(app: &AppHandle, status: &str) {
    let Some(tray) = app.tray_by_id("main") else {
        return;
    };
    let tooltip = match status {
        "running" => "MyrmAgent - 任务执行中...",
        "thinking" => "MyrmAgent - 思考中...",
        "error" => "MyrmAgent - 发生错误",
        "completed" => "MyrmAgent - 空闲",
        _ => "MyrmAgent",
    };
    let _ = tray.set_tooltip(Some(tooltip));
}
