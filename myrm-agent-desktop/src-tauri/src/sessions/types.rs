//! CLI Agent 会话数据结构与状态转换。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::cli_agent_types::{PermissionMode, SessionStatus};

/// 会话信息
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Session {
    pub id: String,
    pub agent_id: String,
    pub title: Option<String>,
    pub cwd: String,
    pub status: SessionStatus,
    pub permission_mode: PermissionMode,
    pub sdk_session_id: Option<String>,
    pub created_at: u64,
    pub updated_at: u64,
    pub flagged: bool,
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

impl Session {
    pub fn new(agent_id: &str, cwd: &str, permission_mode: PermissionMode) -> Self {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_millis() as u64;

        Self {
            id: uuid::Uuid::new_v4().to_string(),
            agent_id: agent_id.to_string(),
            title: None,
            cwd: cwd.to_string(),
            status: SessionStatus::Pending,
            permission_mode,
            sdk_session_id: None,
            created_at: now,
            updated_at: now,
            flagged: false,
            metadata: HashMap::new(),
        }
    }

    pub fn set_status(&mut self, status: SessionStatus) {
        if self.can_transition_to(status) {
            self.status = status;
            self.touch();
        }
    }

    pub fn can_transition_to(&self, target: SessionStatus) -> bool {
        use SessionStatus::*;

        if self.status == target {
            return true;
        }

        matches!(
            (self.status, target),
            (Pending, InProgress)
                | (Pending, Completed)
                | (InProgress, NeedsReview)
                | (InProgress, Completed)
                | (InProgress, Error)
                | (NeedsReview, InProgress)
                | (NeedsReview, Completed)
                | (Completed, InProgress)
                | (Error, InProgress)
        )
    }

    pub fn touch(&mut self) {
        self.updated_at = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_millis() as u64;
    }

    pub fn set_title(&mut self, title: &str) {
        self.title = Some(title.to_string());
        self.touch();
    }

    pub fn toggle_flag(&mut self) {
        self.flagged = !self.flagged;
        self.touch();
    }

    pub fn set_sdk_session_id(&mut self, sdk_id: &str) {
        self.sdk_session_id = Some(sdk_id.to_string());
        self.touch();
    }
}
