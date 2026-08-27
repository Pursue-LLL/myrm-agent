//! Sidecar 独立引擎运行时版本管理与故障自动回滚器
//!
//! [INPUT]
//! - app_data_dir / versions 目录
//! - versions.json 状态清单 (current_version, last_known_good, broken_versions)
//! - resource_dir 内置工厂保底二进制
//!
//! [OUTPUT]
//! - SidecarVersionManager: 解析当前可启动二进制路径、管理版本隔离目录、执行故障回滚与版本拉黑
//!
//! [POS]
//! 桌面端 Sidecar 运行时解耦升级与自愈架构。支持下载增量解压至 versions/<tag>/，
//! 启动失败时自动回滚至 last_known_good 并将故障版本追加至 broken_versions，
//! 双重故障自动降级至 Factory Bundled Binary。

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};
use serde::{Deserialize, Serialize};

const VERSIONS_JSON_FILE: &str = "versions.json";
const VERSIONS_DIR_NAME: &str = "versions";

/// 版本状态清单持久化结构
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SidecarVersionManifest {
    /// 当前活跃版本 Tag（如 "v1.2.1" 或 None 使用内置版）
    pub current_version: Option<String>,
    /// 上一个已知健康的稳定版本 Tag
    pub last_known_good: Option<String>,
    /// 已知启动崩溃的故障版本黑名单（避免死循环重试）
    #[serde(default)]
    pub broken_versions: HashSet<String>,
}

impl Default for SidecarVersionManifest {
    fn default() -> Self {
        Self {
            current_version: None,
            last_known_good: None,
            broken_versions: HashSet::new(),
        }
    }
}

/// Sidecar 运行时版本管理器
pub struct SidecarVersionManager {
    versions_root: PathBuf,
    manifest_path: PathBuf,
    factory_bundle_path: PathBuf,
}

impl SidecarVersionManager {
    /// 初始化版本管理器
    pub fn new(app_data_dir: &Path, factory_bundle_path: &Path) -> Self {
        let versions_root = app_data_dir.join(VERSIONS_DIR_NAME);
        let manifest_path = versions_root.join(VERSIONS_JSON_FILE);

        Self {
            versions_root,
            manifest_path,
            factory_bundle_path: factory_bundle_path.to_path_buf(),
        }
    }

    /// 获取版本根目录
    pub fn versions_root(&self) -> &Path {
        &self.versions_root
    }

    /// 读取或初始化 manifest
    pub fn load_manifest(&self) -> SidecarVersionManifest {
        if !self.manifest_path.exists() {
            return SidecarVersionManifest::default();
        }

        match fs::read_to_string(&self.manifest_path) {
            Ok(content) => serde_json::from_str(&content).unwrap_or_default(),
            Err(_) => SidecarVersionManifest::default(),
        }
    }

    /// 原子保存 manifest
    pub fn save_manifest(&self, manifest: &SidecarVersionManifest) -> Result<(), String> {
        if let Err(e) = fs::create_dir_all(&self.versions_root) {
            return Err(format!("Failed to create versions directory: {e}"));
        }

        let content = serde_json::to_string_pretty(manifest)
            .map_err(|e| format!("Failed to serialize versions manifest: {e}"))?;

        let temp_path = self.manifest_path.with_extension("tmp");
        fs::write(&temp_path, content)
            .map_err(|e| format!("Failed to write temporary manifest: {e}"))?;

        fs::rename(&temp_path, &self.manifest_path)
            .map_err(|e| format!("Failed to atomic rename manifest: {e}"))?;

        Ok(())
    }

    /// 解析指定版本的二进制可执行文件路径
    fn resolve_version_binary(&self, version: &str) -> PathBuf {
        let binary_name = if cfg!(target_os = "windows") {
            "myrmagent-backend.exe"
        } else {
            "myrmagent-backend"
        };
        self.versions_root.join(version).join(binary_name)
    }

    /// 校验二进制文件是否存在、非空并在 Unix 上具备可执行权限
    fn validate_and_prepare_binary(&self, path: &Path) -> bool {
        if !path.exists() {
            return false;
        }

        let len = fs::metadata(path).map(|m| m.len()).unwrap_or(0);
        if len == 0 {
            return false;
        }

        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            if let Ok(metadata) = fs::metadata(path) {
                let mut perms = metadata.permissions();
                if perms.mode() & 0o111 == 0 {
                    perms.set_mode(0o755);
                    let _ = fs::set_permissions(path, perms);
                }
            }
        }

        true
    }

    /// 解析当前应该启动的 Sidecar 二进制路径
    /// 降级链：Current Downloaded -> Last-Known-Good -> Factory Bundled Binary
    pub fn resolve_launch_binary(&self) -> (PathBuf, Option<String>) {
        let manifest = self.load_manifest();

        // 1. 尝试启动 current_version
        if let Some(ref current) = manifest.current_version {
            if !manifest.broken_versions.contains(current) {
                let candidate = self.resolve_version_binary(current);
                if self.validate_and_prepare_binary(&candidate) {
                    return (candidate, Some(current.clone()));
                }
            }
        }

        // 2. 尝试降级至 last_known_good
        if let Some(ref stable) = manifest.last_known_good {
            if !manifest.broken_versions.contains(stable) {
                let candidate = self.resolve_version_binary(stable);
                if self.validate_and_prepare_binary(&candidate) {
                    return (candidate, Some(stable.clone()));
                }
            }
        }

        // 3. 最终保底：工厂内置版本
        (self.factory_bundle_path.clone(), None)
    }

    /// 标记当前启动版本健康可用（晋升为 last_known_good）
    pub fn mark_version_healthy(&self, version: Option<&str>) -> Result<(), String> {
        let Some(ver) = version else {
            return Ok(()); // 工厂版本无需记录
        };

        let mut manifest = self.load_manifest();
        manifest.last_known_good = Some(ver.to_string());
        self.save_manifest(&manifest)
    }

    /// 标记指定版本启动失败并触发自动回滚自愈
    /// 返回回滚后应启动的下一个版本路径
    pub fn mark_version_broken_and_rollback(&self, failed_version: Option<&str>) -> (PathBuf, Option<String>) {
        if let Some(failed) = failed_version {
            let mut manifest = self.load_manifest();
            manifest.broken_versions.insert(failed.to_string());

            // 若当前失败版本就是 current_version，则自动重置回 last_known_good
            if manifest.current_version.as_deref() == Some(failed) {
                manifest.current_version = manifest.last_known_good.clone();
            }

            let _ = self.save_manifest(&manifest);
        }

        self.resolve_launch_binary()
    }
}
