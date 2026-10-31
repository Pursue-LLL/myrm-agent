//! 随包 Sidecar 的启动位置：可执行文件与工作目录
//!
//! [INPUT]
//! - Tauri 资源目录中的 `binaries/myrmagent-backend/`（`tauri.conf.json#bundle.resources` 映射，
//!   内容是 `sidecar/build.py` 产出的 PyInstaller `--onedir` 目录树）
//! - Linux 例外：同一目录树由 `tauri.linux.conf.json#bundle.linux.appimage.files` 放进
//!   `<prefix>/share/<product>/`，不在资源目录 `<prefix>/lib/<product>/` 下
//! - Tauri 应用本地数据目录（工作目录的父目录）
//!
//! [OUTPUT]
//! - `bundled_executable`: release 下 Python 后端入口可执行文件的绝对路径；缺失或为空时返回带构建指引的错误
//! - `sidecar_workdir`: release 下 Python 后端的工作目录（归应用所有、可写、跨启动稳定），必要时创建
//!
//! [POS]
//! 随包 sidecar 布局在 Rust 侧的唯一定义点。常量须与 `sidecar/build.py` 的产物布局、`tauri.conf.json` /
//! `tauri.linux.conf.json` 的映射保持一致，由 `tests/architecture/test_desktop_sidecar_layout.py` 守住。

use std::path::{Path, PathBuf};

use tauri::{AppHandle, Manager};

use super::is_non_empty_file;

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

/// 后端工作目录在应用本地数据目录下的目录名。
const WORKDIR_NAME: &str = "backend";

/// 解析 release 构建里随包 sidecar 的可执行文件路径。
pub fn bundled_executable(app: &AppHandle) -> Result<PathBuf, String> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| format!("Failed to resolve sidecar path: {e}"))?;
    let dir = sidecar_dir(&resource_dir)
        .ok_or_else(|| format!("Unexpected resource directory layout: {resource_dir:?}"))?;
    let executable = executable_in(&dir)?;
    // sidecar 在自己的工作目录里启动，相对的程序路径会因此指向别处。
    std::path::absolute(&executable)
        .map_err(|e| format!("Failed to resolve sidecar path {executable:?}: {e}"))
}

/// 解析 release 下 sidecar 的工作目录并确保它存在。
///
/// 后端把一批状态目录默认放在进程工作目录的 `.myrm/` 下（子 Agent 检查点在导入期就会创建），工作目录因此必须
/// 可写。外壳不指定时它取决于启动方式：macOS 从 Finder 启动为只读的 `/`，Linux AppImage 的 AppRun 先切进只读
/// 挂载的 `usr`，两者都让后端在导入期退出；Windows 为安装目录，用户状态会落进程序目录。
///
/// 目录放在应用本地数据目录（不漫游）下，与用户主目录和工作区分开：后端按工作目录回退出的工作区根因此是这个
/// 应用私有目录，而不是用户的主目录。
pub fn sidecar_workdir(app: &AppHandle) -> Result<PathBuf, String> {
    let base = app
        .path()
        .app_local_data_dir()
        .map_err(|e| format!("Failed to resolve the backend working directory: {e}"))?;
    prepare_workdir(&base)
}

fn prepare_workdir(base: &Path) -> Result<PathBuf, String> {
    let dir = base.join(WORKDIR_NAME);
    std::fs::create_dir_all(&dir)
        .map_err(|e| format!("Failed to create the backend working directory {dir:?}: {e}"))?;
    Ok(dir)
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
    if is_non_empty_file(&executable) {
        Ok(executable)
    } else {
        Err(format!(
            "Backend sidecar is missing or empty at {executable:?}. \
             Build it with: python myrm-agent-desktop/sidecar/build.py"
        ))
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

    #[test]
    fn creates_the_workdir_under_the_base_and_keeps_its_state_across_launches() {
        let base = tempfile::tempdir().expect("create temp dir");

        let first = prepare_workdir(base.path()).expect("create workdir");
        assert_eq!(first, base.path().join(WORKDIR_NAME));
        assert!(first.is_dir());

        std::fs::create_dir(first.join(".myrm")).expect("write backend state");
        let second = prepare_workdir(base.path()).expect("reuse workdir");
        assert_eq!(second, first);
        assert!(
            second.join(".myrm").is_dir(),
            "state of an earlier launch must survive"
        );
    }

    #[test]
    fn a_workdir_that_cannot_be_created_is_reported_with_its_path() {
        let base = tempfile::tempdir().expect("create temp dir");
        let blocker = base.path().join("blocker");
        std::fs::write(&blocker, b"a file").expect("write blocker");

        let err = prepare_workdir(&blocker).expect_err("a file cannot hold a directory");
        assert!(
            err.contains("backend working directory") && err.contains("blocker"),
            "unexpected error: {err}"
        );
    }
}
