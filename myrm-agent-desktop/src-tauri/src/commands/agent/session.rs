//! 会话管理命令

use tauri::State;

use super::{ensure_sidecar_ready, AgentSystemState};
use crate::cli_agent_types::{PermissionMode, SessionStatus};
use crate::sessions::Session;

/// 创建 Agent 会话
#[tauri::command]
pub async fn create_agent_session(
    state: State<'_, AgentSystemState>,
    agent_id: String,
    cwd: String,
    permission_mode: Option<PermissionMode>,
) -> Result<Session, String> {
    ensure_sidecar_ready(&state).await?;

    let mode = permission_mode.unwrap_or_default();
    let session = state
        .session_manager
        .create_session(&agent_id, &cwd, mode)
        .await;

    let params = serde_json::json!({
        "cwd": cwd,
        "permissionMode": mode.as_sidecar_str(),
    });

    let mut sidecar = state.sidecar.lock().await;
    match sidecar.call("create_session", Some(params)).await {
        Ok(result) => {
            if let Some(sdk_session_id) = result.get("sessionId").and_then(|v| v.as_str()) {
                if let Some(mut updated) = state.session_manager.get_session(&session.id).await {
                    updated.set_sdk_session_id(sdk_session_id);
                    state.session_manager.update_session(updated).await;
                }
            }
        }
        Err(e) => {
            state.session_manager.delete_session(&session.id).await;
            return Err(format!("Failed to create sidecar session: {}", e));
        }
    }

    state
        .session_manager
        .get_session(&session.id)
        .await
        .ok_or_else(|| "Session created but not found".to_string())
}

#[tauri::command]
pub async fn list_agent_sessions(
    state: State<'_, AgentSystemState>,
) -> Result<Vec<Session>, String> {
    Ok(state.session_manager.list_sessions().await)
}

#[tauri::command]
pub async fn get_agent_session(
    state: State<'_, AgentSystemState>,
    session_id: String,
) -> Result<Option<Session>, String> {
    Ok(state.session_manager.get_session(&session_id).await)
}

#[tauri::command]
pub async fn delete_agent_session(
    state: State<'_, AgentSystemState>,
    session_id: String,
) -> Result<(), String> {
    if state.is_sidecar_running().await {
        let params = serde_json::json!({ "sessionId": session_id });
        let mut sidecar = state.sidecar.lock().await;
        let _ = sidecar.call("stop_session", Some(params)).await;
    }

    state.session_manager.delete_session(&session_id).await;
    Ok(())
}

/// 恢复会话：通过 `create_session` + `resumeSessionId` 绑定 Claude SDK 会话
#[tauri::command]
pub async fn resume_agent_session(
    state: State<'_, AgentSystemState>,
    session_id: String,
) -> Result<Session, String> {
    ensure_sidecar_ready(&state).await?;

    let session = state
        .session_manager
        .get_session(&session_id)
        .await
        .ok_or_else(|| format!("Session not found: {}", session_id))?;

    let sdk_session_id = session
        .sdk_session_id
        .as_ref()
        .ok_or_else(|| "Session has no SDK session ID, cannot resume".to_string())?;

    let params = serde_json::json!({
        "cwd": session.cwd,
        "permissionMode": session.permission_mode.as_sidecar_str(),
        "resumeSessionId": sdk_session_id,
    });

    let mut sidecar = state.sidecar.lock().await;
    let result = sidecar
        .call("create_session", Some(params))
        .await
        .map_err(|e| format!("Failed to resume session via sidecar: {}", e))?;

    if let Some(new_runner_session_id) = result.get("sessionId").and_then(|v| v.as_str()) {
        if let Some(mut updated) = state.session_manager.get_session(&session_id).await {
            updated.set_sdk_session_id(new_runner_session_id);
            state.session_manager.update_session(updated).await;
        }
    }

    state
        .session_manager
        .set_session_status(&session_id, SessionStatus::InProgress)
        .await;

    state
        .session_manager
        .get_session(&session_id)
        .await
        .ok_or_else(|| "Session not found after resume".to_string())
}
