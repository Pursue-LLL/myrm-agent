//! 随包 Node.js 运行时的定位
//!
//! [INPUT]
//! - 主程序可执行文件所在目录：Tauri 把 `tauri.conf.json#bundle.externalBin` 的
//!   `binaries/myrm-node-<目标三元组>` 去掉三元组后放在这里（macOS `Contents/MacOS/`、Windows 安装目录、
//!   AppImage `usr/bin/`、开发构建 `target/<profile>/`）
//!
//! [OUTPUT]
//! - `bundled_node`: Next standalone 服务使用的 Node 可执行文件绝对路径；缺失或为空时返回带取包指引的错误
//!
//! [POS]
//! 前端运行时在 Rust 侧的唯一定位点。文件名须与 `scripts/fetch_node_runtime.py` 的 `SIDECAR_NAME`、
//! `tauri.conf.json#bundle.externalBin` 保持一致，由 `tests/architecture/test_desktop_node_runtime.py` 守住。
//! 不回退到 PATH 里的 `node`：从 Finder / 开始菜单启动的应用拿不到用户 shell 的 PATH（macOS 只有
//! `/usr/bin:/bin:/usr/sbin:/sbin`），回退只会让缺包问题到用户机器上才暴露。

use std::path::{Path, PathBuf};

use super::is_non_empty_file;

/// `bundle.externalBin` 条目 `binaries/myrm-node` 落地后的文件名。
const EXECUTABLE_NAME: &str = if cfg!(windows) {
    "myrm-node.exe"
} else {
    "myrm-node"
};

/// 解析随包 Node 运行时的绝对路径。
pub fn bundled_node() -> Result<PathBuf, String> {
    let app_exe = std::env::current_exe()
        .map_err(|e| format!("Failed to resolve the application path: {e}"))?;
    let dir = app_exe
        .parent()
        .ok_or_else(|| format!("Application path has no parent directory: {app_exe:?}"))?;
    executable_in(dir)
}

fn executable_in(dir: &Path) -> Result<PathBuf, String> {
    let executable = dir.join(EXECUTABLE_NAME);
    if is_non_empty_file(&executable) {
        Ok(executable)
    } else {
        Err(format!(
            "Bundled Node.js runtime is missing or empty at {executable:?}. \
             Fetch it with: python myrm-agent-desktop/scripts/fetch_node_runtime.py"
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_a_non_empty_executable_next_to_the_app() {
        let dir = tempfile::tempdir().expect("create temp dir");
        let executable = dir.path().join(EXECUTABLE_NAME);
        std::fs::write(&executable, b"node").expect("write executable");

        assert_eq!(executable_in(dir.path()), Ok(executable));
    }

    #[test]
    fn rejects_a_missing_executable_and_says_how_to_fetch_it() {
        let dir = tempfile::tempdir().expect("create temp dir");

        let err = executable_in(dir.path()).expect_err("empty directory has no runtime");
        assert!(err.contains("missing or empty"), "unexpected error: {err}");
        assert!(
            err.contains("fetch_node_runtime.py"),
            "error must say how to fetch it: {err}"
        );
    }

    #[test]
    fn rejects_a_zero_byte_placeholder() {
        let dir = tempfile::tempdir().expect("create temp dir");
        std::fs::write(dir.path().join(EXECUTABLE_NAME), b"").expect("write placeholder");

        assert!(executable_in(dir.path()).is_err());
    }

    #[test]
    fn rejects_a_directory_named_like_the_executable() {
        let dir = tempfile::tempdir().expect("create temp dir");
        std::fs::create_dir(dir.path().join(EXECUTABLE_NAME)).expect("create directory");

        assert!(executable_in(dir.path()).is_err());
    }
}
