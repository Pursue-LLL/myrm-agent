//! Python 后端 Sidecar 进程管理（开发态解释器 / 生产态 PyInstaller 二进制）
//!
//! [INPUT]
//! - config::BackendConfig, ConfigManager (POS: 桌面端系统配置与后端绑定端口)
//! - runtime::port::is_port_in_use (POS: 启动前端口冲突检测)
//!
//! [OUTPUT]
//! - start_backend / stop_backend / check_backend_health IPC
//! - PythonBackend: Sidecar 子进程句柄
//!
//! [POS]
//! Desktop 模式 Python 后端生命周期。dev 走 venv `run.py`；release 走 bundled sidecar 二进制，
//! 启动后最多 30s 轮询 `/health`，并在 release 侧校验 sidecar 非空。

use std::process::{Child, Command};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tauri::{AppHandle, Manager, State};

use crate::config::{BackendConfig, ConfigManager};
use uuid::Uuid;

use crate::runtime::port::is_port_in_use;
use crate::runtime::setup_token::SetupTokenState;

const BACKEND_HEALTH_POLL_INTERVAL: Duration = Duration::from_millis(500);
const BACKEND_HEALTH_MAX_ATTEMPTS: u32 = 60;

pub struct PythonBackend {
    pub process: Arc<Mutex<Option<Child>>>,
}

impl PythonBackend {
    pub fn new() -> Self {
        Self {
            process: Arc::new(Mutex::new(None)),
        }
    }
}

/// 启动 Python 后端 Sidecar（使用默认配置）
#[tauri::command]
pub async fn start_backend(
    app: AppHandle,
    backend: State<'_, PythonBackend>,
) -> Result<String, String> {
    let config_manager = ConfigManager::new(&app)?;
    let system_config = config_manager.load();
    let backend_config = BackendConfig::from_system_config(&system_config);

    start_backend_with_config(app, backend, backend_config).await
}

/// 启动 Python 后端 Sidecar（使用指定配置）
pub async fn start_backend_with_config(
    app: AppHandle,
    backend: State<'_, PythonBackend>,
    config: BackendConfig,
) -> Result<String, String> {
    println!("🚀 Starting Python backend with config: {:?}", config);

    {
        let process_guard = backend.process.lock().unwrap();
        if process_guard.is_some() {
            return Ok("Backend is already running".to_string());
        }
    }

    if is_port_in_use(&config.host, config.port) {
        return Err(format!(
            "Port {}:{} is already in use. Please close the conflicting process or change the port in settings.",
            config.host, config.port
        ));
    }

    let is_dev = cfg!(debug_assertions);

    let mut cmd = if is_dev {
        println!("🔧 Development mode: Using Python interpreter");

        let tauri_dir = std::env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| ".".to_string());
        let project_root = std::path::Path::new(&tauri_dir)
            .parent()
            .and_then(|p| p.parent())
            .ok_or("Failed to get project root")?;
        let server_root = project_root.join("myrm-agent-server");
        let run_script = server_root.join("run.py");

        if !run_script.exists() {
            return Err(format!(
                "run.py not found at: {:?}\nProject root: {:?}\nTauri dir: {}",
                run_script, project_root, tauri_dir
            ));
        }

        println!("📜 Python script: {:?}", run_script);
        println!("📂 Server root: {:?}", server_root);

        let venv_python = if cfg!(target_os = "windows") {
            server_root.join(".venv").join("Scripts").join("python.exe")
        } else {
            server_root.join(".venv").join("bin").join("python")
        };

        let python_exe = if venv_python.exists() {
            println!("✅ Using virtual environment Python: {:?}", venv_python);
            venv_python
        } else {
            println!("⚠️  Virtual environment not found, using system Python");
            std::path::PathBuf::from(if cfg!(target_os = "windows") {
                "python.exe"
            } else {
                "python3"
            })
        };

        let mut cmd = Command::new(python_exe);
        cmd.arg(run_script).current_dir(&server_root);
        cmd
    } else {
        println!("📦 Production mode: Using packaged binary");

        let binary_name = if cfg!(target_os = "windows") {
            "binaries/myrmagent-backend.exe"
        } else {
            "binaries/myrmagent-backend"
        };
        let sidecar_path = app
            .path()
            .resolve(binary_name, tauri::path::BaseDirectory::Resource)
            .map_err(|e| format!("Failed to resolve sidecar path: {}", e))?;

        println!("📦 Sidecar path: {:?}", sidecar_path);

        let sidecar_len = std::fs::metadata(&sidecar_path)
            .map(|meta| meta.len())
            .unwrap_or(0);
        if sidecar_len == 0 {
            return Err(format!(
                "Backend sidecar binary is missing or empty at {:?}. \
                 Build it with: python myrm-agent-desktop/sidecar/build.py",
                sidecar_path
            ));
        }

        Command::new(sidecar_path)
    };

    cmd.env("DEPLOY_MODE", "local")
        .env("PORT", config.port.to_string())
        .env("HOST", &config.host);

    if config.webui_mode {
        cmd.env("WEBUI_MODE", "true");
        if config.remote_mode {
            cmd.env("WEBUI_REMOTE_MODE", "true");

            let setup_token = Uuid::new_v4().to_string();
            cmd.env("WEBUI_SETUP_TOKEN", &setup_token);

            if let Some(state) = app.try_state::<SetupTokenState>() {
                if let Ok(mut guard) = state.token.lock() {
                    *guard = Some(setup_token.clone());
                }
            }

            println!("🌐 WebUI Remote mode: {}:{}", config.host, config.port);
            println!("🔑 Setup token generated for first-time admin setup");
        } else {
            cmd.env("WEBUI_REMOTE_MODE", "false");
            println!("🔒 WebUI Local mode: {}:{}", config.host, config.port);
        }
    } else {
        println!("🖥️  Desktop mode: {}:{}", config.host, config.port);
    }

    super::suppress_console_window(&mut cmd);
    let child = cmd
        .spawn()
        .map_err(|e| format!("Failed to start backend: {}", e))?;

    {
        let mut process_guard = backend.process.lock().unwrap();
        *process_guard = Some(child);
    }

    println!("✅ Backend process started");

    for i in 0..BACKEND_HEALTH_MAX_ATTEMPTS {
        tokio::time::sleep(BACKEND_HEALTH_POLL_INTERVAL).await;

        match check_health_with_port(config.port).await {
            Ok(true) => {
                println!("✅ Backend is healthy after {} attempts", i + 1);
                return Ok("Backend started and healthy".to_string());
            }
            _ => continue,
        }
    }

    Ok("Backend started but health check timeout".to_string())
}

async fn check_health_with_port(port: u16) -> Result<bool, String> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .map_err(|e| format!("Failed to create HTTP client: {}", e))?;

    let url = format!("http://127.0.0.1:{}/health", port);
    match client.get(&url).send().await {
        Ok(response) => {
            if response.status().is_success() {
                Ok(true)
            } else {
                Err(format!(
                    "Health check failed with status: {}",
                    response.status()
                ))
            }
        }
        Err(e) => Err(format!("Health check request failed: {}", e)),
    }
}

#[tauri::command]
pub fn stop_backend(backend: State<'_, PythonBackend>) -> Result<String, String> {
    println!("Stopping Python backend...");

    let mut process_guard = backend.process.lock().unwrap();

    if let Some(mut child) = process_guard.take() {
        match child.kill() {
            Ok(_) => {
                println!("Backend process killed");
                Ok("Backend stopped successfully".to_string())
            }
            Err(e) => Err(format!("Failed to stop backend: {}", e)),
        }
    } else {
        Ok("Backend is not running".to_string())
    }
}

#[tauri::command]
pub async fn check_backend_health(app: AppHandle) -> Result<bool, String> {
    let config_manager = ConfigManager::new(&app)?;
    let system_config = config_manager.load();
    let port = BackendConfig::from_system_config(&system_config).port;
    check_health_with_port(port).await
}

#[tauri::command]
pub fn get_backend_status(backend: State<'_, PythonBackend>) -> Result<String, String> {
    let process_guard = backend.process.lock().unwrap();

    if process_guard.is_some() {
        Ok("running".to_string())
    } else {
        Ok("stopped".to_string())
    }
}
