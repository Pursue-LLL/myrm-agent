//! 桌面进程注册表类型定义
//!
//! [INPUT]
//! - serde (POS: 跨 IPC 序列化支持)
//!
//! [OUTPUT]
//! - ProcessRole: 进程角色枚举
//! - ProcessStatus: 进程生命周期状态枚举
//! - ManagedProcessEntry: 单个受管进程元数据记录
//!
//! [POS]
//! 提供桌面端统一进程注册表的基础数据模型。

use serde::{Deserialize, Serialize};

/// 进程角色
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProcessRole {
    /// Python FastAPI 业务后端
    Backend,
    /// Next.js Standalone 前端
    Frontend,
    /// Agent Runner JSON-RPC Sidecar
    AgentRunner,
    /// 独立会话/CLI Agent 任务 Worker
    AgentWorker,
    /// 外部工具/浏览器等支撑进程
    ToolRunner,
}

/// 进程生命周期状态
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ProcessStatus {
    /// 正在启动
    Starting,
    /// 正常运行中
    Running,
    /// 正常主动停止
    Stopped,
    /// 异常退出/崩溃
    Crashed {
        exit_code: Option<i32>,
        error_message: Option<String>,
    },
    /// 历史孤儿回收
    OrphanReclaimed,
}

/// 单个受管进程条目
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ManagedProcessEntry {
    /// 进程唯一逻辑标识（例如 "sidecar:backend", "session:abc-123"）
    pub id: String,
    /// 进程角色
    pub role: ProcessRole,
    /// 操作系统实际分配的 PID
    pub pid: Option<u32>,
    /// 当前生命周期状态
    pub status: ProcessStatus,
    /// 启动时间戳（毫秒）
    pub started_at: u64,
    /// 终止时间戳（毫秒）
    pub ended_at: Option<u64>,
    /// 退出码
    pub exit_code: Option<i32>,
    /// 错误日志/崩溃信息
    pub error_message: Option<String>,
    /// 自动重启次数
    pub restart_count: u32,
}

impl ManagedProcessEntry {
    pub fn new(id: impl Into<String>, role: ProcessRole, pid: Option<u32>) -> Self {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);

        Self {
            id: id.into(),
            role,
            pid,
            status: ProcessStatus::Running,
            started_at: now,
            ended_at: None,
            exit_code: None,
            error_message: None,
            restart_count: 0,
        }
    }
}
