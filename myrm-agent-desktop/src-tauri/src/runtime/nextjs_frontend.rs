//! Next.js Standalone 前端进程管理（Tauri 桌面始终自启）
//!
//! [INPUT]
//! - config::FrontendConfig (POS: webui_port 与 standalone 资源路径)
//! - runtime::port::is_port_in_use (POS: 启动前端端口冲突检测)
//! - runtime::TOXIC_ENV_VARS (POS: 子进程环境清洗)
//!
//! [OUTPUT]
//! - NextJSFrontend: start/stop Standalone Server 子进程
//!
//! [POS]
//! Tauri 启动时 Next.js Standalone 进程生命周期管理（始终自启，与 enable_webui_mode 无关）。

use std::process::{Child, Command};
use std::sync::{Arc, Mutex};

use tauri::{AppHandle, Manager, State};

use crate::config::FrontendConfig;
use crate::runtime::port::is_port_in_use;
use crate::runtime::survivor_diag::{diagnose_and_reclaim_port, SurvivorDiagResult};
use crate::runtime::TOXIC_ENV_VARS;
use crate::utils::process_tree::kill_process_tree;

pub struct NextJSFrontend {
    pub process: Arc<Mutex<Option<Child>>>,
}

impl NextJSFrontend {
    pub fn new() -> Self {
        Self {
            process: Arc::new(Mutex::new(None)),
        }
    }
}

pub async fn start_frontend(
    app: AppHandle,
    frontend: State<'_, NextJSFrontend>,
    config: FrontendConfig,
) -> Result<String, String> {
    println!("🚀 Starting Next.js frontend with config: {:?}", config);

    {
        let process_guard = frontend.process.lock().unwrap();
        if process_guard.is_some() {
            return Ok("Frontend is already running".to_string());
        }
    }

    if is_port_in_use(&config.host, config.port) {
        println!(
            "⚠️  Port {}:{} in use, diagnosing potential survivor processes...",
            config.host, config.port
        );
        match diagnose_and_reclaim_port(&config.host, config.port).await {
            SurvivorDiagResult::SelfSurvivorReclaimed { pid, process_name } => {
                println!(
                    "✅ Self survivor {} (PID: {}) reclaimed, proceeding with frontend startup",
                    process_name, pid
                );
            }
            SurvivorDiagResult::ForeignConflict { pid, process_name } => {
                return Err(format!(
                    "Port {}:{} is in use by foreign process {} (PID: {}). Please close it or change port in settings.",
                    config.host, config.port, process_name, pid
                ));
            }
            SurvivorDiagResult::UnknownConflict | SurvivorDiagResult::Clean => {
                if is_port_in_use(&config.host, config.port) {
                    return Err(format!(
                        "Port {}:{} is already in use. Please close the conflicting process or change the port in settings.",
                        config.host, config.port
                    ));
                }
            }
        }
    }

    let is_dev = cfg!(debug_assertions);

    let nextjs_dir = if is_dev {
        let tauri_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| ".".to_string());
        let project_root = std::path::Path::new(&tauri_dir)
            .parent()
            .and_then(|p| p.parent())
            .ok_or("Failed to get project root")?;
        project_root.join("myrm-agent-frontend/.next/standalone/myrm-agent-frontend")
    } else {
        app.path()
            .resolve("frontend", tauri::path::BaseDirectory::Resource)
            .map_err(|e| format!("Failed to resolve frontend path: {}", e))?
    };

    if !nextjs_dir.exists() {
        return Err(format!(
            "Next.js standalone directory not found at: {:?}",
            nextjs_dir
        ));
    }

    println!("📂 Next.js dir: {:?}", nextjs_dir);

    let node_exe = if cfg!(target_os = "windows") {
        "node.exe"
    } else {
        "node"
    };

    let mut cmd = Command::new(node_exe);

    for var in TOXIC_ENV_VARS {
        cmd.env_remove(var);
    }

    cmd.arg("server.js")
        .current_dir(&nextjs_dir)
        .env("PORT", config.port.to_string())
        .env("HOSTNAME", &config.host)
        .env("API_PORT", config.api_port.to_string());

    println!("🌐 Frontend will listen on {}:{}", config.host, config.port);
    println!("🔗 API proxy to localhost:{}", config.api_port);

    super::suppress_console_window(&mut cmd);
    let mut child = cmd
        .spawn()
        .map_err(|e| format!("Failed to start frontend: {}", e))?;

    let child_pid = child.id();
    crate::runtime::child_reaper::record_child(&app, "frontend", child_pid);

    // 只有「我们自己的子进程真的在服务」才算前端就绪：端口可能在我们 spawn 的瞬间被
    // 别的进程抢走（bind 探测有竞态窗口），此时 HTTP 探测会命中别人的服务，
    // 页面就会加载出与本应用不匹配的残缺界面。
    let ready = wait_for_http_ready(&config.host, config.port, &mut child, 45).await;
    if let Err(e) = ready {
        let _ = child.kill();
        return Err(e);
    }

    if let Some(registry) = app.try_state::<crate::runtime::ProcessRegistry>() {
        registry
            .register_spawn(
                "sidecar:frontend",
                crate::runtime::ProcessRole::Frontend,
                Some(child_pid),
            )
            .await;
    }

    {
        let mut process_guard = frontend.process.lock().unwrap();
        *process_guard = Some(child);
    }

    println!("✅ Frontend process started (PID: {})", child_pid);

    Ok("Frontend started successfully".to_string())
}

pub fn stop_frontend(
    app: AppHandle,
    frontend: State<'_, NextJSFrontend>,
) -> Result<String, String> {
    println!("Stopping Next.js frontend...");

    if let Some(registry) = app.try_state::<crate::runtime::ProcessRegistry>() {
        let reg = registry.inner().clone();
        tauri::async_runtime::spawn(async move {
            reg.mark_stopped("sidecar:frontend", Some(0)).await;
        });
    }

    let mut process_guard = frontend.process.lock().unwrap();

    if let Some(mut child) = process_guard.take() {
        let pid = child.id();
        kill_process_tree(pid);
        match child.kill() {
            Ok(_) => {
                println!("Frontend process tree killed (root PID: {})", pid);
                Ok("Frontend stopped successfully".to_string())
            }
            Err(e) => Err(format!("Failed to stop frontend: {}", e)),
        }
    } else {
        Ok("Frontend is not running".to_string())
    }
}

/// 等待我们自己拉起的 Next standalone 真正开始服务 HTTP。
///
/// 返回 Err 表示：子进程已退出，或超时仍未就绪——两种情况都不能让主窗口导航过去。
async fn wait_for_http_ready(
    host: &str,
    port: u16,
    child: &mut std::process::Child,
    timeout_sec: u64,
) -> Result<(), String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(2))
        .build()
        .map_err(|e| format!("Failed to build frontend health client: {}", e))?;
    let url = format!("http://{}:{}/", host, port);
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(timeout_sec);
    loop {
        if let Ok(Some(status)) = child.try_wait() {
            return Err(format!(
                "Frontend process exited before serving (status: {}). Another service may own port {}.",
                status,
                port
            ));
        }
        if client.get(&url).send().await.map(|r| r.status().is_success()).unwrap_or(false) {
            return Ok(());
        }
        if std::time::Instant::now() >= deadline {
            return Err(format!(
                "Frontend did not become ready on {}:{} within {}s.",
                host, port, timeout_sec
            ));
        }
        tokio::time::sleep(std::time::Duration::from_millis(300)).await;
    }
}
