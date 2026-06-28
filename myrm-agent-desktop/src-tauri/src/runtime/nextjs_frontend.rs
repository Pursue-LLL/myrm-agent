//! Next.js Standalone 前端进程管理（WebUI 模式）

use std::process::{Child, Command};
use std::sync::{Arc, Mutex};

use tauri::{AppHandle, Manager, State};

use crate::config::FrontendConfig;
use crate::runtime::port::is_port_in_use;

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
        return Err(format!(
            "Port {}:{} is already in use. Please close the conflicting process or change the port in settings.",
            config.host, config.port
        ));
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
    cmd.arg("server.js")
        .current_dir(&nextjs_dir)
        .env("PORT", config.port.to_string())
        .env("HOSTNAME", &config.host)
        .env("API_PORT", config.api_port.to_string());

    println!("🌐 Frontend will listen on {}:{}", config.host, config.port);
    println!("🔗 API proxy to localhost:{}", config.api_port);

    super::suppress_console_window(&mut cmd);
    let child = cmd
        .spawn()
        .map_err(|e| format!("Failed to start frontend: {}", e))?;

    {
        let mut process_guard = frontend.process.lock().unwrap();
        *process_guard = Some(child);
    }

    println!("✅ Frontend process started");

    Ok("Frontend started successfully".to_string())
}

#[tauri::command]
pub fn stop_frontend(frontend: State<'_, NextJSFrontend>) -> Result<String, String> {
    println!("Stopping Next.js frontend...");

    let mut process_guard = frontend.process.lock().unwrap();

    if let Some(mut child) = process_guard.take() {
        match child.kill() {
            Ok(_) => {
                println!("Frontend process killed");
                Ok("Frontend stopped successfully".to_string())
            }
            Err(e) => Err(format!("Failed to stop frontend: {}", e)),
        }
    } else {
        Ok("Frontend is not running".to_string())
    }
}
