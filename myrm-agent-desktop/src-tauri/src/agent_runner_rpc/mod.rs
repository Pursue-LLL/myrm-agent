//! Agent Runner JSON-RPC 进程管理
//!
//! [INPUT]
//! - runtime::TOXIC_ENV_VARS / suppress_console_window (POS: 子进程环境清洗)
//! - transport::read_stdout (POS: stdout JSON-RPC 读取)
//! - types::SidecarEvent / RPCRequest (POS: 协议类型)
//!
//! [OUTPUT]
//! - SidecarManager: JSON-RPC stdio 请求/通知、事件 broadcast
//! - SidecarEvent: Agent 消息/权限/会话状态事件
//!
//! [POS]
//! 管理 agent-runner 子进程（独立二进制或 dev 下 bun/ts 入口），通过 JSON-RPC stdio 通信。

mod transport;
mod types;

use std::collections::HashMap;
use std::io::Write;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, RwLock as StdRwLock};

use tokio::sync::{broadcast, mpsc, Mutex};

pub use types::SidecarEvent;
use types::RPCRequest;

/// Agent Runner JSON-RPC 进程管理器
pub struct SidecarManager {
    process: Option<Child>,
    stdin: Option<ChildStdin>,
    request_id: AtomicU64,
    pending_requests: Arc<Mutex<HashMap<u64, mpsc::Sender<Result<serde_json::Value, String>>>>>,
    ready: Arc<StdRwLock<bool>>,
    event_sender: broadcast::Sender<SidecarEvent>,
}

impl SidecarManager {
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

    pub fn subscribe_events(&self) -> broadcast::Receiver<SidecarEvent> {
        self.event_sender.subscribe()
    }

    pub async fn start(&mut self, sidecar_path: &str) -> Result<(), String> {
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

        for var in crate::runtime::TOXIC_ENV_VARS {
            cmd.env_remove(var);
        }

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

        let pending_requests = self.pending_requests.clone();
        let ready = self.ready.clone();
        let event_sender = self.event_sender.clone();

        std::thread::spawn(move || {
            transport::read_stdout(stdout, pending_requests, ready, event_sender);
        });

        for _ in 0..50 {
            tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
            if *self.ready.read().unwrap_or_else(|e| e.into_inner()) {
                println!("✅ Sidecar is ready");
                return Ok(());
            }
        }

        Err("Sidecar startup timeout".to_string())
    }

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

        let (tx, mut rx) = mpsc::channel(1);
        {
            let mut pending = self.pending_requests.lock().await;
            pending.insert(id, tx);
        }

        writeln!(stdin, "{}", request_json).map_err(|e| format!("Write error: {}", e))?;
        stdin.flush().map_err(|e| format!("Flush error: {}", e))?;

        tokio::select! {
            result = rx.recv() => {
                let mut pending = self.pending_requests.lock().await;
                pending.remove(&id);
                result.ok_or_else(|| "Channel closed".to_string())?
            }
            _ = tokio::time::sleep(tokio::time::Duration::from_secs(10)) => {
                let mut pending = self.pending_requests.lock().await;
                pending.remove(&id);
                Err("Request timeout".to_string())
            }
        }
    }

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
