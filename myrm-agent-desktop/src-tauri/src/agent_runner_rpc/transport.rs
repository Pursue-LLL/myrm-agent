//! Agent Runner stdout JSON-RPC 读取与事件转发。
//!
//! [INPUT]
//! - types::RPCResponse / RPCNotification (POS: JSON-RPC 协议帧)
//! - tokio mpsc pending 请求表 (POS: SidecarManager 请求/响应配对)
//!
//! [OUTPUT]
//! - read_stdout: 阻塞读取 sidecar stdout 行并 dispatch
//! - forward_agent_event: agent.event 通知 → SidecarEvent broadcast
//!
//! [POS]
//! agent_runner_rpc IO 传输层；SidecarManager 生命周期见 `mod.rs`。

use std::collections::HashMap;
use std::io::{BufRead, BufReader};
use std::process::ChildStdout;
use std::sync::{Arc, RwLock as StdRwLock};

use tokio::sync::{broadcast, mpsc, Mutex};

use super::types::{RPCNotification, RPCResponse, SidecarEvent};

/// 读取 stdout 并处理 JSON-RPC 响应与通知。
pub fn read_stdout(
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

        if let Ok(notification) = serde_json::from_str::<RPCNotification>(&line) {
            match notification.method.as_str() {
                "ready" => {
                    if let Ok(mut ready_guard) = ready.write() {
                        *ready_guard = true;
                        println!("📡 Sidecar ready notification received");
                    }
                }
                "agent.event" => {
                    if let Some(params) = notification.params {
                        forward_agent_event(&event_sender, params);
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
        _ => SidecarEvent::AgentMessage {
            session_id,
            message: params,
        },
    };

    let _ = event_sender.send(event);
}
