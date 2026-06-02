//! CLI Agent 适配器模块
//!
//! 提供与各种 CLI Agent（Claude Code、Gemini CLI、Codex）交互的统一接口。
//! 借鉴 craft-agents 的设计理念，实现纯净、优雅的 Agent 抽象。

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use thiserror::Error;
use tokio::sync::mpsc;

pub mod claude_code;
pub mod codex;
pub mod gemini;

// ============================================================================
// 错误类型
// ============================================================================

/// Agent 错误类型
#[derive(Debug, Error)]
pub enum AgentError {
    #[error("Agent not found: {0}")]
    NotFound(String),

    #[error("Session not found: {0}")]
    SessionNotFound(String),

    #[error("Failed to start agent: {0}")]
    StartFailed(String),

    #[error("Failed to send message: {0}")]
    SendFailed(String),

    #[error("Agent process error: {0}")]
    ProcessError(String),

    #[error("Permission denied: {0}")]
    PermissionDenied(String),

    #[error("Timeout: {0}")]
    Timeout(String),
}

// ============================================================================
// 消息类型
// ============================================================================

/// Agent 消息类型
///
/// 统一的消息格式，用于 Agent 与前端之间的通信。
/// 借鉴 AionUi 的 msg_id 设计，支持流式消息合并。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum AgentMessage {
    /// 文本消息（流式）
    Text {
        content: String,
        msg_id: String,
    },

    /// 思考过程（借鉴 AionUi 的 thought_chunk）
    Thought {
        content: String,
    },

    /// 工具调用开始
    ToolCallStart {
        call_id: String,
        tool_name: String,
        arguments: serde_json::Value,
    },

    /// 工具调用结果
    ToolCallResult {
        call_id: String,
        content: String,
        status: ToolCallStatus,
    },

    /// 权限请求（借鉴 craft-agents 的精细控制）
    PermissionRequest {
        request_id: String,
        tool_name: String,
        command: String,
        is_dangerous: bool,
    },

    /// 会话状态变更
    SessionStatus {
        status: SessionStatus,
    },

    /// 错误消息
    Error {
        message: String,
    },

    /// 流结束
    Done,
}

/// 工具调用状态
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ToolCallStatus {
    Running,
    Completed,
    Failed,
}

/// 会话状态（借鉴 craft-agents 的状态工作流）
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
pub enum SessionStatus {
    #[default]
    Pending,
    InProgress,
    NeedsReview,
    Completed,
    Error,
}

// ============================================================================
// 权限模式
// ============================================================================

/// 权限模式（借鉴 craft-agents 的三级权限）
///
/// - Explore: 只读模式，阻止所有写操作
/// - Ask: 询问模式，危险操作需用户确认（默认）
/// - Auto: 自动模式，自动批准（危险命令除外）
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
pub enum PermissionMode {
    Explore,
    #[default]
    Ask,
    Auto,
}

impl PermissionMode {
    /// 循环切换到下一个模式（SHIFT+TAB 快捷键）
    pub fn next(self) -> Self {
        match self {
            Self::Explore => Self::Ask,
            Self::Ask => Self::Auto,
            Self::Auto => Self::Explore,
        }
    }

    /// 获取显示名称
    pub fn display_name(&self) -> &'static str {
        match self {
            Self::Explore => "Explore",
            Self::Ask => "Ask to Edit",
            Self::Auto => "Auto",
        }
    }
}

// ============================================================================
// 会话配置
// ============================================================================

/// 会话配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionConfig {
    /// 工作目录
    pub cwd: String,

    /// 权限模式
    #[serde(default)]
    pub permission_mode: PermissionMode,

    /// 恢复的会话 ID（用于继续之前的会话）
    pub resume_session_id: Option<String>,
}

// ============================================================================
// Agent 适配器 Trait
// ============================================================================

/// CLI Agent 适配器 trait
///
/// 所有 CLI Agent（Claude Code、Gemini CLI、Codex）都需要实现此 trait。
/// 采用纯净设计：
/// - 无全局状态
/// - 通过 channel 返回消息
/// - 明确的错误类型
#[async_trait]
pub trait CLIAgentAdapter: Send + Sync {
    /// 获取适配器名称
    fn name(&self) -> &'static str;

    /// 获取适配器 ID（用于配置和持久化）
    fn id(&self) -> &'static str;

    /// 检测 CLI 是否可用
    async fn detect(&self) -> bool;

    /// 获取 CLI 版本
    async fn version(&self) -> Option<String>;

    /// 启动新会话
    ///
    /// 返回 session_id
    async fn start_session(&self, config: SessionConfig) -> Result<String, AgentError>;

    /// 发送消息到会话
    ///
    /// 通过 tx channel 异步返回消息
    async fn send_message(
        &self,
        session_id: &str,
        prompt: &str,
        tx: mpsc::Sender<AgentMessage>,
    ) -> Result<(), AgentError>;

    /// 响应权限请求
    async fn respond_permission(
        &self,
        session_id: &str,
        request_id: &str,
        allowed: bool,
        always_allow: bool,
    ) -> Result<(), AgentError>;

    /// 停止会话
    async fn stop_session(&self, session_id: &str) -> Result<(), AgentError>;

    /// 获取所有活跃会话 ID
    fn active_sessions(&self) -> Vec<String>;
}

// ============================================================================
// Agent 管理器
// ============================================================================

/// Agent 管理器
///
/// 管理所有可用的 CLI Agent 适配器
pub struct AgentManager {
    adapters: Vec<Box<dyn CLIAgentAdapter>>,
}

impl AgentManager {
    /// 创建新的 Agent 管理器
    pub fn new() -> Self {
        Self {
            adapters: Vec::new(),
        }
    }

    /// 注册适配器
    pub fn register(&mut self, adapter: Box<dyn CLIAgentAdapter>) {
        self.adapters.push(adapter);
    }

    /// 检测所有可用的 Agent
    pub async fn detect_available(&self) -> Vec<&str> {
        let mut available = Vec::new();
        for adapter in &self.adapters {
            if adapter.detect().await {
                available.push(adapter.name());
            }
        }
        available
    }

    /// 根据名称获取适配器
    pub fn get_by_name(&self, name: &str) -> Option<&dyn CLIAgentAdapter> {
        self.adapters
            .iter()
            .find(|a| a.name() == name)
            .map(|a| a.as_ref())
    }

    /// 根据 ID 获取适配器
    pub fn get_by_id(&self, id: &str) -> Option<&dyn CLIAgentAdapter> {
        self.adapters
            .iter()
            .find(|a| a.id() == id)
            .map(|a| a.as_ref())
    }

    /// 获取所有适配器信息
    pub async fn list_adapters(&self) -> Vec<AdapterInfo> {
        let mut infos = Vec::new();
        for adapter in &self.adapters {
            let available = adapter.detect().await;
            let version = if available {
                adapter.version().await
            } else {
                None
            };
            infos.push(AdapterInfo {
                id: adapter.id().to_string(),
                name: adapter.name().to_string(),
                available,
                version,
            });
        }
        infos
    }
}

impl Default for AgentManager {
    fn default() -> Self {
        Self::new()
    }
}

/// 适配器信息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AdapterInfo {
    pub id: String,
    pub name: String,
    pub available: bool,
    pub version: Option<String>,
}
