//! 桌面统一进程注册表实现
//!
//! [INPUT]
//! - super::types::{ManagedProcessEntry, ProcessRole, ProcessStatus}
//! - crate::utils::process_tree::kill_process_tree (POS: 跨平台进程树级联销毁)
//!
//! [OUTPUT]
//! - ProcessRegistry: 线程安全的全局受管进程注册中心
//!
//! [POS]
//! 维护桌面端所有 Sidecar 及派生进程的生命周期，提供毫秒级事件流转与定点销毁能力。

use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

use super::types::{ManagedProcessEntry, ProcessRole, ProcessStatus};
use crate::utils::process_tree::kill_process_tree;

/// 已退出历史进程最大保留条数（LRU 边界防护，防止内存无限膨胀）
const MAX_STOPPED_HISTORY_ENTRIES: usize = 50;

/// 桌面进程注册中心
#[derive(Clone)]
pub struct ProcessRegistry {
    entries: Arc<RwLock<HashMap<String, ManagedProcessEntry>>>,
}

impl ProcessRegistry {
    /// 创建新的注册表实例
    pub fn new() -> Self {
        Self {
            entries: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// 登记子进程 Spawn 事件
    pub async fn register_spawn(&self, id: &str, role: ProcessRole, pid: Option<u32>) {
        let mut map = self.entries.write().await;
        let mut entry = ManagedProcessEntry::new(id, role, pid);
        if let Some(old) = map.get(id) {
            entry.restart_count = old.restart_count;
        }
        map.insert(id.to_string(), entry);
    }

    /// 标记子进程正常退出
    pub async fn mark_stopped(&self, id: &str, exit_code: Option<i32>) {
        let mut map = self.entries.write().await;
        if let Some(entry) = map.get_mut(id) {
            let now = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0);
            entry.status = ProcessStatus::Stopped;
            entry.ended_at = Some(now);
            entry.exit_code = exit_code;
        }
        self.prune_history(&mut map);
    }

    /// 标记子进程异常崩溃
    pub async fn mark_crashed(&self, id: &str, exit_code: Option<i32>, error_message: Option<String>) {
        let mut map = self.entries.write().await;
        if let Some(entry) = map.get_mut(id) {
            let now = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0);
            entry.status = ProcessStatus::Crashed {
                exit_code,
                error_message: error_message.clone(),
            };
            entry.ended_at = Some(now);
            entry.exit_code = exit_code;
            entry.error_message = error_message;
        }
        self.prune_history(&mut map);
    }

    /// 记录自愈重启递增
    pub async fn record_restart(&self, id: &str) {
        let mut map = self.entries.write().await;
        if let Some(entry) = map.get_mut(id) {
            entry.restart_count += 1;
        }
    }

    /// 获取所有受管进程快照
    pub async fn snapshot_all(&self) -> Vec<ManagedProcessEntry> {
        let map = self.entries.read().await;
        map.values().cloned().collect()
    }

    /// 查询特定进程状态
    pub async fn get_entry(&self, id: &str) -> Option<ManagedProcessEntry> {
        let map = self.entries.read().await;
        map.get(id).cloned()
    }

    /// 定向强制终止指定受管进程及其整棵子孙进程树
    pub async fn kill_managed_process(&self, id: &str) -> Result<(), String> {
        let pid_opt = {
            let map = self.entries.read().await;
            map.get(id).and_then(|e| e.pid)
        };

        if let Some(pid) = pid_opt {
            kill_process_tree(pid);
            self.mark_stopped(id, Some(-1)).await;
            Ok(())
        } else {
            Err(format!("Process '{}' has no active PID or is not registered", id))
        }
    }

    /// 修剪过量的已停止/已崩溃历史记录，保持恒定内存
    fn prune_history(&self, map: &mut HashMap<String, ManagedProcessEntry>) {
        let stopped_keys: Vec<String> = map
            .iter()
            .filter(|(_, entry)| matches!(entry.status, ProcessStatus::Stopped | ProcessStatus::Crashed { .. } | ProcessStatus::OrphanReclaimed))
            .map(|(k, _)| k.clone())
            .collect();

        if stopped_keys.len() > MAX_STOPPED_HISTORY_ENTRIES {
            let excess = stopped_keys.len() - MAX_STOPPED_HISTORY_ENTRIES;
            for key in stopped_keys.iter().take(excess) {
                map.remove(key);
            }
        }
    }
}

impl Default for ProcessRegistry {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn test_registry_lifecycle() {
        let registry = ProcessRegistry::new();

        // 1. 注册 Spawn
        registry.register_spawn("sidecar:test", ProcessRole::Backend, Some(12345)).await;
        let entry = registry.get_entry("sidecar:test").await.expect("entry should exist");
        assert_eq!(entry.pid, Some(12345));
        assert_eq!(entry.status, ProcessStatus::Running);
        assert_eq!(entry.restart_count, 0);

        // 2. 自愈重启记录
        registry.record_restart("sidecar:test").await;
        let entry = registry.get_entry("sidecar:test").await.unwrap();
        assert_eq!(entry.restart_count, 1);

        // 3. 标记崩溃
        registry
            .mark_crashed("sidecar:test", Some(139), Some("SIGSEGV".to_string()))
            .await;
        let entry = registry.get_entry("sidecar:test").await.unwrap();
        assert!(matches!(entry.status, ProcessStatus::Crashed { exit_code: Some(139), .. }));
        assert_eq!(entry.exit_code, Some(139));
        assert_eq!(entry.error_message.as_deref(), Some("SIGSEGV"));

        // 4. 再次 Spawn 保持 restart_count
        registry.register_spawn("sidecar:test", ProcessRole::Backend, Some(12346)).await;
        let entry = registry.get_entry("sidecar:test").await.unwrap();
        assert_eq!(entry.pid, Some(12346));
        assert_eq!(entry.restart_count, 1);
        assert_eq!(entry.status, ProcessStatus::Running);
    }
}
