//! 权限管理命令

use tauri::State;

use crate::cli_agent_types::PermissionMode;
use super::{ensure_sidecar_ready, AgentSystemState};

// ============================================================================
// OS 系统权限探针（macOS Accessibility / Screen Recording）
// ============================================================================

/// 检测 macOS Accessibility 权限是否已授予。
/// Windows/Linux 始终返回 true（无此限制）。
#[tauri::command]
pub async fn check_accessibility_permission() -> Result<bool, String> {
    #[cfg(target_os = "macos")]
    {
        Ok(macos_accessibility_trusted())
    }
    #[cfg(not(target_os = "macos"))]
    {
        Ok(true)
    }
}

#[cfg(target_os = "macos")]
fn macos_accessibility_trusted() -> bool {
    use std::process::Command;
    // Use osascript to probe AX access — same technique as appshot.rs
    let result = Command::new("osascript")
        .args(["-e", r#"tell application "System Events" to get name of first application process whose frontmost is true"#])
        .output();
    match result {
        Ok(output) => {
            if output.status.success() {
                return true;
            }
            let stderr = String::from_utf8_lossy(&output.stderr);
            !(stderr.contains("不允许辅助访问") || stderr.to_lowercase().contains("not allowed assistive"))
        }
        Err(_) => false,
    }
}

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
