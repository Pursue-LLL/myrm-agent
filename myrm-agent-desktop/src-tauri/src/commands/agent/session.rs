//! 会话管理命令

use tauri::State;

use crate::agents::{PermissionMode, SessionStatus};
use crate::sessions::Session;
use super::AgentSystemState;

/// 创建 Agent 会话
#[tauri::command]
pub async fn create_agent_session(
    state: State<'_, AgentSystemState>,
    agent_id: String,
    cwd: String,
    permission_mode: Option<PermissionMode>,
) -> Result<Session, String> {
    let mode = permission_mode.unwrap_or_default();

    // 创建会话记录
    let session = state
        .session_manager
        .create_session(&agent_id, &cwd, mode)
        .await;

    // 通过 Sidecar 创建会话
    let sidecar = state.sidecar.lock().await;
    if sidecar.is_running() {
        drop(sidecar);
        let mut sidecar = state.sidecar.lock().await;

        let params = serde_json::json!({
            "cwd": cwd,
            "permissionMode": mode,
        });

        match sidecar.call("create_session", Some(params)).await {
            Ok(result) => {
                if let Some(sdk_session_id) = result.get("sessionId").and_then(|v| v.as_str()) {
                    // 更新 SDK 会话 ID
                    if let Some(mut updated) =
                        state.session_manager.get_session(&session.id).await
                    {
                        updated.set_sdk_session_id(sdk_session_id);
                        state.session_manager.update_session(updated).await;
                    }
                }
            }
            Err(e) => {
                // 删除失败的会话
                state.session_manager.delete_session(&session.id).await;
                return Err(format!("Failed to create sidecar session: {}", e));
            }
        }
    }

    // 返回创建的会话
    state
        .session_manager
        .get_session(&session.id)
        .await
        .ok_or_else(|| "Session created but not found".to_string())
}

/// 获取会话列表
#[tauri::command]
pub async fn list_agent_sessions(
    state: State<'_, AgentSystemState>,
) -> Result<Vec<Session>, String> {
    Ok(state.session_manager.list_sessions().await)
}

/// 获取单个会话
#[tauri::command]
pub async fn get_agent_session(
    state: State<'_, AgentSystemState>,
    session_id: String,
) -> Result<Option<Session>, String> {
    Ok(state.session_manager.get_session(&session_id).await)
}

/// 删除会话
#[tauri::command]
pub async fn delete_agent_session(
    state: State<'_, AgentSystemState>,
    session_id: String,
) -> Result<(), String> {
    // 通过 Sidecar 停止会话
    {
        let sidecar = state.sidecar.lock().await;
        if sidecar.is_running() {
            drop(sidecar);
            let mut sidecar = state.sidecar.lock().await;
            let params = serde_json::json!({ "sessionId": session_id });
            let _ = sidecar.call("stop_session", Some(params)).await;
        }
    }

    // 删除会话记录
    state.session_manager.delete_session(&session_id).await;
    Ok(())
}

/// 恢复会话
///
/// 使用 CLI 的原生会话恢复功能（如 Claude SDK 的 resume 参数）
#[tauri::command]
pub async fn resume_agent_session(
    state: State<'_, AgentSystemState>,
    session_id: String,
) -> Result<Session, String> {
    // 获取会话
    let session = state
        .session_manager
        .get_session(&session_id)
        .await
        .ok_or_else(|| format!("Session not found: {}", session_id))?;

    // 检查是否有 SDK 会话 ID
    let sdk_session_id = session
        .sdk_session_id
        .as_ref()
        .ok_or_else(|| "Session has no SDK session ID, cannot resume".to_string())?;

    // 通过 Sidecar 恢复会话
    {
        let sidecar = state.sidecar.lock().await;
        if sidecar.is_running() {
            drop(sidecar);
            let mut sidecar = state.sidecar.lock().await;

            let params = serde_json::json!({
                "sessionId": sdk_session_id,
                "cwd": session.cwd,
                "permissionMode": session.permission_mode,
                "resume": true,
            });

            match sidecar.call("resume_session", Some(params)).await {
                Ok(_) => {
                    // 更新会话状态为进行中
                    state
                        .session_manager
                        .set_session_status(&session_id, SessionStatus::InProgress)
                        .await;
                }
                Err(e) => {
                    return Err(format!("Failed to resume session via sidecar: {}", e));
                }
            }
        } else {
            return Err("Sidecar not running, cannot resume session".to_string());
        }
    }

    // 返回更新后的会话
    state
        .session_manager
        .get_session(&session_id)
        .await
        .ok_or_else(|| "Session not found after resume".to_string())
}
