//! Appshot 共享工具：时间戳、隐私黑名单、截图压缩、前台应用名。

use std::collections::HashSet;
use std::process::Command;
use tauri::{AppHandle, Manager};

use crate::config::ConfigManager;

/// 截图大小上限（1.5 MB）——超过时自动缩放，避免大图浪费 LLM token
pub(super) const MAX_SCREENSHOT_BYTES: usize = 1_500_000;

pub(crate) fn current_timestamp_ms() -> u128 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

pub(crate) fn load_excluded_apps(app: &AppHandle) -> HashSet<String> {
    let config_manager = app.state::<ConfigManager>();
    let config = config_manager.load();
    config
        .appshot_excluded_apps
        .into_iter()
        .map(|s| s.to_lowercase())
        .collect()
}

pub(crate) fn is_app_excluded(app_name: &str, excluded: &HashSet<String>) -> bool {
    if app_name.is_empty() || excluded.is_empty() {
        return false;
    }
    excluded.contains(&app_name.to_lowercase())
}

/// 将 JPEG 字节压缩到 MAX_SCREENSHOT_BYTES 以内（通过降低分辨率）
pub(super) fn ensure_screenshot_size_limit(buf: Vec<u8>) -> Vec<u8> {
    if buf.len() <= MAX_SCREENSHOT_BYTES {
        return buf;
    }
    let Ok(img) = image::load_from_memory(&buf) else {
        return buf;
    };
    let (w, h) = (img.width(), img.height());
    let ratio = (MAX_SCREENSHOT_BYTES as f64 / buf.len() as f64).sqrt();
    let new_w = ((w as f64 * ratio) as u32).max(320);
    let new_h = ((h as f64 * ratio) as u32).max(240);
    let resized = img.resize(new_w, new_h, image::imageops::FilterType::Triangle);
    let mut out = std::io::Cursor::new(Vec::new());
    if resized.write_to(&mut out, image::ImageFormat::Jpeg).is_ok() {
        let result = out.into_inner();
        if result.len() < buf.len() {
            return result;
        }
    }
    buf
}

pub(super) fn truncate_utf8(s: &str, max_bytes: usize) -> String {
    if s.len() <= max_bytes {
        return s.to_string();
    }
    let mut end = max_bytes;
    while end > 0 && !s.is_char_boundary(end) {
        end -= 1;
    }
    s[..end].to_string()
}

pub(crate) fn get_frontmost_app_name() -> String {
    #[cfg(target_os = "macos")]
    {
        if let Ok(output) = Command::new("osascript")
            .args(["-e", r#"tell application "System Events" to get name of first application process whose frontmost is true"#])
            .output()
        {
            if output.status.success() {
                return String::from_utf8_lossy(&output.stdout).trim().to_string();
            }
        }
        String::new()
    }
    #[cfg(target_os = "windows")]
    {
        super::capture_windows::get_foreground_app_name()
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        String::new()
    }
}
