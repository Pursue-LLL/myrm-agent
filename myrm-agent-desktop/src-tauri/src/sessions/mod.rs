//! 会话管理模块
//!
//! [INPUT]
//! - cli_agent_types::{PermissionMode, SessionStatus} (POS: CLI 可视化共享类型)
//!
//! [OUTPUT]
//! - Session: 会话数据结构
//! - SessionManager: 会话 CRUD 与持久化
//!
//! [POS]
//! CLI Agent 会话生命周期管理。内存存储 + 可选 JSONL 持久化。

mod manager;
mod types;

pub use manager::SessionManager;
pub use types::Session;

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cli_agent_types::PermissionMode;

    #[test]
    fn test_session_creation() {
        let session = Session::new("claude-code", "/home/user", PermissionMode::Ask);
        assert!(!session.id.is_empty());
        assert_eq!(session.agent_id, "claude-code");
        assert_eq!(session.status, crate::cli_agent_types::SessionStatus::Pending);
        assert!(!session.flagged);
    }

    #[test]
    fn test_status_transitions() {
        use crate::cli_agent_types::SessionStatus;

        let mut session = Session::new("claude-code", "/home/user", PermissionMode::Ask);

        assert!(session.can_transition_to(SessionStatus::InProgress));
        session.set_status(SessionStatus::InProgress);
        assert_eq!(session.status, SessionStatus::InProgress);

        assert!(session.can_transition_to(SessionStatus::Completed));
        session.set_status(SessionStatus::Completed);
        assert_eq!(session.status, SessionStatus::Completed);

        assert!(session.can_transition_to(SessionStatus::InProgress));
    }
}
