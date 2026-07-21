//! 权限管理器模块
//!
//! [INPUT]
//! - cli_agent_types::PermissionMode (POS: Explore/Ask/Auto 三级模式)
//! - Agent Runner permission.request 事件（经 commands/agent IPC）
//!
//! [OUTPUT]
//! - PermissionManager: 危险命令黑名单与模式循环决策
//!
//! [POS]
//! CLI 可视化权限决策层；Explore 只读 / Ask 确认 / Auto 自动（危险命令除外）。

use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::sync::Arc;
use tokio::sync::RwLock;

use crate::cli_agent_types::PermissionMode;

// ============================================================================
// 危险命令黑名单（借鉴 craft-agents）
// ============================================================================

/// 危险命令集合
///
/// 这些命令即使在 Auto 模式下也需要用户确认。
/// 借鉴 craft-agents 的 DANGEROUS_COMMANDS。
const DANGEROUS_COMMANDS: &[&str] = &[
    // 文件删除
    "rm",
    "rmdir",
    "del",
    "unlink",
    // 权限提升
    "sudo",
    "su",
    "doas",
    // 权限修改
    "chmod",
    "chown",
    "chgrp",
    // 文件移动/复制（可能覆盖）
    "mv",
    "cp",
    // 底层磁盘操作
    "dd",
    "mkfs",
    "fdisk",
    "parted",
    "format",
    // 进程控制
    "kill",
    "killall",
    "pkill",
    "taskkill",
    // 系统控制
    "reboot",
    "shutdown",
    "halt",
    "poweroff",
    // 网络操作
    "curl",
    "wget",
    "ssh",
    "scp",
    "rsync",
    // Git 危险操作
    "git push",
    "git reset",
    "git rebase",
    "git checkout",
    "git clean",
    "git stash drop",
];

/// 写操作工具集合
const WRITE_TOOLS: &[&str] = &[
    "write_file",
    "edit_file",
    "bash",
    "shell",
    "execute",
    "run",
    "create_file",
    "delete_file",
    "move_file",
    "rename_file",
];

// ============================================================================
// 权限请求
// ============================================================================

/// 权限请求
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PermissionRequest {
    /// 请求 ID
    pub request_id: String,
    /// 工具名称
    pub tool_name: String,
    /// 命令内容
    pub command: String,
    /// 是否为危险命令
    pub is_dangerous: bool,
}

/// 权限响应
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct PermissionResponse {
    /// 是否允许
    pub allowed: bool,
    /// 是否始终允许此工具
    pub always_allow: bool,
}

// ============================================================================
// 权限管理器
// ============================================================================

/// 权限管理器
///
/// 线程安全，支持运行时动态切换权限模式。
pub struct PermissionManager {
    /// 当前权限模式
    mode: Arc<RwLock<PermissionMode>>,
    /// 始终允许的工具集合
    always_allowed_tools: Arc<RwLock<HashSet<String>>>,
}

impl PermissionManager {
    /// 创建新的权限管理器
    pub fn new() -> Self {
        Self {
            mode: Arc::new(RwLock::new(PermissionMode::Ask)),
            always_allowed_tools: Arc::new(RwLock::new(HashSet::new())),
        }
    }

    /// 使用指定模式创建
    pub fn with_mode(mode: PermissionMode) -> Self {
        Self {
            mode: Arc::new(RwLock::new(mode)),
            always_allowed_tools: Arc::new(RwLock::new(HashSet::new())),
        }
    }

    /// 获取当前权限模式
    pub async fn get_mode(&self) -> PermissionMode {
        *self.mode.read().await
    }

    /// 设置权限模式
    pub async fn set_mode(&self, mode: PermissionMode) {
        *self.mode.write().await = mode;
    }

    /// 循环切换权限模式（SHIFT+TAB）
    pub async fn cycle_mode(&self) -> PermissionMode {
        let mut mode = self.mode.write().await;
        *mode = mode.next();
        *mode
    }

    /// 添加始终允许的工具
    pub async fn add_always_allow(&self, tool_name: &str) {
        self.always_allowed_tools
            .write()
            .await
            .insert(tool_name.to_string());
    }

    /// 移除始终允许的工具
    pub async fn remove_always_allow(&self, tool_name: &str) {
        self.always_allowed_tools.write().await.remove(tool_name);
    }

    /// 清除所有始终允许的工具
    pub async fn clear_always_allow(&self) {
        self.always_allowed_tools.write().await.clear();
    }

    /// 检查工具权限
    ///
    /// 返回值：
    /// - Ok(true): 允许执行
    /// - Ok(false): 拒绝执行（Explore 模式下的写操作）
    /// - Err(PermissionRequest): 需要用户确认
    pub async fn check_permission(
        &self,
        tool_name: &str,
        command: &str,
    ) -> Result<bool, PermissionRequest> {
        let mode = self.get_mode().await;
        let is_dangerous = Self::is_dangerous_command(command);
        let is_write = Self::is_write_operation(tool_name);

        match mode {
            PermissionMode::Explore => {
                // Explore 模式：阻止所有写操作
                if is_write {
                    Ok(false)
                } else {
                    Ok(true)
                }
            }
            PermissionMode::Auto => {
                // Auto 模式：自动批准，但危险命令仍需确认
                if is_dangerous {
                    Err(self.create_permission_request(tool_name, command, true))
                } else {
                    Ok(true)
                }
            }
            PermissionMode::Ask => {
                // Ask 模式：检查 always_allow 列表
                let always_allowed = self.always_allowed_tools.read().await;
                if always_allowed.contains(tool_name) && !is_dangerous {
                    return Ok(true);
                }

                // 需要用户确认
                Err(self.create_permission_request(tool_name, command, is_dangerous))
            }
        }
    }

    /// 检查是否为危险命令
    pub fn is_dangerous_command(command: &str) -> bool {
        let command_lower = command.to_lowercase();
        let trimmed = command_lower.trim();

        // 检查命令是否以危险命令开头
        for &dangerous in DANGEROUS_COMMANDS {
            if let Some(after) = trimmed.strip_prefix(dangerous) {
                // 确保是完整的命令词，而不是前缀
                if after.is_empty() || after.starts_with(' ') || after.starts_with('\t') {
                    return true;
                }
            }
        }

        false
    }

    /// 检查是否为写操作
    pub fn is_write_operation(tool_name: &str) -> bool {
        let tool_lower = tool_name.to_lowercase();
        WRITE_TOOLS.iter().any(|&t| tool_lower.contains(t))
    }

    /// 创建权限请求
    fn create_permission_request(
        &self,
        tool_name: &str,
        command: &str,
        is_dangerous: bool,
    ) -> PermissionRequest {
        PermissionRequest {
            request_id: uuid::Uuid::new_v4().to_string(),
            tool_name: tool_name.to_string(),
            command: command.to_string(),
            is_dangerous,
        }
    }
}

impl Default for PermissionManager {
    fn default() -> Self {
        Self::new()
    }
}

// ============================================================================
// 测试
// ============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_dangerous_commands() {
        assert!(PermissionManager::is_dangerous_command("rm -rf /"));
        assert!(PermissionManager::is_dangerous_command("sudo apt update"));
        assert!(PermissionManager::is_dangerous_command(
            "git push origin main"
        ));
        assert!(PermissionManager::is_dangerous_command(
            "curl http://example.com"
        ));

        assert!(!PermissionManager::is_dangerous_command("ls -la"));
        assert!(!PermissionManager::is_dangerous_command("cat file.txt"));
        assert!(!PermissionManager::is_dangerous_command("echo hello"));
        assert!(!PermissionManager::is_dangerous_command("git status"));
    }

    #[test]
    fn test_write_operations() {
        assert!(PermissionManager::is_write_operation("write_file"));
        assert!(PermissionManager::is_write_operation("edit_file"));
        assert!(PermissionManager::is_write_operation("bash"));

        assert!(!PermissionManager::is_write_operation("read_file"));
        assert!(!PermissionManager::is_write_operation("list_directory"));
    }

    #[tokio::test]
    async fn test_permission_modes() {
        let manager = PermissionManager::with_mode(PermissionMode::Explore);

        // Explore 模式阻止写操作
        let result = manager.check_permission("write_file", "echo hello").await;
        assert!(matches!(result, Ok(false)));

        // 但允许读操作
        let result = manager.check_permission("read_file", "cat file.txt").await;
        assert!(matches!(result, Ok(true)));
    }
}
