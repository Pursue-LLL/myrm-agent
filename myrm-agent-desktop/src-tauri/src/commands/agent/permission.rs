//! 权限管理命令

use tauri::State;

use crate::agents::PermissionMode;
use super::AgentSystemState;

/// 响应权限请求
#[tauri::command]
pub async fn respond_agent_permission(
    state: State<'_, AgentSystemState>,
    session_id: String,
    request_id: String,
    allowed: bool,
    always_allow: bool,
) -> Result<(), String> {
    // 通过 Sidecar 响应
    let sidecar = state.sidecar.lock().await;
    if sidecar.is_running() {
        drop(sidecar);
        let mut sidecar = state.sidecar.lock().await;

        let params = serde_json::json!({
            "sessionId": session_id,
            "requestId": request_id,
            "allowed": allowed,
            "alwaysAllow": always_allow,
        });

        sidecar
            .call("respond_permission", Some(params))
            .await
            .map_err(|e| format!("Failed to respond permission: {}", e))?;
    }

    Ok(())
}

/// 获取当前权限模式
#[tauri::command]
pub async fn get_permission_mode(
    state: State<'_, AgentSystemState>,
) -> Result<PermissionMode, String> {
    // 优先从 Sidecar 获取
    {
        let sidecar = state.sidecar.lock().await;
        if sidecar.is_running() {
            drop(sidecar);
            let mut sidecar = state.sidecar.lock().await;
            if let Ok(result) = sidecar.call("get_permission_mode", None).await {
                if let Some(mode_str) = result.get("mode").and_then(|v| v.as_str()) {
                    return match mode_str {
                        "explore" => Ok(PermissionMode::Explore),
                        "ask" => Ok(PermissionMode::Ask),
                        "auto" => Ok(PermissionMode::Auto),
                        _ => Ok(PermissionMode::Ask),
                    };
                }
            }
        }
    }

    // 回退到 Rust 实现
    Ok(state.permission_manager.get_mode().await)
}

/// 设置权限模式
#[tauri::command]
pub async fn set_permission_mode(
    state: State<'_, AgentSystemState>,
    mode: PermissionMode,
) -> Result<(), String> {
    // 同步到 Sidecar
    {
        let sidecar = state.sidecar.lock().await;
        if sidecar.is_running() {
            drop(sidecar);
            let mut sidecar = state.sidecar.lock().await;

            let mode_str = match mode {
                PermissionMode::Explore => "explore",
                PermissionMode::Ask => "ask",
                PermissionMode::Auto => "auto",
            };

            let params = serde_json::json!({ "mode": mode_str });
            let _ = sidecar.call("set_permission_mode", Some(params)).await;
        }
    }

    // 更新本地状态
    state.permission_manager.set_mode(mode).await;
    Ok(())
}

/// 循环切换权限模式（SHIFT+TAB）
#[tauri::command]
pub async fn cycle_permission_mode(
    state: State<'_, AgentSystemState>,
) -> Result<PermissionMode, String> {
    // 通过 Sidecar 切换
    {
        let sidecar = state.sidecar.lock().await;
        if sidecar.is_running() {
            drop(sidecar);
            let mut sidecar = state.sidecar.lock().await;
            if let Ok(result) = sidecar.call("cycle_permission_mode", None).await {
                if let Some(mode_str) = result.get("mode").and_then(|v| v.as_str()) {
                    let mode = match mode_str {
                        "explore" => PermissionMode::Explore,
                        "ask" => PermissionMode::Ask,
                        "auto" => PermissionMode::Auto,
                        _ => PermissionMode::Ask,
                    };
                    // 同步本地状态
                    state.permission_manager.set_mode(mode).await;
                    return Ok(mode);
                }
            }
        }
    }

    // 回退到 Rust 实现
    Ok(state.permission_manager.cycle_mode().await)
}
