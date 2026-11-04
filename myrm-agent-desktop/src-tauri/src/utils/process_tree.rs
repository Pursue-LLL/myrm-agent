//! 进程强杀原语
//!
//! [INPUT]
//! - 目标进程 PID
//! - runtime::suppress_console_window (POS: Windows 下为子进程设置 CREATE_NO_WINDOW，防止弹出控制台窗口)
//! - `ps -axo pid=,ppid=` (POS: POSIX 下读取父子关系，找出此刻仍挂在目标名下的后代)
//!
//! [OUTPUT]
//! - kill_process_tree: 强杀目标进程及此刻仍挂在它名下的后代；Windows 用 `taskkill /T /F`，POSIX 先快照后代再一次 SIGKILL
//! - ps_binary: 当前平台的 `ps` 可执行文件路径，读取进程信息的模块共用
//!
//! [POS]
//! 后端 / 前端停机兜底、重启与端口幸存者回收共用的强杀入口。
//! POSIX 的后代在发信号前一次性快照：目标一死，它的子进程就被 reparent 到 init，之后再也沿父子关系找不到。
//! 目标之前就已 reparent 的进程不在其内。两个平台都没有 Job Object，主进程崩溃时不会内核级联终止子进程。

use std::process::Command;

#[cfg(target_os = "macos")]
pub(crate) fn ps_binary() -> &'static str {
    "/bin/ps"
}

#[cfg(not(target_os = "macos"))]
pub(crate) fn ps_binary() -> &'static str {
    "ps"
}

/// 强杀指定 PID 的进程及此刻仍挂在它名下的后代
///
/// Windows：`taskkill /PID <pid> /T /F`，递归终止整棵子进程树（防止 Chrome/Worker 孤儿残留）。
/// POSIX：先读取进程表得到此刻仍挂在 `pid` 名下的后代，再对它们和 `pid` 一并发送 `kill -9`。
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
        let victims = process_and_descendants(pid, &process_table());
        let _ = Command::new("kill")
            .arg("-9")
            .args(victims.iter().map(u32::to_string))
            .output();
    }
}

/// 当前进程表的 `(pid, ppid)` 列表；读取失败时为空，此时只会强杀目标本身。
#[cfg(not(target_os = "windows"))]
fn process_table() -> Vec<(u32, u32)> {
    Command::new(ps_binary())
        .args(["-axo", "pid=,ppid="])
        .output()
        .map(|output| parse_process_table(&String::from_utf8_lossy(&output.stdout)))
        .unwrap_or_default()
}

#[cfg(not(target_os = "windows"))]
fn parse_process_table(listing: &str) -> Vec<(u32, u32)> {
    listing
        .lines()
        .filter_map(|line| {
            let mut fields = line.split_whitespace();
            let pid = fields.next()?.parse().ok()?;
            let ppid = fields.next()?.parse().ok()?;
            Some((pid, ppid))
        })
        .collect()
}

/// `root` 与沿父子关系可达的全部后代，`root` 在最前。
#[cfg(not(target_os = "windows"))]
fn process_and_descendants(root: u32, table: &[(u32, u32)]) -> Vec<u32> {
    let mut found = vec![root];
    let mut next = 0;
    while next < found.len() {
        let parent = found[next];
        next += 1;
        for &(pid, ppid) in table {
            if ppid == parent && !found.contains(&pid) {
                found.push(pid);
            }
        }
    }
    found
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(unix)]
    use std::time::{Duration, Instant};

    #[test]
    fn test_kill_process_tree_zero_pid_is_noop() {
        kill_process_tree(0);
    }

    #[cfg(not(target_os = "windows"))]
    #[test]
    fn parse_process_table_skips_malformed_rows() {
        let table = parse_process_table("  1     0\n 42     1\nbogus\n  7\n 99    42\n");
        assert_eq!(table, vec![(1, 0), (42, 1), (99, 42)]);
    }

    #[cfg(not(target_os = "windows"))]
    #[test]
    fn process_and_descendants_follow_the_whole_chain_and_nothing_else() {
        let table = [(10, 1), (11, 10), (12, 11), (13, 10), (20, 1), (21, 20)];
        let found = process_and_descendants(10, &table);
        assert_eq!(found[0], 10);
        let mut sorted = found;
        sorted.sort_unstable();
        assert_eq!(sorted, vec![10, 11, 12, 13]);
    }

    /// A process that is gone or only waiting to be reaped (a zombie still answers `kill -0`).
    #[cfg(unix)]
    fn is_running(pid: u32) -> bool {
        Command::new(ps_binary())
            .args(["-o", "stat=", "-p", &pid.to_string()])
            .output()
            .map(|output| {
                let stat = String::from_utf8_lossy(&output.stdout);
                let stat = stat.trim();
                !stat.is_empty() && !stat.starts_with('Z')
            })
            .unwrap_or(false)
    }

    #[cfg(unix)]
    #[test]
    fn kill_process_tree_takes_the_descendants_with_the_root() {
        let mut root = Command::new("sh")
            .args(["-c", "sleep 60 & sleep 60 & wait"])
            .spawn()
            .expect("spawn sh");
        let root_pid = root.id();

        let deadline = Instant::now() + Duration::from_secs(5);
        let sleepers = loop {
            let mut found = process_and_descendants(root_pid, &process_table());
            if found.len() >= 3 || Instant::now() > deadline {
                break found.split_off(1);
            }
            std::thread::sleep(Duration::from_millis(20));
        };
        assert_eq!(
            sleepers.len(),
            2,
            "the shell should have started two sleepers"
        );

        kill_process_tree(root_pid);
        let _ = root.wait();

        let deadline = Instant::now() + Duration::from_secs(5);
        while sleepers.iter().any(|pid| is_running(*pid)) && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(20));
        }
        for pid in sleepers {
            assert!(
                !is_running(pid),
                "descendant {pid} survived kill_process_tree"
            );
        }
    }
}
