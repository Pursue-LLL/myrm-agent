//! WebUI 系统配置管理模块
//!
//! 负责读取、保存和管理 WebUI 服务模式的配置。
//! 配置文件存储在系统的应用配置目录中。
//!
//! ⚠️ 自更新提示：一旦本模块有任何变化，请更新 I/O/P 注释。
//!
//! [INPUT]
//! - Tauri AppHandle（应用配置目录路径）
//! - 磁盘上的 config.json 文件（持久化配置）
//!
//! [OUTPUT]
//! - SystemConfig（WebUI 模式、端口、托盘行为、开机自启、快捷键等）
//! - BackendConfig（Python FastAPI 启动参数）
//! - FrontendConfig（Next.js Server 启动参数）
//!
//! [POS]
//! 配置管理的唯一入口。负责 Sidecar 进程配置的加载、保存、默认值生成
//! 和 Tauri 桌面端的 WebUI 模式配置。

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use tauri::{AppHandle, Manager};

/// 系统配置结构
#[derive(Serialize, Deserialize, Clone, Debug)]
#[serde(rename_all = "camelCase")]
pub struct SystemConfig {
    /// 是否启用 WebUI 模式
    pub enable_webui_mode: bool,
    
    /// 是否允许远程访问
    pub enable_remote_access: bool,
    
    /// WebUI 前端服务端口（Next.js Server）
    pub webui_port: u16,
    
    /// API 后端服务端口（Python FastAPI）
    pub api_port: u16,
    
    /// 是否需要密码（远程访问时强制开启）
    pub require_password: bool,
    
    /// 启动时自动开启 WebUI 服务
    pub auto_start_webui: bool,
    
    /// 关闭窗口时隐藏到托盘（而不是直接退出）
    #[serde(default = "default_close_to_tray")]
    pub close_to_tray: bool,

    /// 开机自动启动（登录后后台运行，仅显示托盘图标）
    #[serde(default = "default_auto_launch_at_login")]
    pub auto_launch_at_login: bool,
    
    /// 配置文件版本（用于未来迁移）
    pub config_version: u8,
    
    /// 全局唤醒快捷键
    #[serde(default = "default_global_shortcut")]
    pub global_shortcut: String,

    /// Appshot 截屏快捷键（按下后截取当前屏幕+提取窗口文本发送到 Agent 对话）
    #[serde(default = "default_appshot_shortcut")]
    pub appshot_shortcut: String,

    /// 是否启用 Locked Use（Computer Use 锁屏操作能力），默认关闭
    #[serde(default)]
    pub locked_use_enabled: bool,

    /// Appshot 截屏隐私黑名单：前台应用名命中时跳过截图，防止敏感应用内容被发往云端 LLM
    #[serde(default = "default_appshot_excluded_apps")]
    pub appshot_excluded_apps: Vec<String>,
}

fn default_close_to_tray() -> bool {
    true
}

fn default_auto_launch_at_login() -> bool {
    true
}

fn default_global_shortcut() -> String {
    "Option+Space".to_string()
}

fn default_appshot_shortcut() -> String {
    "CommandOrControl+Shift+A".to_string()
}

fn default_appshot_excluded_apps() -> Vec<String> {
    vec![
        "微信".to_string(),
        "WeChat".to_string(),
        "1Password".to_string(),
        "Bitwarden".to_string(),
        "KeePassXC".to_string(),
        "LastPass".to_string(),
    ]
}

impl Default for SystemConfig {
    fn default() -> Self {
        Self {
            enable_webui_mode: false,
            enable_remote_access: false,
            webui_port: 3000,
            api_port: 25808,
            require_password: true,
            auto_start_webui: true,
            close_to_tray: true,
            auto_launch_at_login: true,
            config_version: 1,
            global_shortcut: "Option+Space".to_string(),
            appshot_shortcut: "CommandOrControl+Shift+A".to_string(),
            locked_use_enabled: false,
            appshot_excluded_apps: default_appshot_excluded_apps(),
        }
    }
}

/// 后端启动配置
#[derive(Clone, Debug)]
pub struct BackendConfig {
    pub port: u16,
    pub host: String,
    pub webui_mode: bool,
    pub remote_mode: bool,
}

impl BackendConfig {
    /// 从系统配置创建后端配置
    pub fn from_system_config(config: &SystemConfig) -> Self {
        if config.enable_webui_mode {
            Self {
                port: config.api_port,
                host: if config.enable_remote_access {
                    "0.0.0.0".to_string()
                } else {
                    "127.0.0.1".to_string()
                },
                webui_mode: true,
                remote_mode: config.enable_remote_access,
            }
        } else {
            // Desktop 模式默认配置
            Self {
                port: 8080,
                host: "127.0.0.1".to_string(),
                webui_mode: false,
                remote_mode: false,
            }
        }
    }
}

/// 前端启动配置
#[derive(Clone, Debug)]
pub struct FrontendConfig {
    pub port: u16,
    pub host: String,
    pub api_port: u16,
}

impl FrontendConfig {
    /// 从系统配置创建前端配置
    pub fn from_system_config(config: &SystemConfig) -> Self {
        Self {
            port: config.webui_port,
            host: if config.enable_remote_access {
                "0.0.0.0".to_string()
            } else {
                "127.0.0.1".to_string()
            },
            api_port: config.api_port,
        }
    }
}

/// 配置管理器
pub struct ConfigManager {
    config_path: PathBuf,
}

impl ConfigManager {
    /// 创建配置管理器
    pub fn new(app: &AppHandle) -> Result<Self, String> {
        let config_dir = app
            .path()
            .app_config_dir()
            .map_err(|e| format!("Failed to get config dir: {}", e))?;
        
        // 确保配置目录存在
        fs::create_dir_all(&config_dir)
            .map_err(|e| format!("Failed to create config dir: {}", e))?;
        
        let config_path = config_dir.join("system_config.json");
        
        println!("📂 Config path: {:?}", config_path);
        
        Ok(Self { config_path })
    }
    
    /// 加载配置
    pub fn load(&self) -> SystemConfig {
        if let Ok(content) = fs::read_to_string(&self.config_path) {
            match serde_json::from_str(&content) {
                Ok(config) => {
                    println!("✅ Loaded config from file");
                    config
                }
                Err(e) => {
                    println!("⚠️  Failed to parse config: {}, using default", e);
                    SystemConfig::default()
                }
            }
        } else {
            println!("ℹ️  No config file found, using default");
            SystemConfig::default()
        }
    }
    
    /// 保存配置
    pub fn save(&self, config: &SystemConfig) -> Result<(), String> {
        let json = serde_json::to_string_pretty(config)
            .map_err(|e| format!("Failed to serialize config: {}", e))?;
        
        fs::write(&self.config_path, json)
            .map_err(|e| format!("Failed to write config: {}", e))?;
        
        println!("✅ Config saved to {:?}", self.config_path);
        Ok(())
    }
    
    /// 重置为默认配置
    pub fn reset(&self) -> Result<(), String> {
        let default_config = SystemConfig::default();
        self.save(&default_config)?;
        println!("✅ Config reset to default");
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_config_has_auto_launch_enabled() {
        let config = SystemConfig::default();
        assert!(config.auto_launch_at_login);
        assert!(config.close_to_tray);
    }

    #[test]
    fn serde_round_trip_preserves_all_fields() {
        let config = SystemConfig::default();
        let json = serde_json::to_string(&config).unwrap();
        let deserialized: SystemConfig = serde_json::from_str(&json).unwrap();

        assert_eq!(config.auto_launch_at_login, deserialized.auto_launch_at_login);
        assert_eq!(config.close_to_tray, deserialized.close_to_tray);
        assert_eq!(config.enable_webui_mode, deserialized.enable_webui_mode);
        assert_eq!(config.global_shortcut, deserialized.global_shortcut);
    }

    #[test]
    fn serde_camel_case_field_names() {
        let config = SystemConfig::default();
        let json = serde_json::to_string(&config).unwrap();

        assert!(json.contains("autoLaunchAtLogin"));
        assert!(json.contains("closeToTray"));
        assert!(json.contains("enableWebuiMode"));
        assert!(!json.contains("auto_launch_at_login"));
    }

    #[test]
    fn deserialize_legacy_config_without_auto_launch() {
        let legacy_json = r#"{
            "enableWebuiMode": false,
            "enableRemoteAccess": false,
            "webuiPort": 3000,
            "apiPort": 25808,
            "requirePassword": true,
            "autoStartWebui": true,
            "closeToTray": true,
            "configVersion": 1,
            "globalShortcut": "Option+Space",
            "appshotShortcut": "CommandOrControl+Shift+A",
            "appshotExcludedApps": [],
            "lockedUseEnabled": false
        }"#;

        let config: SystemConfig = serde_json::from_str(legacy_json).unwrap();
        assert!(config.auto_launch_at_login, "should default to true for legacy configs");
    }

    #[test]
    fn backend_config_from_system_config() {
        let mut sys = SystemConfig::default();
        sys.enable_webui_mode = true;
        sys.enable_remote_access = true;
        sys.api_port = 9999;

        let backend = BackendConfig::from_system_config(&sys);
        assert_eq!(backend.port, 9999);
        assert_eq!(backend.host, "0.0.0.0");
        assert!(backend.webui_mode);
        assert!(backend.remote_mode);
    }

    #[test]
    fn frontend_config_from_system_config() {
        let mut sys = SystemConfig::default();
        sys.webui_port = 4000;
        sys.api_port = 8888;
        sys.enable_remote_access = false;

        let frontend = FrontendConfig::from_system_config(&sys);
        assert_eq!(frontend.port, 4000);
        assert_eq!(frontend.host, "127.0.0.1");
        assert_eq!(frontend.api_port, 8888);
    }
}
