//! Claude Code CLI 适配器
//!
//! 实现与 Claude Code CLI 的交互。
//! 借鉴 Claude-Cowork 的简洁设计。

use async_trait::async_trait;
use std::collections::HashMap;
use std::process::Stdio;
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::{Child, Command};
use tokio::sync::{mpsc, Mutex};

use super::{
    AgentError, AgentMessage, CLIAgentAdapter, SessionConfig, SessionStatus, ToolCallStatus,
};

/// Claude Code 会话
struct ClaudeSession {
    /// CLI 进程
    child: Child,
    /// SDK 内部会话 ID（用于恢复）
    sdk_session_id: Option<String>,
    /// 会话配置
    config: SessionConfig,
    /// 中止信号发送器
    abort_tx: Option<mpsc::Sender<()>>,
}

/// Claude Code CLI 适配器
pub struct ClaudeCodeAdapter {
    /// 活跃会话
    sessions: Arc<Mutex<HashMap<String, ClaudeSession>>>,
}

impl ClaudeCodeAdapter {
    /// 创建新的适配器
    pub fn new() -> Self {
        Self {
            sessions: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    /// 解析 Claude Code 输出行
    fn parse_output_line(line: &str) -> Option<AgentMessage> {
        // Claude Code CLI 输出 JSON-RPC 格式
        // 这里需要根据实际 CLI 输出格式解析
        if line.starts_with('{') {
            if let Ok(value) = serde_json::from_str::<serde_json::Value>(line) {
                return Self::convert_json_to_message(&value);
            }
        }
        None
    }

    /// 将 JSON 转换为 AgentMessage
    fn convert_json_to_message(value: &serde_json::Value) -> Option<AgentMessage> {
        let msg_type = value.get("type")?.as_str()?;

        match msg_type {
            "assistant" => {
                let content = value.get("message")?.get("content")?.as_str()?;
                Some(AgentMessage::Text {
                    content: content.to_string(),
                    msg_id: uuid::Uuid::new_v4().to_string(),
                })
            }
            "tool_use" => {
                let call_id = value.get("id")?.as_str()?;
                let tool_name = value.get("name")?.as_str()?;
                let arguments = value.get("input").cloned().unwrap_or(serde_json::json!({}));
                Some(AgentMessage::ToolCallStart {
                    call_id: call_id.to_string(),
                    tool_name: tool_name.to_string(),
                    arguments,
                })
            }
            "tool_result" => {
                let call_id = value.get("tool_use_id")?.as_str()?;
                let content = value.get("content")?.as_str().unwrap_or("");
                let is_error = value.get("is_error").and_then(|v| v.as_bool()).unwrap_or(false);
                Some(AgentMessage::ToolCallResult {
                    call_id: call_id.to_string(),
                    content: content.to_string(),
                    status: if is_error {
                        ToolCallStatus::Failed
                    } else {
                        ToolCallStatus::Completed
                    },
                })
            }
            "result" => {
                let subtype = value.get("subtype")?.as_str()?;
                let status = match subtype {
                    "success" => SessionStatus::Completed,
                    "error" => SessionStatus::Error,
                    _ => SessionStatus::Completed,
                };
                Some(AgentMessage::SessionStatus { status })
            }
            _ => None,
        }
    }
}

impl Default for ClaudeCodeAdapter {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl CLIAgentAdapter for ClaudeCodeAdapter {
    fn name(&self) -> &'static str {
        "Claude Code"
    }

    fn id(&self) -> &'static str {
        "claude-code"
    }

    async fn detect(&self) -> bool {
        Command::new("claude")
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .await
            .map(|s| s.success())
            .unwrap_or(false)
    }

    async fn version(&self) -> Option<String> {
        let output = Command::new("claude")
            .arg("--version")
            .output()
            .await
            .ok()?;

        if output.status.success() {
            String::from_utf8(output.stdout)
                .ok()
                .map(|s| s.trim().to_string())
        } else {
            None
        }
    }

    async fn start_session(&self, config: SessionConfig) -> Result<String, AgentError> {
        let session_id = uuid::Uuid::new_v4().to_string();

        // 构建 Claude Code 命令
        let mut cmd = Command::new("claude");
        cmd.current_dir(&config.cwd)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        // 如果是恢复会话
        if let Some(ref resume_id) = config.resume_session_id {
            cmd.arg("--resume").arg(resume_id);
        }

        let child = cmd
            .spawn()
            .map_err(|e| AgentError::StartFailed(format!("Failed to spawn claude: {}", e)))?;

        // 创建中止通道
        let (abort_tx, _abort_rx) = mpsc::channel::<()>(1);

        // 保存会话
        let session = ClaudeSession {
            child,
            sdk_session_id: config.resume_session_id.clone(),
            config,
            abort_tx: Some(abort_tx),
        };

        self.sessions.lock().await.insert(session_id.clone(), session);

        Ok(session_id)
    }

    async fn send_message(
        &self,
        session_id: &str,
        prompt: &str,
        tx: mpsc::Sender<AgentMessage>,
    ) -> Result<(), AgentError> {
        let mut sessions = self.sessions.lock().await;
        let session = sessions
            .get_mut(session_id)
            .ok_or_else(|| AgentError::SessionNotFound(session_id.to_string()))?;

        // 发送消息到 stdin
        if let Some(stdin) = session.child.stdin.as_mut() {
            use tokio::io::AsyncWriteExt;
            stdin
                .write_all(prompt.as_bytes())
                .await
                .map_err(|e| AgentError::SendFailed(e.to_string()))?;
            stdin
                .write_all(b"\n")
                .await
                .map_err(|e| AgentError::SendFailed(e.to_string()))?;
            stdin
                .flush()
                .await
                .map_err(|e| AgentError::SendFailed(e.to_string()))?;
        }

        // 读取 stdout 并转发消息
        if let Some(stdout) = session.child.stdout.take() {
            let reader = BufReader::new(stdout);
            let mut lines = reader.lines();

            tokio::spawn(async move {
                while let Ok(Some(line)) = lines.next_line().await {
                    if let Some(msg) = Self::parse_output_line(&line) {
                        if tx.send(msg).await.is_err() {
                            break;
                        }
                    }
                }
                let _ = tx.send(AgentMessage::Done).await;
            });
        }

        Ok(())
    }

    async fn respond_permission(
        &self,
        session_id: &str,
        _request_id: &str,
        allowed: bool,
        _always_allow: bool,
    ) -> Result<(), AgentError> {
        let mut sessions = self.sessions.lock().await;
        let session = sessions
            .get_mut(session_id)
            .ok_or_else(|| AgentError::SessionNotFound(session_id.to_string()))?;

        // 发送权限响应到 stdin
        if let Some(stdin) = session.child.stdin.as_mut() {
            use tokio::io::AsyncWriteExt;
            let response = if allowed { "yes" } else { "no" };
            stdin
                .write_all(response.as_bytes())
                .await
                .map_err(|e| AgentError::SendFailed(e.to_string()))?;
            stdin
                .write_all(b"\n")
                .await
                .map_err(|e| AgentError::SendFailed(e.to_string()))?;
        }

        Ok(())
    }

    async fn stop_session(&self, session_id: &str) -> Result<(), AgentError> {
        let mut sessions = self.sessions.lock().await;

        if let Some(mut session) = sessions.remove(session_id) {
            // 发送中止信号
            if let Some(abort_tx) = session.abort_tx.take() {
                let _ = abort_tx.send(()).await;
            }

            // 终止进程
            session
                .child
                .kill()
                .await
                .map_err(|e| AgentError::ProcessError(format!("Failed to kill process: {}", e)))?;
        }

        Ok(())
    }

    fn active_sessions(&self) -> Vec<String> {
        // 这个方法需要同步访问，暂时返回空
        // 实际使用中可以用 try_lock 或其他机制
        Vec::new()
    }
}
