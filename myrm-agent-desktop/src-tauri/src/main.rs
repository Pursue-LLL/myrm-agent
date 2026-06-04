//! Tauri 桌面应用入口
//!
//! ⚠️ 自更新提示：一旦我被更新，务必更新：
//! 1. 本文件的 INPUT/OUTPUT/POS 注释
//! 2. 所属文件夹的 _ARCH.md
//!
//! [INPUT]
//! - agents: CLI Agent 适配器（Claude Code 等）
//! - commands: Tauri IPC 命令实现
//! - config: 配置管理（后端地址、WebUI 模式）
//! - permissions: 权限管理（Explore/Ask/Auto）
//! - sessions: CLI 会话生命周期管理
//! - lifecycle: 优雅停机与生命周期管理
//! - tray: 系统托盘与状态管理
//!
//! [OUTPUT]
//! - Tauri 应用实例
//! - IPC 命令注册（start_backend, stop_backend, check_backend_health 等）
//! - Agent 系统命令（create_session, send_message 等）
//!
//! [POS]
//! Tauri 桌面应用的入口点。负责初始化 Tauri 应用、注册插件
//! （shell、dialog）、注册 IPC 命令、管理 Python/Node.js Sidecar
//! 进程生命周期。支持 CLI 可视化工具和 WebUI 远程访问模式。
//! 包含端口冲突检测机制，防止启动失败。

// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod agents;
mod commands;
mod config;
mod permissions;
mod sessions;
mod sidecar;
mod utils;
mod lifecycle;
mod tray;
mod tunnel;

use std::net::TcpListener;
use std::process::{Child, Command};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager, State};
use uuid::Uuid;

use commands::agent::AgentSystemState;
use commands::*;
use config::{BackendConfig, ConfigManager, FrontendConfig};

/// Shared state for identifying the Appshot shortcut in the global handler.
pub static APPSHOT_SHORTCUT_STR: std::sync::Mutex<String> = std::sync::Mutex::new(String::new());

/// Toggle main window visibility (global shortcut handler).
fn handle_toggle_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.is_visible().unwrap_or(false) {
            let _ = window.hide();
            #[cfg(target_os = "macos")]
            {
                let _ = app.set_activation_policy(tauri::ActivationPolicy::Accessory);
            }
        } else {
            #[cfg(target_os = "macos")]
            {
                let _ = app.set_activation_policy(tauri::ActivationPolicy::Regular);
            }
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
}

/// Capture screenshot + extract window text, then emit to frontend (Appshot).
fn handle_appshot_shortcut(app: &AppHandle) {
    let app_handle = app.clone();
    std::thread::spawn(move || {
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis();

        #[cfg(target_os = "macos")]
        let (screenshot_b64, window_title, extracted_text, needs_permission) = {
            capture_appshot_macos()
        };

        #[cfg(not(target_os = "macos"))]
        let (screenshot_b64, window_title, extracted_text, needs_permission) = {
            capture_appshot_fallback()
        };

        let payload = serde_json::json!({
            "screenshot": screenshot_b64,
            "windowTitle": window_title,
            "extractedText": extracted_text,
            "needsPermission": needs_permission,
            "timestamp": timestamp,
        });

        if let Err(e) = app_handle.emit("appshot-captured", payload) {
            eprintln!("Failed to emit appshot event: {}", e);
        }
    });
}

#[cfg(target_os = "macos")]
fn capture_appshot_macos() -> (String, String, String, bool) {
    use std::io::Read;
    use base64::Engine;

    let mut screenshot_b64 = String::new();
    let tmp_path = std::env::temp_dir().join(format!("appshot_{}.jpg", std::process::id()));

    if let Ok(output) = Command::new("screencapture")
        .args(["-x", "-C", "-t", "jpg", tmp_path.to_str().unwrap_or("/tmp/appshot.jpg")])
        .output()
    {
        if output.status.success() {
            if let Ok(mut f) = std::fs::File::open(&tmp_path) {
                let mut buf = Vec::new();
                if f.read_to_end(&mut buf).is_ok() {
                    screenshot_b64 = base64::engine::general_purpose::STANDARD.encode(&buf);
                }
            }
        }
    }
    let _ = std::fs::remove_file(&tmp_path);

    let ax_script = r#"
tell application "System Events"
    set frontApp to first application process whose frontmost is true
    set appName to name of frontApp
    set winTitle to ""
    try
        set winTitle to name of window 1 of frontApp
    end try
    set textParts to {}
    try
        set uiElements to entire contents of window 1 of frontApp
        set maxElements to (count of uiElements)
        if maxElements > 500 then set maxElements to 500
        repeat with i from 1 to maxElements
            set elem to item i of uiElements
            try
                set elemRole to role of elem
                if elemRole is in {"AXTextField", "AXTextArea", "AXStaticText"} then
                    set elemValue to value of elem
                    if elemValue is not missing value and elemValue is not "" then
                        set end of textParts to elemValue
                    end if
                end if
            end try
        end repeat
    end try
    set AppleScript's text item delimiters to linefeed
    return appName & "|||" & winTitle & "|||" & (textParts as string)
end tell
"#;

    let (mut window_title, mut extracted_text, mut needs_permission) =
        (String::new(), String::new(), false);

    if let Ok(output) = Command::new("osascript")
        .args(["-e", ax_script])
        .output()
    {
        if output.status.success() {
            let result = String::from_utf8_lossy(&output.stdout).trim().to_string();
            let parts: Vec<&str> = result.splitn(3, "|||").collect();
            window_title = parts.first().unwrap_or(&"").to_string();
            if parts.len() > 1 {
                window_title = format!("{} - {}", window_title, parts[1]);
            }
            if parts.len() > 2 {
                extracted_text = parts[2].to_string();
            }
        } else {
            let stderr = String::from_utf8_lossy(&output.stderr);
            if stderr.contains("不允许辅助访问") || stderr.to_lowercase().contains("not allowed assistive") {
                needs_permission = true;
            }
            if let Ok(title_out) = Command::new("osascript")
                .args(["-e", r#"tell application "System Events" to get name of first application process whose frontmost is true"#])
                .output()
            {
                if title_out.status.success() {
                    window_title = String::from_utf8_lossy(&title_out.stdout).trim().to_string();
                }
            }
        }
    }

    (screenshot_b64, window_title, extracted_text, needs_permission)
}

#[cfg(not(target_os = "macos"))]
fn capture_appshot_fallback() -> (String, String, String, bool) {
    (String::new(), String::new(), String::new(), false)
}

/// WebUI Remote 模式的 Setup Token（前端 WebView 查询后跳转 setup 页面）
struct SetupTokenState {
    token: Mutex<Option<String>>,
}

/// 获取 Setup Token（仅 Tauri WebView 可调用，远程浏览器无法触发）
#[tauri::command]
fn get_setup_token(state: State<'_, SetupTokenState>) -> Result<Option<String>, String> {
    let guard = state.token.lock().map_err(|e| format!("Lock error: {}", e))?;
    Ok(guard.clone())
}

/// 检查端口是否被占用
fn is_port_in_use(host: &str, port: u16) -> bool {
    TcpListener::bind((host, port)).is_err()
}

// Python 后端进程管理
struct PythonBackend {
    process: Arc<Mutex<Option<Child>>>,
}

impl PythonBackend {
    fn new() -> Self {
        Self {
            process: Arc::new(Mutex::new(None)),
        }
    }
}

// Next.js 前端进程管理
struct NextJSFrontend {
    process: Arc<Mutex<Option<Child>>>,
}

impl NextJSFrontend {
    fn new() -> Self {
        Self {
            process: Arc::new(Mutex::new(None)),
        }
    }
}

/// 启动 Python 后端 Sidecar（使用默认配置）
#[tauri::command]
async fn start_backend(
    app: AppHandle,
    backend: State<'_, PythonBackend>,
) -> Result<String, String> {
    // 读取配置
    let config_manager = ConfigManager::new(&app)?;
    let system_config = config_manager.load();
    let backend_config = BackendConfig::from_system_config(&system_config);
    
    start_backend_with_config(app, backend, backend_config).await
}

/// 启动 Python 后端 Sidecar（使用指定配置）
async fn start_backend_with_config(
    app: AppHandle,
    backend: State<'_, PythonBackend>,
    config: BackendConfig,
) -> Result<String, String> {
    println!("🚀 Starting Python backend with config: {:?}", config);

    // 检查是否已经在运行
    {
        let process_guard = backend.process.lock().unwrap();
        if process_guard.is_some() {
            return Ok("Backend is already running".to_string());
        }
    }
    
    // 检查端口是否被占用
    if is_port_in_use(&config.host, config.port) {
        return Err(format!(
            "Port {}:{} is already in use. Please close the conflicting process or change the port in settings.",
            config.host, config.port
        ));
    }

    // 检测是否为开发模式（通过环境变量或 debug 配置判断）
    let is_dev = cfg!(debug_assertions);
    
    let mut cmd = if is_dev {
        // 开发模式：直接使用 Python 解释器运行 run.py
        println!("🔧 Development mode: Using Python interpreter");
        
        // 获取 run.py 路径
        // 在开发模式下，使用编译时环境变量获取 Cargo 项目目录
        let tauri_dir = std::env::var("CARGO_MANIFEST_DIR")
            .unwrap_or_else(|_| ".".to_string());
        // src-tauri -> myrm-agent-desktop -> myrm-agent (product root)
        let project_root = std::path::Path::new(&tauri_dir)
            .parent()  // -> myrm-agent-desktop
            .and_then(|p| p.parent())  // -> myrm-agent
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
        
        // 获取虚拟环境中的 Python 路径
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
        cmd.arg(run_script)
            .current_dir(&server_root);
        cmd
    } else {
        // 生产模式：使用打包的二进制文件
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
        
        Command::new(sidecar_path)
    };
    
    // 设置通用环境变量
    cmd.env("DEPLOY_MODE", "local")
        .env("PORT", config.port.to_string())
        .env("HOST", &config.host);

    if let Ok(cloudflared_path) = tunnel::resolve_cloudflared_path(&app) {
        cmd.env("CLOUDFLARED_PATH", cloudflared_path);
    }
    
    // WebUI 模式的额外环境变量
    if config.webui_mode {
        cmd.env("WEBUI_MODE", "true");
        if config.remote_mode {
            cmd.env("WEBUI_REMOTE_MODE", "true");

            // Generate setup token for first-time admin setup
            let setup_token = Uuid::new_v4().to_string();
            cmd.env("WEBUI_SETUP_TOKEN", &setup_token);

            // Store token so the WebView can retrieve it via get_setup_token
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

    let child = cmd
        .spawn()
        .map_err(|e| format!("Failed to start backend: {}", e))?;

    // 存储进程句柄
    {
        let mut process_guard = backend.process.lock().unwrap();
        *process_guard = Some(child);
    }

    println!("✅ Backend process started");

    // 等待后端启动（最多 10 秒）
    for i in 0..20 {
        thread::sleep(Duration::from_millis(500));
        
        // 检查健康状态
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

/// 检查后端健康状态（支持自定义端口）
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
                Err(format!("Health check failed with status: {}", response.status()))
            }
        }
        Err(e) => Err(format!("Health check request failed: {}", e)),
    }
}

/// 停止 Python 后端
#[tauri::command]
fn stop_backend(backend: State<'_, PythonBackend>) -> Result<String, String> {
    println!("Stopping Python backend...");

    let mut process_guard = backend.process.lock().unwrap();
    
    if let Some(mut child) = process_guard.take() {
        // 尝试优雅关闭
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

/// 启动 Next.js 前端 Server（WebUI 模式）
async fn start_frontend(
    app: AppHandle,
    frontend: State<'_, NextJSFrontend>,
    config: FrontendConfig,
) -> Result<String, String> {
    println!("🚀 Starting Next.js frontend with config: {:?}", config);

    // 检查是否已经在运行
    {
        let process_guard = frontend.process.lock().unwrap();
        if process_guard.is_some() {
            return Ok("Frontend is already running".to_string());
        }
    }
    
    // 检查端口是否被占用
    if is_port_in_use(&config.host, config.port) {
        return Err(format!(
            "Port {}:{} is already in use. Please close the conflicting process or change the port in settings.",
            config.host, config.port
        ));
    }

    // 检测是否为开发模式
    let is_dev = cfg!(debug_assertions);
    
    // 获取 Next.js standalone 目录
    let nextjs_dir = if is_dev {
        // 开发模式：使用源代码目录
        let tauri_dir = std::env::var("CARGO_MANIFEST_DIR")
            .unwrap_or_else(|_| ".".to_string());
        let project_root = std::path::Path::new(&tauri_dir)
            .parent()
            .and_then(|p| p.parent())
            .ok_or("Failed to get project root")?;
        project_root.join("myrm-agent-frontend/.next/standalone")
    } else {
        // 生产模式：使用打包的 frontend
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
    
    // 查找 Node.js 可执行文件
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
    
    let child = cmd
        .spawn()
        .map_err(|e| format!("Failed to start frontend: {}", e))?;

    // 存储进程句柄
    {
        let mut process_guard = frontend.process.lock().unwrap();
        *process_guard = Some(child);
    }

    println!("✅ Frontend process started");

    Ok("Frontend started successfully".to_string())
}

/// 停止 Next.js 前端
#[tauri::command]
fn stop_frontend(frontend: State<'_, NextJSFrontend>) -> Result<String, String> {
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

/// 检查后端健康状态（Tauri 命令）
#[tauri::command]
async fn check_backend_health() -> Result<bool, String> {
    check_health_with_port(8080).await
}

/// 获取后端状态信息
#[tauri::command]
fn get_backend_status(backend: State<'_, PythonBackend>) -> Result<String, String> {
    let process_guard = backend.process.lock().unwrap();
    
    if process_guard.is_some() {
        Ok("running".to_string())
    } else {
        Ok("stopped".to_string())
    }
}

#[tauri::command]
async fn fix_quarantine_with_auth() -> Result<bool, String> {
    utils::auth::fix_quarantine_with_auth()
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, shortcut, event| {
                    if event.state != tauri_plugin_global_shortcut::ShortcutState::Pressed {
                        return;
                    }

                    let shortcut_str = format!("{shortcut}");
                    let is_appshot = APPSHOT_SHORTCUT_STR
                        .lock()
                        .map_or(false, |saved| *saved == shortcut_str);

                    if is_appshot {
                        handle_appshot_shortcut(app);
                    } else {
                        handle_toggle_window(app);
                    }
                })
                .build(),
        )
        .setup(|app| {
            println!("🚀 Initializing MyrmAgent...");

            // Tauri Updater pubkey 安全校验：占位符状态下 OTA 不安全，必须提示
            match utils::updater_safety::check_updater_pubkey_safety() {
                utils::updater_safety::UpdaterPubkeySafety::Safe => {
                    println!("🔐 Updater pubkey verified, OTA channel is secure");
                }
                utils::updater_safety::UpdaterPubkeySafety::PlaceholderDev => {
                    // Dev build with placeholder: warning printed by check function
                }
                utils::updater_safety::UpdaterPubkeySafety::PlaceholderProd => {
                    // Production with placeholder: never auto-arm updater plugin
                    eprintln!("🚫 Production OTA disabled due to placeholder pubkey");
                }
                utils::updater_safety::UpdaterPubkeySafety::Invalid(reason) => {
                    eprintln!("🚫 Updater config invalid: {reason}");
                }
            }

            // 异步检测 macOS 隔离属性
            let app_handle = app.handle().clone();
            std::thread::spawn(move || {
                if utils::quarantine::scan_and_silent_heal() {
                    println!("⚠️ 检测到 com.apple.quarantine 属性且静默移除失败，需要提权修复");
                    let _ = app_handle.emit("quarantine-detected", ());
                } else {
                    println!("✅ 隔离属性检测通过或已静默修复");
                }
            });

            // 初始化配置管理器
            let config_manager = ConfigManager::new(app.handle())
                .expect("Failed to initialize config manager");
            
            // 加载系统配置
            let system_config = config_manager.load();
            println!("📋 Loaded config: {:?}", system_config);
            
            // 注册全局快捷键
            if !system_config.global_shortcut.is_empty() {
                use tauri_plugin_global_shortcut::GlobalShortcutExt;
                use std::str::FromStr;
                
                if let Ok(shortcut) = tauri_plugin_global_shortcut::Shortcut::from_str(&system_config.global_shortcut) {
                    if let Err(e) = app.global_shortcut().register(shortcut) {
                        println!("⚠️ Failed to register global shortcut: {}", e);
                    } else {
                        println!("⌨️  Global shortcut registered: {}", system_config.global_shortcut);
                    }
                } else {
                    println!("⚠️ Invalid global shortcut format: {}", system_config.global_shortcut);
                }
            }
            
            // 注册 Appshot 截屏快捷键
            if !system_config.appshot_shortcut.is_empty() {
                use tauri_plugin_global_shortcut::GlobalShortcutExt;
                use std::str::FromStr;
                if let Ok(shortcut) = tauri_plugin_global_shortcut::Shortcut::from_str(&system_config.appshot_shortcut) {
                    if let Ok(mut guard) = APPSHOT_SHORTCUT_STR.lock() {
                        *guard = format!("{shortcut}");
                    }
                    if let Err(e) = app.global_shortcut().register(shortcut) {
                        println!("Failed to register appshot shortcut: {}", e);
                    } else {
                        println!("Appshot shortcut registered: {}", system_config.appshot_shortcut);
                    }
                } else {
                    println!("Invalid appshot shortcut format: {}", system_config.appshot_shortcut);
                }
            }

            // 显示当前运行模式
            if system_config.enable_webui_mode {
                if system_config.enable_remote_access {
                    println!("🌐 Running in WebUI Remote mode");
                } else {
                    println!("🔒 Running in WebUI Local mode");
                }
            } else {
                println!("🖥️  Running in Desktop mode");
            }
            
            // 保存配置管理器到 State
            app.manage(config_manager);

            // 初始化 Setup Token State
            app.manage(SetupTokenState {
                token: Mutex::new(None),
            });

            // 初始化电源管理状态
            app.manage(commands::power::PowerState::new());

            // 初始化屏幕锁定管理状态
            app.manage(commands::screen_lock::ScreenLockState::new());

            // 初始化后端状态
            let backend = PythonBackend::new();
            app.manage(backend);

            // 初始化前端状态
            let frontend = NextJSFrontend::new();
            app.manage(frontend);
            
            if let Err(e) = tray::setup_tray(&app.handle().clone()) {
                println!("⚠️ Failed to setup tray: {e}");
            }

            // 初始化 Agent 系统
            // 获取 agent-runner sidecar 路径
            let sidecar_path = if cfg!(debug_assertions) {
                // 开发模式：通过 node 运行源代码（开发者有 node）
                let tauri_dir = std::env::var("CARGO_MANIFEST_DIR")
                    .unwrap_or_else(|_| ".".to_string());
                let project_root = std::path::Path::new(&tauri_dir)
                    .parent()
                    .and_then(|p| p.parent())
                    .map(|p| p.to_path_buf())
                    .unwrap_or_default();
                project_root
                    .join("myrm-agent-desktop/sidecar/agent-runner/dist/index.js")
                    .to_string_lossy()
                    .to_string()
            } else {
                // 生产模式：使用 Bun compile 编译的独立二进制（无需系统 Node.js）
                let binary_name = if cfg!(target_os = "windows") {
                    "binaries/agent-runner.exe"
                } else {
                    "binaries/agent-runner"
                };
                app.path()
                    .resolve(binary_name, tauri::path::BaseDirectory::Resource)
                    .map(|p| p.to_string_lossy().to_string())
                    .unwrap_or_default()
            };
            
            println!("📦 Agent sidecar path: {}", sidecar_path);
            
            // 获取应用数据目录用于会话持久化
            let app_data_dir = app.path().app_data_dir().ok();
            if let Some(ref dir) = app_data_dir {
                println!("📂 App data dir: {:?}", dir);
            }
            
            let agent_system = AgentSystemState::new(sidecar_path, app_data_dir);
            
            // 启动 Agent Sidecar 并设置事件转发
            let agent_system_clone = agent_system.sidecar.clone();
            let sidecar_path_clone = agent_system.sidecar_path.clone();
            let app_handle_for_sidecar = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                tokio::time::sleep(Duration::from_millis(1000)).await;
                
                // 启动 sidecar
                let mut sidecar = agent_system_clone.lock().await;
                match sidecar.start(&sidecar_path_clone).await {
                    Ok(_) => {
                        println!("✅ Agent sidecar started");
                        
                        // 订阅事件并转发到 Tauri
                        let mut event_rx = sidecar.subscribe_events();
                        drop(sidecar); // 释放锁
                        
                        // 事件转发任务
                        tokio::spawn(async move {
                            use tauri::Emitter;
                            while let Ok(event) = event_rx.recv().await {
                                match &event {
                                    sidecar::SidecarEvent::AgentMessage { session_id, message } => {
                                        let event_name = format!("agent:message:{}", session_id);
                                        let _ = app_handle_for_sidecar.emit(&event_name, message);
                                    }
                                    sidecar::SidecarEvent::PermissionRequest { session_id, .. } => {
                                        let event_name = format!("agent:permission:{}", session_id);
                                        let _ = app_handle_for_sidecar.emit(&event_name, &event);
                                    }
                                    sidecar::SidecarEvent::SessionStatus { session_id, status, error } => {
                                        let event_name = format!("agent:status:{}", session_id);
                                        let _ = app_handle_for_sidecar.emit(&event_name, &event);
                                        
                                        // Handle task completion notification when window is hidden or minimized
                                        if status == "completed" || status == "error" {
                                            if let Some(window) = app_handle_for_sidecar.get_webview_window("main") {
                                                let is_visible = window.is_visible().unwrap_or(true);
                                                let is_minimized = window.is_minimized().unwrap_or(false);
                                                if !is_visible || is_minimized {
                                                    use tauri_plugin_notification::NotificationExt;
                                                    let title = match status.as_str() {
                                                        "completed" => "任务已完成",
                                                        "error" => "任务出错",
                                                        _ => "MyrmAgent 通知",
                                                    };
                                                    let body = if let Some(e) = error {
                                                        format!("会话: {}\n错误: {}", session_id, e)
                                                    } else {
                                                        format!("会话: {}", session_id)
                                                    };
                                                    let _ = app_handle_for_sidecar.notification()
                                                        .builder()
                                                        .title(title)
                                                        .body(body)
                                                        .show();
                                                }
                                            }
                                        }
                                        
                                        // Update Tray Tooltip dynamically based on status
                                        if let Some(tray) = app_handle_for_sidecar.tray_by_id("main") {
                                            let tooltip = match status.as_str() {
                                                "running" => "MyrmAgent - 任务执行中...",
                                                "thinking" => "MyrmAgent - 思考中...",
                                                "error" => "MyrmAgent - 发生错误",
                                                "completed" => "MyrmAgent - 空闲",
                                                _ => "MyrmAgent",
                                            };
                                            let _ = tray.set_tooltip(Some(tooltip));
                                        }
                                    }
                                    sidecar::SidecarEvent::Error { message } => {
                                        let _ = app_handle_for_sidecar.emit("agent:error", message);
                                    }
                                }
                            }
                        });
                    }
                    Err(e) => eprintln!("⚠️  Agent sidecar not started: {}", e),
                }
            });
            
            app.manage(agent_system);
            println!("🤖 Agent system initialized");

            // 创建后端配置
            let backend_config = BackendConfig::from_system_config(&system_config);

            // 自动启动 Python 后端
            let app_handle = app.handle().clone();
            let system_config_clone = system_config.clone();
            tauri::async_runtime::spawn(async move {
                tokio::time::sleep(Duration::from_millis(500)).await;
                
                let backend_state = app_handle.state::<PythonBackend>();
                match start_backend_with_config(
                    app_handle.clone(),
                    backend_state,
                    backend_config,
                ).await {
                    Ok(msg) => println!("✅ {}", msg),
                    Err(e) => eprintln!("❌ Failed to auto-start backend: {}", e),
                }

                // 如果启用 WebUI 模式，启动 Next.js Server
                if system_config_clone.enable_webui_mode {
                    println!("🌐 WebUI mode enabled, starting Next.js Server...");
                    tokio::time::sleep(Duration::from_millis(1000)).await;
                    
                    let frontend_config = FrontendConfig::from_system_config(&system_config_clone);
                    let frontend_state = app_handle.state::<NextJSFrontend>();
                    
                    match start_frontend(
                        app_handle.clone(),
                        frontend_state,
                        frontend_config,
                    ).await {
                        Ok(msg) => println!("✅ {}", msg),
                        Err(e) => eprintln!("❌ Failed to auto-start frontend: {}", e),
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            match event {
                tauri::WindowEvent::CloseRequested { api, .. } => {
                    // 获取配置，判断是否最小化到托盘
                    let config_manager = window.app_handle().state::<ConfigManager>();
                    let config = config_manager.load();
                    
                    if config.close_to_tray {
                        let _ = window.hide();
                        api.prevent_close();
                        
                        // Mac: 隐藏窗口后切换为 Accessory 模式，隐藏 Dock 图标
                        #[cfg(target_os = "macos")]
                        {
                            let _ = window.app_handle().set_activation_policy(tauri::ActivationPolicy::Accessory);
                        }
                    }
                }
                tauri::WindowEvent::Destroyed => {
                    // 应用退出时清理进程 (兜底)
                    let app_handle = window.app_handle().clone();
                    tauri::async_runtime::spawn(async move {
                        crate::lifecycle::graceful_shutdown(app_handle).await;
                    });
                }
                _ => {}
            }
        })
        .invoke_handler(tauri::generate_handler![
            fix_quarantine_with_auth,
            // Config commands
            load_system_config,
            save_system_config,
            reset_system_config,
            get_current_mode,
            restart_app,
            get_local_ip,
            get_setup_token,
            update_global_shortcut,
            // Backend commands
            start_backend,
            stop_backend,
            check_backend_health,
            get_backend_status,
            // Frontend commands
            stop_frontend,
            // Agent commands
            detect_agents,
            list_agent_adapters,
            create_agent_session,
            list_agent_sessions,
            get_agent_session,
            delete_agent_session,
            resume_agent_session,
            send_agent_message,
            stop_agent_message,
            respond_agent_permission,
            get_permission_mode,
            set_permission_mode,
            cycle_permission_mode,
            // Power commands
            power_lock_acquire,
            power_lock_release,
            power_lock_status,
            // Screen lock commands
            screen_is_locked,
            screen_unlock,
            screen_relock,
            screen_lock_store_password,
            screen_lock_has_password,
            screen_lock_delete_password,
            screen_lock_platform_support,
            show_visual_approval_overlay,
            hide_visual_approval_overlay,
            // Tray commands
            tray::set_tray_status
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::ExitRequested { api, .. } = event {
                println!("🛑 Exit requested (e.g., Cmd+Q), initiating graceful shutdown...");
                api.prevent_exit();
                let app_handle_clone = app_handle.clone();
                tauri::async_runtime::spawn(async move {
                    crate::lifecycle::graceful_shutdown(app_handle_clone.clone()).await;
                    app_handle_clone.exit(0);
                });
            }
        });
}
