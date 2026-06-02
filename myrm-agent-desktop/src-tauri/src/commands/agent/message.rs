//! 消息发送命令

use tauri::{AppHandle, Emitter, State};

use crate::agents::{AgentMessage, SessionStatus};
use super::AgentSystemState;

/// 发送消息到 Agent
///
/// 通过 Tauri 事件流式返回响应。
/// 事件名称: `agent:message:{session_id}`
#[tauri::command]
pub async fn send_agent_message(
    app: AppHandle,
    state: State<'_, AgentSystemState>,
    session_id: String,
    prompt: String,
) -> Result<(), String> {
    // 获取会话
    let session = state
        .session_manager
        .get_session(&session_id)
        .await
        .ok_or_else(|| format!("Session not found: {}", session_id))?;

    // 更新会话状态为进行中
    state
        .session_manager
        .set_session_status(&session_id, SessionStatus::InProgress)
        .await;

    // 通过 Sidecar 发送消息
    {
        let sidecar = state.sidecar.lock().await;
        if sidecar.is_running() {
            drop(sidecar);
            let mut sidecar = state.sidecar.lock().await;

            // 获取 SDK 会话 ID
            let sdk_session_id = session.sdk_session_id.as_ref().unwrap_or(&session_id);

            let params = serde_json::json!({
                "sessionId": sdk_session_id,
                "prompt": prompt,
            });

            // 发送消息（异步，通过事件返回结果）
            sidecar
                .call("send_message", Some(params))
                .await
                .map_err(|e| format!("Failed to send message: {}", e))?;

            // Sidecar 会通过 JSON-RPC notification 发送事件
            // 这些事件会被 SidecarManager::read_stdout 捕获
            // 然后转发到 Tauri 事件系统

            return Ok(());
        }
    }

    // 回退到 Rust 实现
    let (tx, mut rx) = tokio::sync::mpsc::channel::<AgentMessage>(100);

    {
        let manager = state.agent_manager.lock().await;
        if let Some(adapter) = manager.get_by_id(&session.agent_id) {
            adapter
                .send_message(&session_id, &prompt, tx)
                .await
                .map_err(|e| format!("Failed to send message: {}", e))?;
        } else {
            return Err(format!("Agent not found: {}", session.agent_id));
        }
    }

    // 在后台处理消息并转发到前端
    let event_name = format!("agent:message:{}", session_id);
    let session_id_clone = session_id.clone();
    let session_manager = state.session_manager.clone();

    tokio::spawn(async move {
        while let Some(msg) = rx.recv().await {
            // 检查会话完成状态
            if let AgentMessage::SessionStatus { status } = &msg {
                session_manager
                    .set_session_status(&session_id_clone, *status)
                    .await;
            }

            // 发送事件到前端
            if let Err(e) = app.emit(&event_name, &msg) {
                eprintln!("Failed to emit event: {}", e);
                break;
            }

            // 结束信号
            if matches!(msg, AgentMessage::Done) {
                break;
            }
        }
    });

    Ok(())
}

/// 停止 Agent 消息流
#[tauri::command]
pub async fn stop_agent_message(
    state: State<'_, AgentSystemState>,
    session_id: String,
) -> Result<(), String> {
    let session = state
        .session_manager
        .get_session(&session_id)
        .await
        .ok_or_else(|| format!("Session not found: {}", session_id))?;

    // 通过 Sidecar 停止
    {
        let sidecar = state.sidecar.lock().await;
        if sidecar.is_running() {
            drop(sidecar);
            let mut sidecar = state.sidecar.lock().await;
            let sdk_session_id = session.sdk_session_id.as_ref().unwrap_or(&session_id);
            let params = serde_json::json!({ "sessionId": sdk_session_id });
            let _ = sidecar.call("stop_session", Some(params)).await;
            return Ok(());
        }
    }

    // 回退到 Rust 实现
    let manager = state.agent_manager.lock().await;
    if let Some(adapter) = manager.get_by_id(&session.agent_id) {
        adapter
            .stop_session(&session_id)
            .await
            .map_err(|e| format!("Failed to stop: {}", e))?;
    }

    Ok(())
}
