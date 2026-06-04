//! CLI Agent 相关的 Tauri 命令
//!
//! 提供前端与 CLI Agent 交互的 API。
//! 唯一执行路径：Agent Runner Sidecar（`sidecar/agent-runner`）JSON-RPC。

mod message;
mod permission;
mod session;

pub use message::*;
pub use permission::*;
pub use session::*;

use std::sync::Arc;
use tokio::sync::Mutex;

use crate::cli_agent_types::{adapter_display_name, AdapterInfo, PermissionMode};
use crate::permissions::PermissionManager;
use crate::sessions::SessionManager;
use crate::sidecar::SidecarManager;

// ============================================================================
// Sidecar 状态
// ============================================================================

/// Agent Runner Sidecar 生命周期状态
#[derive(Debug, Clone)]
pub enum SidecarStatus {
    Starting,
    Ready,
    Failed(String),
}

// ============================================================================
// 状态类型
// ============================================================================

/// Agent 系统状态
pub struct AgentSystemState {
    pub sidecar: Arc<Mutex<SidecarManager>>,
    pub sidecar_status: Arc<Mutex<SidecarStatus>>,
    pub permission_manager: Arc<PermissionManager>,
    pub session_manager: Arc<SessionManager>,
    pub sidecar_path: String,
}

impl AgentSystemState {
    pub fn new(sidecar_path: String, app_data_dir: Option<std::path::PathBuf>) -> Self {
        let session_manager = if let Some(data_dir) = app_data_dir {
            let sessions_file = data_dir.join("sessions.jsonl");
            if let Some(parent) = sessions_file.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            SessionManager::with_storage(sessions_file)
        } else {
            SessionManager::new()
        };

        Self {
            sidecar: Arc::new(Mutex::new(SidecarManager::new())),
            sidecar_status: Arc::new(Mutex::new(SidecarStatus::Starting)),
            permission_manager: Arc::new(PermissionManager::new()),
            session_manager: Arc::new(session_manager),
            sidecar_path,
        }
    }

    pub async fn is_sidecar_running(&self) -> bool {
        self.sidecar.lock().await.is_running()
    }

    pub async fn set_sidecar_status(&self, status: SidecarStatus) {
        let mut guard = self.sidecar_status.lock().await;
        *guard = status;
    }

    pub async fn sidecar_status_snapshot(&self) -> SidecarStatus {
        self.sidecar_status.lock().await.clone()
    }
}

pub async fn ensure_sidecar_ready(state: &AgentSystemState) -> Result<(), String> {
    match state.sidecar_status_snapshot().await {
        SidecarStatus::Ready => {
            if state.is_sidecar_running().await {
                Ok(())
            } else {
                Err("Agent Runner process is not running".to_string())
            }
        }
        SidecarStatus::Starting => {
            Err("Agent Runner is still starting. Please retry in a moment.".to_string())
        }
        SidecarStatus::Failed(msg) => Err(format!("Agent Runner failed to start: {}", msg)),
    }
}

async fn call_detect_agents(state: &AgentSystemState) -> Result<Vec<String>, String> {
    ensure_sidecar_ready(state).await?;
    let mut sidecar = state.sidecar.lock().await;
    let result = sidecar.call("detect_agents", None).await?;
    if let Some(agents) = result.get("agents").and_then(|v| v.as_array()) {
        return Ok(agents
            .iter()
            .filter_map(|v| v.as_str().map(String::from))
            .collect());
    }
    Ok(Vec::new())
}

// ============================================================================
// Agent 检测命令
// ============================================================================

use tauri::State;

/// 检测可用的 CLI Agent
#[tauri::command]
pub async fn detect_agents(state: State<'_, AgentSystemState>) -> Result<Vec<String>, String> {
    call_detect_agents(&state).await
}

/// 获取所有适配器信息（与 detect_agents 同源）
#[tauri::command]
pub async fn list_agent_adapters(
    state: State<'_, AgentSystemState>,
) -> Result<Vec<AdapterInfo>, String> {
    let ids = call_detect_agents(&state).await?;
    Ok(ids
        .into_iter()
        .map(|id| AdapterInfo {
            name: adapter_display_name(&id),
            available: true,
            version: None,
            id,
        })
        .collect())
}

/// 查询 Agent Runner Sidecar 状态（供 CLI 面板展示）
#[tauri::command]
pub async fn get_agent_sidecar_status(
    state: State<'_, AgentSystemState>,
) -> Result<String, String> {
    let status = state.sidecar_status_snapshot().await;
    Ok(match status {
        SidecarStatus::Ready => "ready".to_string(),
        SidecarStatus::Starting => "starting".to_string(),
        SidecarStatus::Failed(msg) => format!("failed:{msg}"),
    })
}
