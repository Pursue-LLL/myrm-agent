//! Agent Runner Sidecar 管理模块
//!
//! 管理 agent-runner sidecar 进程（独立二进制），通过 JSON-RPC stdio 通信。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, RwLock as StdRwLock};
use tokio::sync::{broadcast, mpsc, Mutex};

// ============================================================================
// JSON-RPC 类型
// ============================================================================

#[derive(Debug, Serialize)]
struct RPCRequest {
    jsonrpc: &'static str,
    id: u64,
    method: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    params: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
struct RPCResponse {
    jsonrpc: String,
    id: u64,
    result: Option<serde_json::Value>,
    error: Option<RPCError>,
}

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
struct RPCError {
    code: i32,
    message: String,
}

#[derive(Debug, Deserialize)]
#[allow(dead_code)]
struct RPCNotification {
    jsonrpc: String,
    method: String,
    params: Option<serde_json::Value>,
}

// ============================================================================
// Agent 事件（从 Sidecar 转发）
// ============================================================================

/// Agent 事件类型
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
    Error {
        message: String,
    },
}

// ============================================================================
// Sidecar 管理器
// ============================================================================

/// Sidecar 管理器
pub struct SidecarManager {
    /// 子进程
    process: Option<Child>,
    /// stdin 写入器
    stdin: Option<ChildStdin>,
    /// 请求 ID 计数器
    request_id: AtomicU64,
    /// 待处理的请求
    pending_requests: Arc<Mutex<HashMap<u64, mpsc::Sender<Result<serde_json::Value, String>>>>>,
    /// 是否就绪（使用标准库 RwLock 以便在非 Tokio 线程中使用）
    ready: Arc<StdRwLock<bool>>,
    /// 事件广播通道
    event_sender: broadcast::Sender<SidecarEvent>,
}

impl SidecarManager {
    /// 创建新的 Sidecar 管理器
    pub fn new() -> Self {
        let (event_sender, _) = broadcast::channel(100);
        Self {
            process: None,
            stdin: None,
            request_id: AtomicU64::new(1),
            pending_requests: Arc::new(Mutex::new(HashMap::new())),
            ready: Arc::new(StdRwLock::new(false)),
            event_sender,
        }
    }

    /// 获取事件接收器
    pub fn subscribe_events(&self) -> broadcast::Receiver<SidecarEvent> {
        self.event_sender.subscribe()
    }

    /// 启动 Sidecar 进程
    pub async fn start(&mut self, sidecar_path: &str) -> Result<(), String> {
        // 检查是否已经在运行
        if self.process.is_some() {
            return Ok(());
        }

        println!("🚀 Starting agent-runner sidecar: {}", sidecar_path);

        let mut cmd = if sidecar_path.ends_with(".js") || sidecar_path.ends_with(".ts") {
            let runner = {
                let mut probe = Command::new("bun");
                probe.arg("--version");
                crate::runtime::suppress_console_window(&mut probe);
                if probe.output().is_ok() { "bun" } else { "node" }
            };
            let mut c = Command::new(runner);
            c.arg(sidecar_path);
            c
        } else {
            Command::new(sidecar_path)
        };

        crate::runtime::suppress_console_window(&mut cmd);
        let mut child = cmd
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|e| format!("Failed to start sidecar: {}", e))?;

        let stdin = child.stdin.take().ok_or("Failed to get stdin")?;
        let stdout = child.stdout.take().ok_or("Failed to get stdout")?;

        self.process = Some(child);
        self.stdin = Some(stdin);

        // 启动 stdout 读取线程
        let pending_requests = self.pending_requests.clone();
        let ready = self.ready.clone();
        let event_sender = self.event_sender.clone();

        std::thread::spawn(move || {
            Self::read_stdout(stdout, pending_requests, ready, event_sender);
        });

        // 等待就绪
        for _ in 0..50 {
            tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
            if *self.ready.read().unwrap_or_else(|e| e.into_inner()) {
                println!("✅ Sidecar is ready");
                return Ok(());
            }
        }

        Err("Sidecar startup timeout".to_string())
    }

    /// 读取 stdout 并处理响应
    fn read_stdout(
        stdout: ChildStdout,
        pending_requests: Arc<Mutex<HashMap<u64, mpsc::Sender<Result<serde_json::Value, String>>>>>,
        ready: Arc<StdRwLock<bool>>,
        event_sender: broadcast::Sender<SidecarEvent>,
    ) {
        let reader = BufReader::new(stdout);

        for line in reader.lines() {
            let line = match line {
                Ok(l) => l,
                Err(e) => {
                    eprintln!("Sidecar read error: {}", e);
                    break;
                }
            };

            if line.is_empty() {
                continue;
            }

            // 尝试解析为响应
            if let Ok(response) = serde_json::from_str::<RPCResponse>(&line) {
                let pending = pending_requests.blocking_lock();
                if let Some(tx) = pending.get(&response.id) {
                    let result = if let Some(error) = response.error {
                        Err(error.message)
                    } else {
                        Ok(response.result.unwrap_or(serde_json::Value::Null))
                    };
                    let _ = tx.blocking_send(result);
                }
                continue;
            }

            // 尝试解析为通知
            if let Ok(notification) = serde_json::from_str::<RPCNotification>(&line) {
                match notification.method.as_str() {
                    "ready" => {
                        if let Ok(mut ready_guard) = ready.write() {
                            *ready_guard = true;
                            println!("📡 Sidecar ready notification received");
                        }
                    }
                    "agent.event" => {
                        // 转发 Agent 事件
                        if let Some(params) = notification.params {
                            Self::forward_agent_event(&event_sender, params);
                        }
                    }
                    "error" => {
                        if let Some(params) = notification.params {
                            let message = params
                                .get("message")
                                .and_then(|v| v.as_str())
                                .unwrap_or("Unknown error")
                                .to_string();
                            let _ = event_sender.send(SidecarEvent::Error { message });
                        }
                    }
                    _ => {}
                }
            }
        }
    }

    /// 转发 Agent 事件
    fn forward_agent_event(event_sender: &broadcast::Sender<SidecarEvent>, params: serde_json::Value) {
        let event_type = params.get("type").and_then(|v| v.as_str()).unwrap_or("");
        let session_id = params
            .get("sessionId")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        let event = match event_type {
            "stream.message" => {
                if let Some(message) = params.get("message") {
                    SidecarEvent::AgentMessage {
                        session_id,
                        message: message.clone(),
                    }
                } else {
                    return;
                }
            }
            "permission.request" => SidecarEvent::PermissionRequest {
                session_id,
                request_id: params
                    .get("requestId")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string(),
                tool_name: params
                    .get("toolName")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string(),
                command: params
                    .get("command")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string(),
                is_dangerous: params
                    .get("isDangerous")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false),
            },
            "session.status" => SidecarEvent::SessionStatus {
                session_id,
                status: params
                    .get("status")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string(),
                error: params
                    .get("error")
                    .and_then(|v| v.as_str())
                    .map(String::from),
            },
            _ => {
                // 未知事件类型，作为通用消息处理
                SidecarEvent::AgentMessage {
                    session_id,
                    message: params,
                }
            }
        };

        let _ = event_sender.send(event);
    }

    /// 发送 RPC 请求
    pub async fn call(
        &mut self,
        method: &str,
        params: Option<serde_json::Value>,
    ) -> Result<serde_json::Value, String> {
        let stdin = self.stdin.as_mut().ok_or("Sidecar not running")?;

        let id = self.request_id.fetch_add(1, Ordering::SeqCst);

        let request = RPCRequest {
            jsonrpc: "2.0",
            id,
            method: method.to_string(),
            params,
        };

        let request_json =
            serde_json::to_string(&request).map_err(|e| format!("Serialize error: {}", e))?;

        // 创建响应通道
        let (tx, mut rx) = mpsc::channel(1);
        {
            let mut pending = self.pending_requests.lock().await;
            pending.insert(id, tx);
        }

        // 发送请求
        writeln!(stdin, "{}", request_json).map_err(|e| format!("Write error: {}", e))?;
        stdin.flush().map_err(|e| format!("Flush error: {}", e))?;

        // 等待响应（10 秒超时）
        tokio::select! {
            result = rx.recv() => {
                // 清理 pending
                let mut pending = self.pending_requests.lock().await;
                pending.remove(&id);

                result.ok_or_else(|| "Channel closed".to_string())?
            }
            _ = tokio::time::sleep(tokio::time::Duration::from_secs(10)) => {
                // 清理 pending
                let mut pending = self.pending_requests.lock().await;
                pending.remove(&id);

                Err("Request timeout".to_string())
            }
        }
    }

    /// 停止 Sidecar
    pub fn stop(&mut self) -> Result<(), String> {
        if let Some(mut process) = self.process.take() {
            process
                .kill()
                .map_err(|e| format!("Failed to kill sidecar: {}", e))?;
            println!("🛑 Sidecar stopped");
        }
        self.stdin = None;
        Ok(())
    }

    /// 检查是否正在运行
    pub fn is_running(&self) -> bool {
        self.process.is_some()
    }
}

impl Default for SidecarManager {
    fn default() -> Self {
        Self::new()
    }
}

impl Drop for SidecarManager {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}
