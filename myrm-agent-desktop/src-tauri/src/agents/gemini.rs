//! Gemini CLI 适配器
//!
//! ⚠️ 自更新提示：一旦我被更新，务必更新：
//! 1. 本文件的 INPUT/OUTPUT/POS 注释
//! 2. 所属文件夹的 _ARCH.md
//!
//! [INPUT]
//! - super::CLIAgentAdapter trait
//! - super::AgentMessage, SessionConfig, SessionStatus
//! - tokio: 异步运行时
//!
//! [OUTPUT]
//! - GeminiAdapter: Gemini CLI 适配器实现
//!
//! [POS]
//! Gemini CLI 适配器。实现与 Google Gemini CLI 的交互，
//! 解析 Gemini 事件格式，转换为统一的 AgentMessage 类型。

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

/// Gemini 会话
struct GeminiSession {
    /// CLI 进程
    child: Child,
    /// 会话配置
    #[allow(dead_code)]
    config: SessionConfig,
    /// 中止信号发送器
    #[allow(dead_code)]
    abort_tx: Option<mpsc::Sender<()>>,
}

/// Gemini CLI 适配器
pub struct GeminiAdapter {
    /// 活跃会话
    sessions: Arc<Mutex<HashMap<String, GeminiSession>>>,
}

impl GeminiAdapter {
    /// 创建新的适配器
    pub fn new() -> Self {
        Self {
            sessions: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    /// 解析 Gemini 输出行
    /// 
    /// Gemini 事件类型：
    /// - content: 文本内容
    /// - tool_call: 工具调用
    /// - tool_call_request: 工具调用请求（需要确认）
    /// - error: 错误
    fn parse_output_line(line: &str) -> Option<AgentMessage> {
        if line.starts_with('{') {
            if let Ok(value) = serde_json::from_str::<serde_json::Value>(line) {
                return Self::convert_json_to_message(&value);
            }
        }
        None
    }

    /// 将 Gemini JSON 事件转换为 AgentMessage
    fn convert_json_to_message(value: &serde_json::Value) -> Option<AgentMessage> {
        let event_type = value.get("type")?.as_str()?;

        match event_type {
            // 文本内容
            "content" | "gemini" | "gemini_content" => {
                let text = value.get("text")?.as_str()?;
                Some(AgentMessage::Text {
                    content: text.to_string(),
                    msg_id: uuid::Uuid::new_v4().to_string(),
                })
            }
            // 用户消息（回显）
            "user" => {
                // 用户消息不需要转发
                None
            }
            // 工具调用
            "tool_call" => {
                let status = value.get("status")?.as_str()?;
                let call_id = value.get("callId")?.as_str()?;
                let name = value.get("name")?.as_str()?;

                match status {
                    "Pending" | "Executing" => {
                        let args = value.get("args").cloned().unwrap_or(serde_json::json!({}));
                        Some(AgentMessage::ToolCallStart {
                            call_id: call_id.to_string(),
                            tool_name: name.to_string(),
                            arguments: args,
                        })
                    }
                    "Confirming" => {
                        // 需要用户确认
                        let description = value.get("confirmationDetails")
                            .and_then(|d| d.get("description"))
                            .and_then(|s| s.as_str())
                            .unwrap_or(name);
                        Some(AgentMessage::PermissionRequest {
                            request_id: call_id.to_string(),
                            tool_name: name.to_string(),
                            command: description.to_string(),
                            is_dangerous: false,
                        })
                    }
                    "Success" => {
                        let result = value.get("resultDisplay")
                            .and_then(|r| r.get("output"))
                            .and_then(|s| s.as_str())
                            .unwrap_or("");
                        Some(AgentMessage::ToolCallResult {
                            call_id: call_id.to_string(),
                            content: result.to_string(),
                            status: ToolCallStatus::Completed,
                        })
                    }
                    "Error" | "Canceled" => {
                        let result = value.get("resultDisplay")
                            .and_then(|r| r.get("output"))
                            .and_then(|s| s.as_str())
                            .unwrap_or("Tool call failed");
                        Some(AgentMessage::ToolCallResult {
                            call_id: call_id.to_string(),
                            content: result.to_string(),
                            status: ToolCallStatus::Failed,
                        })
                    }
                    _ => None,
                }
            }
            // 工具调用请求
            "tool_call_request" => {
                let call_id = value.get("callId")?.as_str()?;
                let name = value.get("name")?.as_str()?;
                Some(AgentMessage::PermissionRequest {
                    request_id: call_id.to_string(),
                    tool_name: name.to_string(),
                    command: format!("Execute: {}", name),
                    is_dangerous: false,
                })
            }
            // 信息
            "info" => {
                let text = value.get("text")?.as_str()?;
                Some(AgentMessage::Text {
                    content: format!("[info] {}", text),
                    msg_id: uuid::Uuid::new_v4().to_string(),
                })
            }
            // 错误
            "error" => {
                let text = value.get("text")?.as_str()?;
                Some(AgentMessage::Error {
                    message: text.to_string(),
                })
            }
            // 会话状态
            "session_start" | "task_start" => {
                Some(AgentMessage::SessionStatus {
                    status: SessionStatus::InProgress,
                })
            }
            "session_end" | "task_complete" => {
                Some(AgentMessage::SessionStatus {
                    status: SessionStatus::Completed,
                })
            }
            _ => None,
        }
    }
}

impl Default for GeminiAdapter {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl CLIAgentAdapter for GeminiAdapter {
    fn name(&self) -> &'static str {
        "Gemini"
    }

    fn id(&self) -> &'static str {
        "gemini"
    }

    async fn detect(&self) -> bool {
        Command::new("gemini")
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .await
            .map(|s| s.success())
            .unwrap_or(false)
    }

    async fn version(&self) -> Option<String> {
        let output = Command::new("gemini")
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

        // 构建 Gemini 命令
        let mut cmd = Command::new("gemini");
        cmd.current_dir(&config.cwd)
            .arg("--json")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        let child = cmd
            .spawn()
            .map_err(|e| AgentError::StartFailed(format!("Failed to spawn gemini: {}", e)))?;

        // 创建中止通道
        let (abort_tx, _abort_rx) = mpsc::channel::<()>(1);

        // 保存会话
        let session = GeminiSession {
            child,
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
        request_id: &str,
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
            // Gemini 使用简单的 y/n 响应
            let response = if allowed { "y" } else { "n" };
            stdin
                .write_all(format!("{}\n", response).as_bytes())
                .await
                .map_err(|e| AgentError::SendFailed(e.to_string()))?;
            stdin
                .flush()
                .await
                .map_err(|e| AgentError::SendFailed(e.to_string()))?;
        }

        // 发送确认消息
        let _ = request_id; // 使用 request_id 避免警告

        Ok(())
    }

    async fn stop_session(&self, session_id: &str) -> Result<(), AgentError> {
        let mut sessions = self.sessions.lock().await;
        if let Some(mut session) = sessions.remove(session_id) {
            // 杀死进程
            let _ = session.child.kill().await;
        }
        Ok(())
    }

    fn active_sessions(&self) -> Vec<String> {
        Vec::new()
    }
}
