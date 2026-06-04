//! 消息发送命令

use tauri::State;

use crate::cli_agent_types::SessionStatus;
use super::{ensure_sidecar_ready, AgentSystemState};

/// 发送消息到 Agent（事件名: `agent:message:{session_id}`）
#[tauri::command]
pub async fn send_agent_message(
    state: State<'_, AgentSystemState>,
    session_id: String,
    prompt: String,
) -> Result<(), String> {
    ensure_sidecar_ready(&state).await?;

    let session = state
        .session_manager
        .get_session(&session_id)
        .await
        .ok_or_else(|| format!("Session not found: {}", session_id))?;

    state
        .session_manager
        .set_session_status(&session_id, SessionStatus::InProgress)
        .await;

    let sdk_session_id = session.sdk_session_id.as_ref().unwrap_or(&session_id);
    let params = serde_json::json!({
        "sessionId": sdk_session_id,
        "prompt": prompt,
    });

    let mut sidecar = state.sidecar.lock().await;
    sidecar
        .call("send_message", Some(params))
        .await
        .map_err(|e| format!("Failed to send message: {}", e))?;

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

    if !state.is_sidecar_running().await {
        return Ok(());
    }

    let sdk_session_id = session.sdk_session_id.as_ref().unwrap_or(&session_id);
    let params = serde_json::json!({ "sessionId": sdk_session_id });
    let mut sidecar = state.sidecar.lock().await;
    let _ = sidecar.call("stop_session", Some(params)).await;

    Ok(())
}
