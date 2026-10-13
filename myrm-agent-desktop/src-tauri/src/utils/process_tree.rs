//! 进程强杀原语
//!
//! [INPUT]
//! - 目标进程 PID
//!
//! [OUTPUT]
//! - kill_process_tree: Windows 用 `taskkill /T /F` 终止整棵子进程树；POSIX 只对该 PID 发 SIGKILL，不递归
//!
//! [POS]
//! 后端 / 前端停机兜底、重启与端口幸存者回收共用的强杀入口。
//! POSIX 下后代进程不会被一并终止，由后代自身的退出处理收尾；主进程崩溃时没有内核级联终止。

use std::process::Command;

/// 强杀指定 PID 的进程
///
/// Windows：`taskkill /PID <pid> /T /F`，递归终止整棵子进程树（防止 Chrome/Worker 孤儿残留）。
/// POSIX：只对该 PID 发送 `kill -9`，不递归、不设进程组，后代进程不会被一并终止。
pub fn kill_process_tree(pid: u32) {
    if pid == 0 {
        return;
    }

    #[cfg(target_os = "windows")]
    {
        // Windows 平台：调用 taskkill 递归终止整棵进程树
        let mut cmd = Command::new("taskkill");
        cmd.args(["/PID", &pid.to_string(), "/T", "/F"]);
        crate::runtime::suppress_console_window(&mut cmd);
        let _ = cmd.output();
    }

    #[cfg(not(target_os = "windows"))]
    {
        // POSIX 平台：仅强杀该 PID，不递归
        let _ = Command::new("kill").args(["-9", &pid.to_string()]).output();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kill_process_tree_zero_pid_is_noop() {
        kill_process_tree(0);
    }
}
