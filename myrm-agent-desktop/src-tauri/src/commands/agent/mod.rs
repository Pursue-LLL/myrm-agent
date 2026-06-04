//! CLI Agent 相关的 Tauri 命令
//!
//! 提供前端与 CLI Agent 交互的 API。
//! 主路径：Agent Runner Sidecar（`sidecar/agent-runner` 编译二进制）JSON-RPC。
//! 备用：Rust `agents/` 适配器（Sidecar 未运行时）。

mod message;
mod permission;
mod session;

// 重新导出所有命令
pub use message::*;
pub use permission::*;
pub use session::*;

use std::sync::Arc;
use tokio::sync::Mutex;

use crate::agents::AgentManager;
use crate::agents::claude_code::ClaudeCodeAdapter;
use crate::permissions::PermissionManager;
use crate::sessions::SessionManager;
use crate::sidecar::SidecarManager;

// ============================================================================
// 状态类型
// ============================================================================

/// Agent 系统状态
pub struct AgentSystemState {
    /// Sidecar 管理器（主要通道）
    pub sidecar: Arc<Mutex<SidecarManager>>,
    /// Agent 管理器（Rust 备用实现）
    pub agent_manager: Arc<Mutex<AgentManager>>,
    /// 权限管理器
    pub permission_manager: Arc<PermissionManager>,
    /// 会话管理器
    pub session_manager: Arc<SessionManager>,
    /// Sidecar 路径
    pub sidecar_path: String,
}

impl AgentSystemState {
    /// 创建并初始化 Agent 系统
    pub fn new(sidecar_path: String, app_data_dir: Option<std::path::PathBuf>) -> Self {
        let mut agent_manager = AgentManager::new();

        // 注册 Rust 适配器作为备用
        agent_manager.register(Box::new(ClaudeCodeAdapter::new()));

        // 配置会话持久化路径
        let session_manager = if let Some(data_dir) = app_data_dir {
            let sessions_file = data_dir.join("sessions.jsonl");
            // 确保目录存在
            if let Some(parent) = sessions_file.parent() {
                let _ = std::fs::create_dir_all(parent);
            }
            SessionManager::with_storage(sessions_file)
        } else {
            SessionManager::new()
        };

        Self {
            sidecar: Arc::new(Mutex::new(SidecarManager::new())),
            agent_manager: Arc::new(Mutex::new(agent_manager)),
            permission_manager: Arc::new(PermissionManager::new()),
            session_manager: Arc::new(session_manager),
            sidecar_path,
        }
    }

    /// 启动 Sidecar
    pub async fn start_sidecar(&self) -> Result<(), String> {
        let mut sidecar = self.sidecar.lock().await;
        sidecar.start(&self.sidecar_path).await
    }

    /// 检查 Sidecar 是否运行
    pub async fn is_sidecar_running(&self) -> bool {
        let sidecar = self.sidecar.lock().await;
        sidecar.is_running()
    }
}

// ============================================================================
// Agent 检测命令
// ============================================================================

use tauri::State;
use crate::agents::AdapterInfo;

/// 检测可用的 CLI Agent
#[tauri::command]
pub async fn detect_agents(state: State<'_, AgentSystemState>) -> Result<Vec<String>, String> {
    let sidecar = state.sidecar.lock().await;

    if sidecar.is_running() {
        // 通过 Sidecar 检测
        drop(sidecar);
        let mut sidecar = state.sidecar.lock().await;
        let result = sidecar.call("detect_agents", None).await?;

        if let Some(agents) = result.get("agents").and_then(|v| v.as_array()) {
            return Ok(agents
                .iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect());
        }
    }

    // 回退到 Rust 实现
    let manager = state.agent_manager.lock().await;
    let available = manager.detect_available().await;
    Ok(available.into_iter().map(String::from).collect())
}

/// 获取所有适配器信息
#[tauri::command]
pub async fn list_agent_adapters(
    state: State<'_, AgentSystemState>,
) -> Result<Vec<AdapterInfo>, String> {
    // 使用 Rust 实现获取适配器列表
    let manager = state.agent_manager.lock().await;
    Ok(manager.list_adapters().await)
}
