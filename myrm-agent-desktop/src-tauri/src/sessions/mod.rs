//! 会话管理模块
//!
//! 管理 CLI Agent 会话的生命周期和状态。
//! 借鉴 craft-agents 的状态工作流设计。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

use crate::agents::{PermissionMode, SessionStatus};

// ============================================================================
// 会话数据结构
// ============================================================================

/// 会话信息
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Session {
    /// 会话 ID
    pub id: String,

    /// 关联的 Agent ID
    pub agent_id: String,

    /// 会话标题（可由 AI 生成）
    pub title: Option<String>,

    /// 工作目录
    pub cwd: String,

    /// 会话状态
    pub status: SessionStatus,

    /// 权限模式
    pub permission_mode: PermissionMode,

    /// SDK 内部会话 ID（用于恢复）
    pub sdk_session_id: Option<String>,

    /// 创建时间（Unix 时间戳毫秒）
    pub created_at: u64,

    /// 更新时间（Unix 时间戳毫秒）
    pub updated_at: u64,

    /// 是否标记（重要会话）
    pub flagged: bool,

    /// 元数据
    #[serde(default)]
    pub metadata: HashMap<String, serde_json::Value>,
}

impl Session {
    /// 创建新会话
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

    /// 更新状态
    pub fn set_status(&mut self, status: SessionStatus) {
        // 验证状态转换是否有效
        if self.can_transition_to(status) {
            self.status = status;
            self.touch();
        }
    }

    /// 检查是否可以转换到目标状态
    pub fn can_transition_to(&self, target: SessionStatus) -> bool {
        use SessionStatus::*;
        
        // 状态保持不变总是允许的
        if self.status == target {
            return true;
        }
        
        matches!(
            (self.status, target),
            // Pending 可以转换为 InProgress 或 Completed
            (Pending, InProgress) | (Pending, Completed) |
            // InProgress 可以转换为 NeedsReview、Completed 或 Error
            (InProgress, NeedsReview) | (InProgress, Completed) | (InProgress, Error) |
            // NeedsReview 可以转换为 InProgress 或 Completed
            (NeedsReview, InProgress) | (NeedsReview, Completed) |
            // Completed 可以重新打开
            (Completed, InProgress) |
            // Error 可以重试
            (Error, InProgress)
        )
    }

    /// 更新时间戳
    pub fn touch(&mut self) {
        self.updated_at = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_millis() as u64;
    }

    /// 设置标题
    pub fn set_title(&mut self, title: &str) {
        self.title = Some(title.to_string());
        self.touch();
    }

    /// 切换标记状态
    pub fn toggle_flag(&mut self) {
        self.flagged = !self.flagged;
        self.touch();
    }

    /// 设置 SDK 会话 ID
    pub fn set_sdk_session_id(&mut self, sdk_id: &str) {
        self.sdk_session_id = Some(sdk_id.to_string());
        self.touch();
    }
}

// ============================================================================
// 会话管理器
// ============================================================================

/// 会话管理器
///
/// 管理所有会话的生命周期，支持持久化。
pub struct SessionManager {
    /// 会话存储
    sessions: Arc<RwLock<HashMap<String, Session>>>,
    /// 持久化文件路径
    storage_path: Option<std::path::PathBuf>,
}

impl SessionManager {
    /// 创建新的会话管理器
    pub fn new() -> Self {
        Self {
            sessions: Arc::new(RwLock::new(HashMap::new())),
            storage_path: None,
        }
    }

    /// 创建带持久化的会话管理器
    pub fn with_storage(storage_path: std::path::PathBuf) -> Self {
        let manager = Self {
            sessions: Arc::new(RwLock::new(HashMap::new())),
            storage_path: Some(storage_path.clone()),
        };
        // 尝试加载已有会话
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

    /// 从文件加载会话
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

    /// 保存会话到文件
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

    /// 创建新会话
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

    /// 获取会话
    pub async fn get_session(&self, session_id: &str) -> Option<Session> {
        self.sessions.read().await.get(session_id).cloned()
    }

    /// 更新会话
    pub async fn update_session(&self, session: Session) {
        self.sessions.write().await.insert(session.id.clone(), session);
        self.save_to_file().await;
    }

    /// 删除会话
    pub async fn delete_session(&self, session_id: &str) -> Option<Session> {
        let result = self.sessions.write().await.remove(session_id);
        self.save_to_file().await;
        result
    }

    /// 获取所有会话
    pub async fn list_sessions(&self) -> Vec<Session> {
        self.sessions.read().await.values().cloned().collect()
    }

    /// 按状态筛选会话
    pub async fn list_sessions_by_status(&self, status: SessionStatus) -> Vec<Session> {
        self.sessions
            .read()
            .await
            .values()
            .filter(|s| s.status == status)
            .cloned()
            .collect()
    }

    /// 按 Agent 筛选会话
    pub async fn list_sessions_by_agent(&self, agent_id: &str) -> Vec<Session> {
        self.sessions
            .read()
            .await
            .values()
            .filter(|s| s.agent_id == agent_id)
            .cloned()
            .collect()
    }

    /// 获取标记的会话
    pub async fn list_flagged_sessions(&self) -> Vec<Session> {
        self.sessions
            .read()
            .await
            .values()
            .filter(|s| s.flagged)
            .cloned()
            .collect()
    }

    /// 更新会话状态
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

    /// 设置会话标题
    pub async fn set_session_title(&self, session_id: &str, title: &str) -> Option<Session> {
        let mut sessions = self.sessions.write().await;
        if let Some(session) = sessions.get_mut(session_id) {
            session.set_title(title);
            return Some(session.clone());
        }
        None
    }

    /// 切换会话标记
    pub async fn toggle_session_flag(&self, session_id: &str) -> Option<Session> {
        let mut sessions = self.sessions.write().await;
        if let Some(session) = sessions.get_mut(session_id) {
            session.toggle_flag();
            return Some(session.clone());
        }
        None
    }

    /// 获取会话数量
    pub async fn count(&self) -> usize {
        self.sessions.read().await.len()
    }

    /// 清理已完成的会话（保留最近 N 个）
    pub async fn cleanup_completed(&self, keep_count: usize) {
        let mut sessions = self.sessions.write().await;

        // 找出已完成的会话
        let mut completed: Vec<_> = sessions
            .values()
            .filter(|s| s.status == SessionStatus::Completed)
            .cloned()
            .collect();

        // 按更新时间排序（最新在前）
        completed.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));

        // 删除超出保留数量的会话
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

// ============================================================================
// 测试
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_session_creation() {
        let session = Session::new("claude-code", "/home/user", PermissionMode::Ask);
        assert!(!session.id.is_empty());
        assert_eq!(session.agent_id, "claude-code");
        assert_eq!(session.status, SessionStatus::Pending);
        assert!(!session.flagged);
    }

    #[test]
    fn test_status_transitions() {
        let mut session = Session::new("claude-code", "/home/user", PermissionMode::Ask);

        // Pending -> InProgress: 允许
        assert!(session.can_transition_to(SessionStatus::InProgress));
        session.set_status(SessionStatus::InProgress);
        assert_eq!(session.status, SessionStatus::InProgress);

        // InProgress -> Completed: 允许
        assert!(session.can_transition_to(SessionStatus::Completed));
        session.set_status(SessionStatus::Completed);
        assert_eq!(session.status, SessionStatus::Completed);

        // Completed -> InProgress: 允许（重新打开）
        assert!(session.can_transition_to(SessionStatus::InProgress));
    }

    #[tokio::test]
    async fn test_session_manager() {
        let manager = SessionManager::new();

        // 创建会话
        let session = manager
            .create_session("claude-code", "/home/user", PermissionMode::Ask)
            .await;
        assert_eq!(manager.count().await, 1);

        // 获取会话
        let retrieved = manager.get_session(&session.id).await;
        assert!(retrieved.is_some());
        assert_eq!(retrieved.unwrap().agent_id, "claude-code");

        // 更新状态
        manager
            .set_session_status(&session.id, SessionStatus::InProgress)
            .await;
        let updated = manager.get_session(&session.id).await.unwrap();
        assert_eq!(updated.status, SessionStatus::InProgress);

        // 删除会话
        manager.delete_session(&session.id).await;
        assert_eq!(manager.count().await, 0);
    }
}
