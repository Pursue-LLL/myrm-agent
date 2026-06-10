//! 权限管理命令

use tauri::State;

use crate::cli_agent_types::PermissionMode;
use super::{ensure_sidecar_ready, AgentSystemState};

#[tauri::command]
pub async fn respond_agent_permission(
    state: State<'_, AgentSystemState>,
    session_id: String,
    request_id: String,
    allowed: bool,
    always_allow: bool,
) -> Result<(), String> {
    ensure_sidecar_ready(&state).await?;

    let params = serde_json::json!({
        "sessionId": session_id,
        "requestId": request_id,
        "allowed": allowed,
        "alwaysAllow": always_allow,
    });

    let mut sidecar = state.sidecar.lock().await;
    sidecar
        .call("respond_permission", Some(params))
        .await
        .map_err(|e| format!("Failed to respond permission: {}", e))?;

    Ok(())
}

#[tauri::command]
pub async fn get_permission_mode(
    state: State<'_, AgentSystemState>,
) -> Result<PermissionMode, String> {
    if state.is_sidecar_running().await {
        let mut sidecar = state.sidecar.lock().await;
        if let Ok(result) = sidecar.call("get_permission_mode", None).await {
            if let Some(mode_str) = result.get("mode").and_then(|v| v.as_str()) {
                return Ok(PermissionMode::from_sidecar_str(mode_str));
            }
        }
    }

    Ok(state.permission_manager.get_mode().await)
}

#[tauri::command]
pub async fn set_permission_mode(
    state: State<'_, AgentSystemState>,
    mode: PermissionMode,
) -> Result<(), String> {
    if state.is_sidecar_running().await {
        let mut sidecar = state.sidecar.lock().await;
        let params = serde_json::json!({ "mode": mode.as_sidecar_str() });
        let _ = sidecar.call("set_permission_mode", Some(params)).await;
    }

    state.permission_manager.set_mode(mode).await;
    Ok(())
}

#[tauri::command]
pub async fn cycle_permission_mode(
    state: State<'_, AgentSystemState>,
) -> Result<PermissionMode, String> {
    if state.is_sidecar_running().await {
        let mut sidecar = state.sidecar.lock().await;
        if let Ok(result) = sidecar.call("cycle_permission_mode", None).await {
            if let Some(mode_str) = result.get("mode").and_then(|v| v.as_str()) {
                let mode = PermissionMode::from_sidecar_str(mode_str);
                state.permission_manager.set_mode(mode).await;
                return Ok(mode);
            }
        }
    }

    Ok(state.permission_manager.cycle_mode().await)
}
