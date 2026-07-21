//! Agent Runner JSON-RPC 协议类型与 Sidecar 事件定义。
//!
//! [INPUT]
//! - serde JSON 协议（agent-runner sidecar stdout 行）
//!
//! [OUTPUT]
//! - SidecarEvent: 广播给 Tauri 前端的 Agent/权限/会话事件
//! - RPCRequest / RPCResponse / RPCNotification: stdio JSON-RPC 帧
//!
//! [POS]
//! agent_runner_rpc 协议层类型；进程管理与 IO 见 `transport.rs` 与 `mod.rs`。

use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize)]
pub(crate) struct RPCRequest {
    pub jsonrpc: &'static str,
    pub id: u64,
    pub method: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub params: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
pub(crate) struct RPCResponse {
    pub jsonrpc: String,
    pub id: u64,
    pub result: Option<serde_json::Value>,
    pub error: Option<RPCError>,
}

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
pub(crate) struct RPCError {
    pub code: i32,
    pub message: String,
}

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
pub(crate) struct RPCNotification {
    pub jsonrpc: String,
    pub method: String,
    pub params: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum SidecarEvent {
    /// Agent 消息
    AgentMessage {
        session_id: String,
        message: serde_json::Value,
    },
    /// 权限请求
    PermissionRequest {
        session_id: String,
        request_id: String,
        tool_name: String,
        command: String,
        is_dangerous: bool,
    },
    /// 会话状态
    SessionStatus {
        session_id: String,
        status: String,
        error: Option<String>,
    },
    /// 错误
    Error { message: String },
}
