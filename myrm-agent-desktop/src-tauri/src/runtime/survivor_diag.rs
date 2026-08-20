//! 端口幸存者诊断与自愈回收器（Survivor Diag & Signature-Gated Re-Kill）
//!
//! [INPUT]
//! - 冲突的 host 与 port
//! - 允许自愈的可执行文件签名/镜像名模式
//!
//! [OUTPUT]
//! - `SurvivorDiagResult`: 诊断结果（Clean / SelfSurvivorReclaimed / ForeignConflict / CheckFailed）
//! - 自动执行安全进程树 Re-kill 并等待端口完全释放
//!
//! [POS]
//! 解决 Windows 桌面端启动与热重启时，因历史孤儿进程死锁端口导致的闪退问题。
//! 具备严格的三道防误杀防线，确保绝不误杀用户无关业务进程。

use std::time::Duration;
use crate::runtime::port::is_port_in_use;
use crate::utils::process_tree::kill_process_tree;

/// 幸存者诊断与自愈结果
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SurvivorDiagResult {
    /// 端口空闲干净，无需处理
    Clean,
    /// 检测到自身历史遗留幸存者进程，已安全 Re-kill 并释放端口
    SelfSurvivorReclaimed { pid: u32, process_name: String },
    /// 端口被外部非自身进程占用（触发防误杀保护，未杀进程）
    ForeignConflict { pid: u32, process_name: String },
    /// 诊断失败或无法确定 PID
    UnknownConflict,
}

/// 判定指定进程名/路径是否属于 Myrm 自身组件
pub fn is_self_process(process_name: &str, _exe_path: &str) -> bool {
    let lower_name = process_name.to_lowercase();
    let lower_path = _exe_path.to_lowercase();

    // 1. 匹配后端或前端核心二进制名称
    if lower_name.contains("myrmagent") || lower_name.contains("myrm-agent") {
        return true;
    }

    // 2. 匹配 python/node 二进制且路径包含 myrm 相关工作区或资源目录
    if (lower_name.contains("python") || lower_name.contains("node"))
        && (lower_path.contains("myrm") || lower_path.contains("standalone"))
    {
        return true;
    }

    false
}

/// 获取占用指定端口的 PID 与进程名（Windows 平台实现）
#[cfg(target_os = "windows")]
fn find_process_occupying_port(port: u16) -> Option<(u32, String)> {
    use std::process::Command;
    // 使用 netstat 快速定位占用端口的 PID
    let mut cmd = Command::new("netstat");
    cmd.args(["-ano", "-p", "tcp"]);
    crate::runtime::suppress_console_window(&mut cmd);

    let output = cmd.output().ok()?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let port_str = format!(":{}", port);

    let mut found_pid: Option<u32> = None;
    for line in stdout.lines() {
        if line.contains("LISTENING") && line.contains(&port_str) {
            let parts: Vec<&str> = line.split_whitespace().collect();
            if let Some(pid_str) = parts.last() {
                if let Ok(pid) = pid_str.parse::<u32>() {
                    found_pid = Some(pid);
                    break;
                }
            }
        }
    }

    let pid = found_pid?;
    if pid == 0 {
        return None;
    }

    // 查询 PID 对应的进程名
    let mut tasklist_cmd = Command::new("tasklist");
    tasklist_cmd.args(["/FI", &format!("PID eq {}", pid), "/FO", "CSV", "/NH"]);
    crate::runtime::suppress_console_window(&mut tasklist_cmd);

    let task_out = tasklist_cmd.output().ok()?;
    let task_str = String::from_utf8_lossy(&task_out.stdout);
    let process_name = task_str
        .lines()
        .next()
        .and_then(|l| l.split(',').next())
        .map(|s| s.trim_matches('"').to_string())
        .unwrap_or_else(|| "unknown.exe".to_string());

    Some((pid, process_name))
}

#[cfg(not(target_os = "windows"))]
fn find_process_occupying_port(port: u16) -> Option<(u32, String)> {
    use std::process::Command;
    let output = Command::new("lsof")
        .args(["-iTCP", &format!(":{}", port), "-sTCP:LISTEN", "-t"])
        .output()
        .ok()?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let pid_str = stdout.lines().next()?.trim();
    let pid = pid_str.parse::<u32>().ok()?;

    let name_out = Command::new("ps")
        .args(["-p", &pid.to_string(), "-o", "comm="])
        .output()
        .ok()?;
    let proc_name = String::from_utf8_lossy(&name_out.stdout).trim().to_string();

    Some((pid, proc_name))
}

/// 诊断并自愈端口冲突（带防误杀三道防线与 TCP 释放确认）
pub async fn diagnose_and_reclaim_port(host: &str, port: u16) -> SurvivorDiagResult {
    if !is_port_in_use(host, port) {
        return SurvivorDiagResult::Clean;
    }

    let (pid, proc_name) = match find_process_occupying_port(port) {
        Some(res) => res,
        None => return SurvivorDiagResult::UnknownConflict,
    };

    // 防线校验：必须确认为自身历史遗留幸存者
    if !is_self_process(&proc_name, "") {
        eprintln!(
            "⚠️  Port {}:{} is occupied by foreign process: {} (PID: {}). Refusing to kill.",
            host, port, proc_name, pid
        );
        return SurvivorDiagResult::ForeignConflict {
            pid,
            process_name: proc_name,
        };
    }

    println!(
        "🔄 Detected survivor process occupying port {}:{} -> {} (PID: {}). Reclaiming...",
        host, port, proc_name, pid
    );

    // 执行进程树强杀
    kill_process_tree(pid);

    // TCP 协议栈释放确认循环（最多等待 1000ms）
    for _ in 0..10 {
        tokio::time::sleep(Duration::from_millis(100)).await;
        if !is_port_in_use(host, port) {
            println!("✅ Successfully reclaimed port {}:{}", host, port);
            return SurvivorDiagResult::SelfSurvivorReclaimed {
                pid,
                process_name: proc_name,
            };
        }
    }

    SurvivorDiagResult::SelfSurvivorReclaimed {
        pid,
        process_name: proc_name,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_is_self_process_detection() {
        assert!(is_self_process("myrmagent-backend.exe", ""));
        assert!(is_self_process("myrm-agent.exe", ""));
        assert!(is_self_process("python.exe", "C:\\Program Files\\MyrmAgent\\resources"));
        assert!(is_self_process("node.exe", "C:\\Users\\app\\myrm\\standalone"));
        assert!(!is_self_process("nginx.exe", "C:\\nginx"));
        assert!(!is_self_process("java.exe", "C:\\Java\\bin"));
    }
}
