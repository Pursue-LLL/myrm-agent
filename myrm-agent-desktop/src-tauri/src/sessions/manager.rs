//! CLI Agent 会话存储与 JSONL 持久化。

use std::collections::HashMap;
use std::sync::Arc;

use tokio::sync::RwLock;

use super::types::Session;
use crate::cli_agent_types::{PermissionMode, SessionStatus};

/// 会话管理器：内存存储 + 可选持久化。
pub struct SessionManager {
    sessions: Arc<RwLock<HashMap<String, Session>>>,
    storage_path: Option<std::path::PathBuf>,
}

impl SessionManager {
    pub fn new() -> Self {
        Self {
            sessions: Arc::new(RwLock::new(HashMap::new())),
            storage_path: None,
        }
    }

    pub fn with_storage(storage_path: std::path::PathBuf) -> Self {
        let manager = Self {
            sessions: Arc::new(RwLock::new(HashMap::new())),
            storage_path: Some(storage_path.clone()),
        };
        if let Ok(sessions) = Self::load_from_file(&storage_path) {
            let store = manager.sessions.clone();
            std::thread::spawn(move || {
                if let Ok(rt) = tokio::runtime::Runtime::new() {
                    rt.block_on(async {
                        let mut store_write = store.write().await;
                        for session in sessions {
                            store_write.insert(session.id.clone(), session);
                        }
                    });
                }
            });
        }
        manager
    }

    fn load_from_file(path: &std::path::Path) -> Result<Vec<Session>, String> {
        if !path.exists() {
            return Ok(vec![]);
        }
        let content = std::fs::read_to_string(path)
            .map_err(|e| format!("Failed to read sessions file: {}", e))?;
        let mut sessions = Vec::new();
        for line in content.lines() {
            if line.trim().is_empty() {
                continue;
            }
            match serde_json::from_str::<Session>(line) {
                Ok(session) => sessions.push(session),
                Err(e) => eprintln!("Failed to parse session line: {}", e),
            }
        }
        Ok(sessions)
    }

    async fn save_to_file(&self) {
        if let Some(ref path) = self.storage_path {
            let sessions = self.sessions.read().await;
            let mut content = String::new();
            for session in sessions.values() {
                if let Ok(line) = serde_json::to_string(session) {
                    content.push_str(&line);
                    content.push('\n');
                }
            }
            if let Err(e) = std::fs::write(path, content) {
                eprintln!("Failed to save sessions: {}", e);
            }
        }
    }

    pub async fn create_session(
        &self,
        agent_id: &str,
        cwd: &str,
        permission_mode: PermissionMode,
    ) -> Session {
        let session = Session::new(agent_id, cwd, permission_mode);
        self.sessions
            .write()
            .await
            .insert(session.id.clone(), session.clone());
        self.save_to_file().await;
        session
    }

    pub async fn get_session(&self, session_id: &str) -> Option<Session> {
        self.sessions.read().await.get(session_id).cloned()
    }

    pub async fn update_session(&self, session: Session) {
        self.sessions.write().await.insert(session.id.clone(), session);
        self.save_to_file().await;
    }

    pub async fn delete_session(&self, session_id: &str) -> Option<Session> {
        let result = self.sessions.write().await.remove(session_id);
        self.save_to_file().await;
        result
    }

    pub async fn list_sessions(&self) -> Vec<Session> {
        self.sessions.read().await.values().cloned().collect()
    }

    pub async fn list_sessions_by_status(&self, status: SessionStatus) -> Vec<Session> {
        self.sessions
            .read()
            .await
            .values()
            .filter(|s| s.status == status)
            .cloned()
            .collect()
    }

    pub async fn list_sessions_by_agent(&self, agent_id: &str) -> Vec<Session> {
        self.sessions
            .read()
            .await
            .values()
            .filter(|s| s.agent_id == agent_id)
            .cloned()
            .collect()
    }

    pub async fn list_flagged_sessions(&self) -> Vec<Session> {
        self.sessions
            .read()
            .await
            .values()
            .filter(|s| s.flagged)
            .cloned()
            .collect()
    }

    pub async fn set_session_status(
        &self,
        session_id: &str,
        status: SessionStatus,
    ) -> Option<Session> {
        let result = {
            let mut sessions = self.sessions.write().await;
            if let Some(session) = sessions.get_mut(session_id) {
                session.set_status(status);
                Some(session.clone())
            } else {
                None
            }
        };
        if result.is_some() {
            self.save_to_file().await;
        }
        result
    }

    pub async fn set_session_title(&self, session_id: &str, title: &str) -> Option<Session> {
        let mut sessions = self.sessions.write().await;
        if let Some(session) = sessions.get_mut(session_id) {
            session.set_title(title);
            return Some(session.clone());
        }
        None
    }

    pub async fn toggle_session_flag(&self, session_id: &str) -> Option<Session> {
        let mut sessions = self.sessions.write().await;
        if let Some(session) = sessions.get_mut(session_id) {
            session.toggle_flag();
            return Some(session.clone());
        }
        None
    }

    pub async fn count(&self) -> usize {
        self.sessions.read().await.len()
    }

    pub async fn cleanup_completed(&self, keep_count: usize) {
        let mut sessions = self.sessions.write().await;

        let mut completed: Vec<_> = sessions
            .values()
            .filter(|s| s.status == SessionStatus::Completed)
            .cloned()
            .collect();

        completed.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));

        for session in completed.iter().skip(keep_count) {
            sessions.remove(&session.id);
        }
    }
}

impl Default for SessionManager {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cli_agent_types::PermissionMode;

    #[tokio::test]
    async fn test_session_manager() {
        let manager = SessionManager::new();

        let session = manager
            .create_session("claude-code", "/home/user", PermissionMode::Ask)
            .await;
        assert_eq!(manager.count().await, 1);

        let retrieved = manager.get_session(&session.id).await;
        assert!(retrieved.is_some());
        assert_eq!(retrieved.unwrap().agent_id, "claude-code");

        manager
            .set_session_status(&session.id, SessionStatus::InProgress)
            .await;
        let updated = manager.get_session(&session.id).await.unwrap();
        assert_eq!(updated.status, SessionStatus::InProgress);

        manager.delete_session(&session.id).await;
        assert_eq!(manager.count().await, 0);
    }
}
