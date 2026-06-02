//! Codex CLI 适配器
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
//! - CodexAdapter: Codex CLI 适配器实现
//!
//! [POS]
//! Codex CLI 适配器。实现与 OpenAI Codex CLI 的交互，
//! 解析 Codex 事件格式，转换为统一的 AgentMessage 类型。

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

/// Codex 会话
struct CodexSession {
    /// CLI 进程
    child: Child,
    /// 会话配置
    config: SessionConfig,
    /// 中止信号发送器
    #[allow(dead_code)]
    abort_tx: Option<mpsc::Sender<()>>,
}

/// Codex CLI 适配器
pub struct CodexAdapter {
    /// 活跃会话
    sessions: Arc<Mutex<HashMap<String, CodexSession>>>,
}

impl CodexAdapter {
    /// 创建新的适配器
    pub fn new() -> Self {
        Self {
            sessions: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    /// 解析 Codex 输出行
    /// 
    /// Codex 事件类型：
    /// - agent_message / agent_message_delta: 助手消息
    /// - agent_reasoning / agent_reasoning_delta: 思考过程
    /// - exec_command_begin / exec_command_end: 命令执行
    /// - apply_patch_approval_request: 补丁审批请求
    /// - patch_apply_begin / patch_apply_end: 补丁应用
    /// - task_started / task_complete: 任务状态
    fn parse_output_line(line: &str) -> Option<AgentMessage> {
        if line.starts_with('{') {
            if let Ok(value) = serde_json::from_str::<serde_json::Value>(line) {
                return Self::convert_json_to_message(&value);
            }
        }
        None
    }

    /// 将 Codex JSON 事件转换为 AgentMessage
    fn convert_json_to_message(value: &serde_json::Value) -> Option<AgentMessage> {
        let event_type = value.get("type")?.as_str()?;

        match event_type {
            // 文本消息（流式增量或完整）
            "agent_message_delta" | "agent_message" => {
                let content = if event_type == "agent_message_delta" {
                    value.get("payload")?.get("delta")?.as_str()?
                } else {
                    value.get("payload")?.get("message")?.as_str()?
                };
                Some(AgentMessage::Text {
                    content: content.to_string(),
                    msg_id: uuid::Uuid::new_v4().to_string(),
                })
            }
            // 思考过程
            "agent_reasoning_delta" | "agent_reasoning" => {
                let content = if event_type == "agent_reasoning_delta" {
                    value.get("payload")?.get("delta")?.as_str()?
                } else {
                    value.get("payload")?.get("text")?.as_str()?
                };
                Some(AgentMessage::Thought {
                    content: content.to_string(),
                })
            }
            // 命令执行开始
            "exec_command_begin" => {
                let call_id = value.get("payload")?.get("call_id")?.as_str()?;
                let command = value.get("payload")?.get("command")?.as_str()?;
                Some(AgentMessage::ToolCallStart {
                    call_id: call_id.to_string(),
                    tool_name: "exec_command".to_string(),
                    arguments: serde_json::json!({ "command": command }),
                })
            }
            // 命令执行结束
            "exec_command_end" => {
                let call_id = value.get("payload")?.get("call_id")?.as_str()?;
                let exit_code = value.get("payload")?.get("exit_code").and_then(|v| v.as_i64()).unwrap_or(0);
                let output = value.get("payload")?.get("output").and_then(|v| v.as_str()).unwrap_or("");
                Some(AgentMessage::ToolCallResult {
                    call_id: call_id.to_string(),
                    content: output.to_string(),
                    status: if exit_code == 0 {
                        ToolCallStatus::Completed
                    } else {
                        ToolCallStatus::Failed
                    },
                })
            }
            // 补丁审批请求
            "apply_patch_approval_request" => {
                let call_id = value.get("payload")?.get("call_id")?.as_str()?;
                let file_path = value.get("payload")?.get("file_path")?.as_str()?;
                Some(AgentMessage::PermissionRequest {
                    request_id: call_id.to_string(),
                    tool_name: "apply_patch".to_string(),
                    command: format!("Edit file: {}", file_path),
                    is_dangerous: false,
                })
            }
            // 补丁应用开始
            "patch_apply_begin" => {
                let call_id = value.get("payload")?.get("call_id")?.as_str()?;
                let file_path = value.get("payload")?.get("file_path")?.as_str()?;
                Some(AgentMessage::ToolCallStart {
                    call_id: call_id.to_string(),
                    tool_name: "apply_patch".to_string(),
                    arguments: serde_json::json!({ "file_path": file_path }),
                })
            }
            // 补丁应用结束
            "patch_apply_end" => {
                let call_id = value.get("payload")?.get("call_id")?.as_str()?;
                let success = value.get("payload")?.get("success").and_then(|v| v.as_bool()).unwrap_or(true);
                Some(AgentMessage::ToolCallResult {
                    call_id: call_id.to_string(),
                    content: if success { "Patch applied successfully" } else { "Patch failed" }.to_string(),
                    status: if success {
                        ToolCallStatus::Completed
                    } else {
                        ToolCallStatus::Failed
                    },
                })
            }
            // 任务开始
            "task_started" => {
                Some(AgentMessage::SessionStatus {
                    status: SessionStatus::InProgress,
                })
            }
            // 任务完成
            "task_complete" => {
                Some(AgentMessage::SessionStatus {
                    status: SessionStatus::Completed,
                })
            }
            // 错误
            "error" => {
                let message = value.get("payload")?.get("message")?.as_str()?;
                Some(AgentMessage::Error {
                    message: message.to_string(),
                })
            }
            _ => None,
        }
    }
}

impl Default for CodexAdapter {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl CLIAgentAdapter for CodexAdapter {
    fn name(&self) -> &'static str {
        "Codex"
    }

    fn id(&self) -> &'static str {
        "codex"
    }

    async fn detect(&self) -> bool {
        Command::new("codex")
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .await
            .map(|s| s.success())
            .unwrap_or(false)
    }

    async fn version(&self) -> Option<String> {
        let output = Command::new("codex")
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

        // 构建 Codex 命令
        let mut cmd = Command::new("codex");
        cmd.current_dir(&config.cwd)
            .arg("--json")
            .arg("--stream")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        let child = cmd
            .spawn()
            .map_err(|e| AgentError::StartFailed(format!("Failed to spawn codex: {}", e)))?;

        // 创建中止通道
        let (abort_tx, _abort_rx) = mpsc::channel::<()>(1);

        // 保存会话
        let session = CodexSession {
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

        // 发送权限响应到 stdin（JSON 格式）
        if let Some(stdin) = session.child.stdin.as_mut() {
            use tokio::io::AsyncWriteExt;
            let response = serde_json::json!({
                "type": "permission_response",
                "request_id": request_id,
                "approved": allowed,
            });
            stdin
                .write_all(format!("{}\n", response).as_bytes())
                .await
                .map_err(|e| AgentError::SendFailed(e.to_string()))?;
            stdin
                .flush()
                .await
                .map_err(|e| AgentError::SendFailed(e.to_string()))?;
        }

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
        // 注意：这里不能使用 async，所以无法获取锁
        // 返回空列表，实际使用时应该通过其他方式获取
        Vec::new()
    }
}
