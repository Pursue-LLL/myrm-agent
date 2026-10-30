//! 随包 Sidecar 可执行文件的定位
//!
//! [INPUT]
//! - Tauri 资源目录中的 `binaries/myrmagent-backend/`（`tauri.conf.json#bundle.resources` 映射，
//!   内容是 `sidecar/build.py` 产出的 PyInstaller `--onedir` 目录树）
//! - Linux 例外：同一目录树由 `tauri.linux.conf.json#bundle.linux.appimage.files` 放进
//!   `<prefix>/share/<product>/`，不在资源目录 `<prefix>/lib/<product>/` 下
//!
//! [OUTPUT]
//! - `bundled_executable`: release 下 Python 后端入口可执行文件的绝对路径；缺失或为空时返回带构建指引的错误
//!
//! [POS]
//! 随包 sidecar 布局在 Rust 侧的唯一定义点。常量须与 `sidecar/build.py` 的产物布局、`tauri.conf.json` /
//! `tauri.linux.conf.json` 的映射保持一致，由 `tests/architecture/test_desktop_sidecar_layout.py` 守住。

use std::path::{Path, PathBuf};

use tauri::{AppHandle, Manager};

/// 承载 PyInstaller 目录树的子目录（相对资源目录；Linux 下相对 `<prefix>/share/<product>`）。
const RESOURCE_DIR: &str = "binaries/myrmagent-backend";

/// Linux 安装前缀下承载目录树的目录名。
///
/// AppImage 打包时 linuxdeploy 会对 `<prefix>/lib` 下每个 ELF 文件解析依赖并改写 RPATH；PyInstaller
/// 目录树自带全部依赖库，被解析必然失败、即便解析成功也会被改写，所以目录树放在它不扫描的 `share`。
const LINUX_SHARE_DIR: &str = "share";

/// 目录树里的入口可执行文件（PyInstaller 以构建名命名入口）。
const EXECUTABLE_NAME: &str = if cfg!(windows) {
    "myrmagent-backend.exe"
} else {
    "myrmagent-backend"
};

/// 解析 release 构建里随包 sidecar 的可执行文件路径。
pub fn bundled_executable(app: &AppHandle) -> Result<PathBuf, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("Failed to resolve sidecar path: {e}"))?;
    let dir = sidecar_dir(&resource_dir)
        .ok_or_else(|| format!("Unexpected resource directory layout: {resource_dir:?}"))?;
    executable_in(&dir)
}

/// 目录树所在目录，由 Tauri 资源目录推出。
fn sidecar_dir(resource_dir: &Path) -> Option<PathBuf> {
    if !cfg!(target_os = "linux") {
        return Some(resource_dir.join(RESOURCE_DIR));
    }
    // Linux 的资源目录恒为 `<prefix>/lib/<product>`；目录树与它同属一个前缀、同名子目录，只换 `lib` 为 `share`。
    let product = resource_dir.file_name()?;
    let prefix = resource_dir.parent()?.parent()?;
    Some(
        prefix
            .join(LINUX_SHARE_DIR)
            .join(product)
            .join(RESOURCE_DIR),
    )
}

fn executable_in(dir: &Path) -> Result<PathBuf, String> {
    let executable = dir.join(EXECUTABLE_NAME);
    // 0 字节文件是占位产物（git 占位 / CI stub），不是可运行的 sidecar。
    match std::fs::metadata(&executable) {
        Ok(meta) if meta.is_file() && meta.len() > 0 => Ok(executable),
        _ => Err(format!(
            "Backend sidecar is missing or empty at {executable:?}. \
             Build it with: python myrm-agent-desktop/sidecar/build.py"
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_a_non_empty_executable_inside_the_tree() {
        let dir = tempfile::tempdir().expect("create temp dir");
        let executable = dir.path().join(EXECUTABLE_NAME);
        std::fs::write(&executable, b"sidecar").expect("write executable");

        assert_eq!(executable_in(dir.path()), Ok(executable));
    }

    #[test]
    fn rejects_a_missing_executable() {
        let dir = tempfile::tempdir().expect("create temp dir");

        let err = executable_in(dir.path()).expect_err("empty tree has no executable");
        assert!(err.contains("missing or empty"), "unexpected error: {err}");
        assert!(
            err.contains("sidecar/build.py"),
            "error must say how to build: {err}"
        );
    }

    #[test]
    fn rejects_a_zero_byte_placeholder() {
        let dir = tempfile::tempdir().expect("create temp dir");
        std::fs::write(dir.path().join(EXECUTABLE_NAME), b"").expect("write placeholder");

        assert!(executable_in(dir.path()).is_err());
    }

    #[test]
    fn places_the_tree_by_platform_relative_to_the_resource_dir() {
        let resource_dir = Path::new("/tmp/.mount_app/usr/lib/MyrmAgent");
        // AppImage: the tree sits in `share`, where linuxdeploy does not rewrite it.
        let expected = if cfg!(target_os = "linux") {
            "/tmp/.mount_app/usr/share/MyrmAgent/binaries/myrmagent-backend"
        } else {
            "/tmp/.mount_app/usr/lib/MyrmAgent/binaries/myrmagent-backend"
        };

        assert_eq!(sidecar_dir(resource_dir), Some(PathBuf::from(expected)));
    }

    #[test]
    fn linux_rejects_a_resource_dir_without_an_install_prefix() {
        if cfg!(target_os = "linux") {
            assert_eq!(sidecar_dir(Path::new("/MyrmAgent")), None);
        }
    }

    #[test]
    fn rejects_a_directory_named_like_the_executable() {
        let dir = tempfile::tempdir().expect("create temp dir");
        std::fs::create_dir(dir.path().join(EXECUTABLE_NAME)).expect("create directory");

        assert!(executable_in(dir.path()).is_err());
    }
}
