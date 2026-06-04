//! CLI Agent 共享类型（会话状态、权限模式、适配器元数据）
//!
//! [INPUT]
//! - 无（纯类型定义）
//!
//! [OUTPUT]
//! - PermissionMode / SessionStatus / AdapterInfo：供 sessions、permissions、commands/agent 序列化
//!
//! [POS]
//! CLI 可视化功能的跨模块类型契约；执行逻辑由 Agent Runner Sidecar 承担。

use serde::{Deserialize, Serialize};

/// 会话状态
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

/// 权限模式
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
pub enum PermissionMode {
    Explore,
    #[default]
    Ask,
    Auto,
}

impl PermissionMode {
    pub fn next(self) -> Self {
        match self {
            Self::Explore => Self::Ask,
            Self::Ask => Self::Auto,
            Self::Auto => Self::Explore,
        }
    }

    pub fn display_name(&self) -> &'static str {
        match self {
            Self::Explore => "Explore",
            Self::Ask => "Ask to Edit",
            Self::Auto => "Auto",
        }
    }

    pub fn from_sidecar_str(s: &str) -> Self {
        match s {
            "explore" => Self::Explore,
            "auto" => Self::Auto,
            _ => Self::Ask,
        }
    }

    pub fn as_sidecar_str(self) -> &'static str {
        match self {
            Self::Explore => "explore",
            Self::Ask => "ask",
            Self::Auto => "auto",
        }
    }
}

/// 适配器信息（与前端 `cli-agent.ts` AdapterInfo 对齐）
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AdapterInfo {
    pub id: String,
    pub name: String,
    pub available: bool,
    pub version: Option<String>,
}

pub fn adapter_display_name(id: &str) -> String {
    match id {
        "claude-code" => "Claude Code".to_string(),
        "codex" => "Codex".to_string(),
        "gemini-cli" | "gemini" => "Gemini CLI".to_string(),
        other => other.to_string(),
    }
}
