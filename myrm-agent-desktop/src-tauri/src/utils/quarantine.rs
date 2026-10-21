use std::path::{Path, PathBuf};
use std::process::Command;

/// 检测指定路径是否存在 com.apple.quarantine 属性
pub fn has_quarantine_attribute(path: &Path) -> bool {
    #[cfg(target_os = "macos")]
    {
        if !path.exists() {
            return false;
        }

        let output = Command::new("xattr")
            .arg("-p")
            .arg("com.apple.quarantine")
            .arg(path)
            .output();

        if let Ok(output) = output {
            return output.status.success() && !output.stdout.is_empty();
        }
    }
    false
}

/// 尝试静默移除 com.apple.quarantine 属性
/// 返回 true 表示移除成功或本就不存在，false 表示移除失败（通常是因为权限不足）
pub fn remove_quarantine_attribute_silently(path: &Path) -> bool {
    #[cfg(target_os = "macos")]
    {
        if !has_quarantine_attribute(path) {
            return true;
        }

        let output = Command::new("xattr")
            .arg("-d")
            .arg("com.apple.quarantine")
            .arg(path)
            .output();

        if let Ok(output) = output {
            return output.status.success();
        }
        false
    }

    #[cfg(not(target_os = "macos"))]
    {
        true
    }
}

/// 获取当前应用的根目录 (xxx.app)
/// 如果不是在 .app 包内运行，则返回当前执行文件所在的目录
pub fn get_app_bundle_path() -> PathBuf {
    let exe_path = std::env::current_exe().unwrap_or_default();

    // 检查路径中是否包含 .app
    let path_str = exe_path.to_string_lossy();
    if let Some(app_index) = path_str.find(".app/") {
        let app_path_str = &path_str[0..app_index + 4];
        return PathBuf::from(app_path_str);
    }

    // 如果没有 .app，返回执行文件所在目录
    if let Some(parent) = exe_path.parent() {
        return parent.to_path_buf();
    }

    exe_path
}

/// 异步精准扫描并静默修复
/// 返回是否需要提权修复 (true = 有隔离属性且静默移除失败)
pub fn scan_and_silent_heal() -> bool {
    #[cfg(target_os = "macos")]
    {
        let app_path = get_app_bundle_path();

        // 1. 检查主程序包本身
        if has_quarantine_attribute(&app_path) && !remove_quarantine_attribute_silently(&app_path) {
            return true; // 静默失败，需要提权
        }

        // 2. 检查内部关键目录 (MacOS 和 Resources)
        // 注意：为了避免全盘扫描导致启动慢，我们只扫描 .app 根目录，
        // 提权修复时使用 xattr -cr 会递归修复所有内部文件。
        // 如果主程序包的隔离属性被移除，通常内部的也能被正常加载，
        // 除非某些 sidecar 被单独隔离。

        // 作为一个轻量级检测，如果主程序本身没有被隔离，我们假设它是安全的。
        // （如果用户通过右键打开，主程序的隔离属性会被系统记录为已批准，
        // 但 xattr -p 仍然能看到它。如果 xattr -d 失败，说明用户没有写权限，
        // 比如放在了 /Applications 下且不是管理员）。

        false
    }

    #[cfg(not(target_os = "macos"))]
    {
        false
    }
}
