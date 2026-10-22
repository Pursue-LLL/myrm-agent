//! 桌面端子进程遗孤回收
//!
//! [INPUT]
//! - tauri::AppHandle (POS: 应用句柄，用于定位应用数据目录)
//! - std::process::Command (POS: 读取进程存活时间)
//!
//! [OUTPUT]
//! - record_child: 记录本次拉起的子进程（pid / 角色 / 启动时间）
//! - reap_orphaned_children: 回收上一次运行遗留的孤儿子进程
//!
//! [POS]
//! 桌面端被强杀时，Next standalone 与 Python Sidecar 会被 reparent 到 init，继续占着端口，
//! 导致下一次启动直接失败（用户看到的是黑屏/启动面板而不是界面）。
//! 这里用「pid + 进程启动时间」双因子确认是同一个进程后才回收，避免误杀 pid 复用的无关进程。

use std::path::PathBuf;
use std::process::Command;

use tauri::{AppHandle, Manager};

use crate::utils::process_tree::kill_process_tree;

const RECORD_FILE: &str = "child-processes.txt";

fn record_path(app: &AppHandle) -> Option<PathBuf> {
    let dir = app.path().app_data_dir().ok()?;
    std::fs::create_dir_all(&dir).ok()?;
    Some(dir.join(RECORD_FILE))
}

/// 读取进程启动时间（ps 的 lstart），用于区分 pid 复用。
fn process_start_time(pid: u32) -> Option<String> {
    let output = Command::new(ps_binary()).args(["-p", &pid.to_string(), "-o", "lstart="]).output().ok()?;
    let text = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if text.is_empty() { None } else { Some(text) }
}

#[cfg(target_os = "macos")]
fn ps_binary() -> &'static str {
    "/bin/ps"
}

#[cfg(not(target_os = "macos"))]
fn ps_binary() -> &'static str {
    "ps"
}

/// 记录一个由本应用拉起的子进程。
pub fn record_child(app: &AppHandle, role: &str, pid: u32) {
    let Some(path) = record_path(app) else { return };
    let Some(start) = process_start_time(pid) else { return };
    let mut records = read_records(&path);
    records.retain(|(_, existing_role, _)| existing_role != role);
    records.push((pid, role.to_string(), start));
    let body: String = records
        .iter()
        .map(|(pid, role, start)| format!("{}\t{}\t{}", pid, role, start))
        .collect::<Vec<_>>()
        .join("\n");
    let _ = std::fs::write(&path, body);
}

/// 回收上一次运行遗留的孤儿子进程。
///
/// 只有当 pid 仍存在、且启动时间与记录一致、且父进程已是 init（说明原宿主已退出）时才回收。
pub fn reap_orphaned_children(app: &AppHandle) {
    let Some(path) = record_path(app) else { return };
    let records = read_records(&path);
    let _ = std::fs::remove_file(&path);
    for (pid, role, start) in records {
        let Some(current_start) = process_start_time(pid) else {
            continue; // 进程已退出
        };
        if current_start != start {
            continue; // pid 已被复用，属于无关进程
        }
        let parent = process_parent(pid);
        if parent != 1 {
            continue; // 仍有活着的宿主（例如同一台机器上的另一个实例）
        }
        println!("🧹 Reaping orphaned {} (PID: {}) from a previous run", role, pid);
        kill_process_tree(pid);
    }
}

fn process_parent(pid: u32) -> u32 {
    let output = Command::new(ps_binary()).args(["-p", &pid.to_string(), "-o", "ppid="]).output().ok();
    output
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().parse::<u32>().unwrap_or(0))
        .unwrap_or(0)
}

fn read_records(path: &PathBuf) -> Vec<(u32, String, String)> {
    let Ok(text) = std::fs::read_to_string(path) else { return Vec::new() };
    text.lines()
        .filter_map(|line| {
            let mut parts = line.split('\t');
            let pid = parts.next()?.parse::<u32>().ok()?;
            let role = parts.next()?.to_string();
            let start = parts.next()?.to_string();
            Some((pid, role, start))
        })
        .collect()
}
