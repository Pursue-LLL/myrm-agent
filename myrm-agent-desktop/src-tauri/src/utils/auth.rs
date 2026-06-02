use std::path::PathBuf;
use std::process::Command;

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

/// 使用 osascript 弹出 macOS 原生提权密码框执行 xattr -cr
/// 返回 true 表示提权执行成功，false 表示失败（如用户取消输入密码）
pub fn fix_quarantine_with_auth() -> Result<bool, String> {
    #[cfg(target_os = "macos")]
    {
        let app_path = get_app_bundle_path();
        
        if !app_path.exists() {
            return Err("应用路径不存在，无法执行修复".to_string());
        }
        
        let path_str = app_path.to_string_lossy();
        
        // 构造 osascript 命令
        // do shell script "xattr -cr '/Applications/MyrmAgent.app'" with administrator privileges
        let script = format!(
            "do shell script \"xattr -cr '{}'\" with administrator privileges",
            path_str
        );
        
        let output = Command::new("osascript")
            .arg("-e")
            .arg(&script)
            .output()
            .map_err(|e| format!("执行 osascript 失败: {}", e))?;
            
        if output.status.success() {
            Ok(true)
        } else {
            let stderr = String::from_utf8_lossy(&output.stderr);
            Err(format!("提权修复失败: {}", stderr))
        }
    }
    
    #[cfg(not(target_os = "macos"))]
    {
        Ok(true)
    }
}
