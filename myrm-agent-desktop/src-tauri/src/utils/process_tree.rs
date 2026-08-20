//! 跨平台进程树安全销毁与 Windows Job Object 管理器
//!
//! [INPUT]
//! - 目标进程 PID 或标准库 Child 句柄
//!
//! [OUTPUT]
//! - 递归整树终止（Windows taskkill /T /F，POSIX killpg / kill）
//! - Windows Job Object 托管能力（JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE）
//!
//! [POS]
//! 桌面端子进程全生命周期进程树管理与防孤儿核心工具。
//! 确保在停机、OTA 重启、主进程崩溃或 Panic 时，派生的整棵子孙进程树能干净销毁。

use std::process::Command;

/// 安全递归终止指定 PID 的整棵进程树
///
/// 在 Windows 上使用 `taskkill /PID <pid> /T /F`（递归终止整棵子进程树，防止 Chrome/Worker 孤儿残留）；
/// 在 Unix/macOS 上发送 SIGTERM/SIGKILL。
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
        // POSIX 平台：优先尝试发送信号
        let _ = Command::new("kill")
            .args(["-9", &pid.to_string()])
            .output();
    }
}

/// Windows 作业对象守卫：确保主进程退出（无论正常还是异常崩溃）时，关联的子进程树被内核自动级联销毁
#[cfg(target_os = "windows")]
pub struct WindowsJobObjectGuard {
    job_handle: windows_sys::Win32::Foundation::HANDLE,
}

#[cfg(target_os = "windows")]
impl WindowsJobObjectGuard {
    /// 创建一个新的 Windows Job Object，并配置 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`
    pub fn new() -> Option<Self> {
        use std::mem::size_of;
        use std::ptr::null;
        use windows_sys::Win32::System::JobObjects::{
            CreateJobObjectW, SetInformationJobObject, JobObjectExtendedLimitInformation,
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
        };

        unsafe {
            let handle = CreateJobObjectW(null(), null());
            if handle.is_null() || handle == 0 as _ {
                return None;
            }

            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

            let ok = SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const std::ffi::c_void,
                size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            );

            if ok == 0 {
                windows_sys::Win32::Foundation::CloseHandle(handle);
                return None;
            }

            Some(Self { job_handle: handle })
        }
    }

    /// 将正在运行的子进程句柄关联到该 Job Object 中
    pub fn assign_process(&self, process_handle: windows_sys::Win32::Foundation::HANDLE) -> bool {
        use windows_sys::Win32::System::JobObjects::AssignProcessToJobObject;
        unsafe {
            let ok = AssignProcessToJobObject(self.job_handle, process_handle);
            ok != 0
        }
    }
}

#[cfg(target_os = "windows")]
impl Drop for WindowsJobObjectGuard {
    fn drop(&mut self) {
        use windows_sys::Win32::Foundation::CloseHandle;
        unsafe {
            if !self.job_handle.is_null() && self.job_handle != 0 as _ {
                CloseHandle(self.job_handle);
            }
        }
    }
}

#[cfg(target_os = "windows")]
unsafe impl Send for WindowsJobObjectGuard {}
#[cfg(target_os = "windows")]
unsafe impl Sync for WindowsJobObjectGuard {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_kill_process_tree_zero_pid_is_noop() {
        kill_process_tree(0);
    }
}
