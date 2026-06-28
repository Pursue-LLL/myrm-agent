//! 全局快捷键处理中心：Appshot 截屏 + Voice PTT + 窗口切换
//!
//! [INPUT]
//! - ConfigManager (POS: 配置管理，提供 appshot_excluded_apps 隐私黑名单)
//! - Tauri AppHandle (用于 emit IPC 事件和窗口管理)
//! - OS 层：macOS screencapture + AX API / Windows PrintWindow + UI Automation
//!
//! [OUTPUT]
//! - IPC 事件: `appshot-captured` (screenshot_b64, windowTitle, extractedText, needsPermission, timestamp)
//! - IPC 事件: `appshot-blocked` (blockedApp, timestamp)
//! - IPC 事件: `voice-ptt-start` / `voice-ptt-stop`
//!
//! [POS]
//! 全局快捷键处理的唯一入口。负责 Appshot 跨平台截屏（macOS + Windows）、
//! 隐私黑名单拦截、Voice PTT 事件转发、主窗口 toggle。

use std::collections::HashSet;
use std::process::Command;
use tauri::{AppHandle, Emitter, Manager};

use crate::config::ConfigManager;

/// 截图大小上限（1.5 MB）——超过时自动缩放，避免大图浪费 LLM token
const MAX_SCREENSHOT_BYTES: usize = 1_500_000;

/// 用于在全局快捷键 handler 中识别 Appshot 绑定
pub static APPSHOT_SHORTCUT_STR: std::sync::Mutex<String> = std::sync::Mutex::new(String::new());

/// 用于在全局快捷键 handler 中识别 Voice PTT 绑定
pub static VOICE_PTT_SHORTCUT_STR: std::sync::Mutex<String> = std::sync::Mutex::new(String::new());

/// Voice PTT 快捷键按下：通知前端开始录音
pub fn handle_voice_ptt_start(app: &AppHandle) {
    let _ = app.emit("voice-ptt-start", ());
}

/// Voice PTT 快捷键松开：通知前端停止录音并发送
pub fn handle_voice_ptt_stop(app: &AppHandle) {
    let _ = app.emit("voice-ptt-stop", ());
}

/// 切换主窗口显示/隐藏
pub fn handle_toggle_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        if window.is_minimized().unwrap_or(false) {
            let _ = window.unminimize();
            let _ = window.set_focus();
        } else if window.is_visible().unwrap_or(false) {
            let _ = window.hide();
            #[cfg(target_os = "macos")]
            {
                let _ = app.set_activation_policy(tauri::ActivationPolicy::Accessory);
            }
        } else {
            #[cfg(target_os = "macos")]
            {
                let _ = app.set_activation_policy(tauri::ActivationPolicy::Regular);
            }
            let _ = window.show();
            let _ = window.set_focus();
        }
    }
}

/// 截屏入口：检查隐私黑名单后执行截屏
pub fn handle_appshot_shortcut(app: &AppHandle) {
    let excluded_apps = load_excluded_apps(app);
    let app_handle = app.clone();

    std::thread::spawn(move || {
        let front_app_name = get_frontmost_app_name();

        if is_app_excluded(&front_app_name, &excluded_apps) {
            let timestamp = current_timestamp_ms();
            let payload = serde_json::json!({
                "blockedApp": front_app_name,
                "timestamp": timestamp,
            });
            let _ = app_handle.emit("appshot-blocked", payload);
            show_main_window(&app_handle);
            return;
        }

        do_capture_and_emit(&app_handle);
    });
}

/// 绕过黑名单强制截屏（用户点击 "Continue Anyway" 后调用）
pub fn force_capture(app: &AppHandle) {
    let app_handle = app.clone();
    std::thread::spawn(move || {
        do_capture_and_emit(&app_handle);
    });
}

fn do_capture_and_emit(app: &AppHandle) {
    let timestamp = current_timestamp_ms();

    #[cfg(target_os = "macos")]
    let (screenshot_b64, window_title, extracted_text, needs_permission) = capture_appshot_macos();

    #[cfg(target_os = "windows")]
    let (screenshot_b64, window_title, extracted_text, needs_permission) =
        capture_appshot_windows();

    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    let (screenshot_b64, window_title, extracted_text, needs_permission) =
        (String::new(), String::new(), String::new(), false);

    let payload = serde_json::json!({
        "screenshot": screenshot_b64,
        "windowTitle": window_title,
        "extractedText": extracted_text,
        "needsPermission": needs_permission,
        "timestamp": timestamp,
    });

    if let Err(e) = app.emit("appshot-captured", payload) {
        eprintln!("Failed to emit appshot event: {}", e);
    }

    show_main_window(app);
}

fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        #[cfg(target_os = "macos")]
        {
            let _ = app.set_activation_policy(tauri::ActivationPolicy::Regular);
        }
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn current_timestamp_ms() -> u128 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

fn load_excluded_apps(app: &AppHandle) -> HashSet<String> {
    let config_manager = app.state::<ConfigManager>();
    let config = config_manager.load();
    config
        .appshot_excluded_apps
        .into_iter()
        .map(|s| s.to_lowercase())
        .collect()
}

fn is_app_excluded(app_name: &str, excluded: &HashSet<String>) -> bool {
    if app_name.is_empty() || excluded.is_empty() {
        return false;
    }
    excluded.contains(&app_name.to_lowercase())
}

/// 将 JPEG 字节压缩到 MAX_SCREENSHOT_BYTES 以内（通过降低分辨率）
fn ensure_screenshot_size_limit(buf: Vec<u8>) -> Vec<u8> {
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

fn get_frontmost_app_name() -> String {
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
        win::get_foreground_app_name()
    }
    #[cfg(not(any(target_os = "macos", target_os = "windows")))]
    {
        String::new()
    }
}

#[cfg(target_os = "macos")]
fn capture_appshot_macos() -> (String, String, String, bool) {
    use base64::Engine;
    use std::io::Read;

    let mut screenshot_b64 = String::new();
    let tmp_path = std::env::temp_dir().join(format!("appshot_{}.jpg", std::process::id()));

    if let Ok(output) = Command::new("screencapture")
        .args([
            "-x",
            "-C",
            "-t",
            "jpg",
            tmp_path.to_str().unwrap_or("/tmp/appshot.jpg"),
        ])
        .output()
    {
        if output.status.success() {
            if let Ok(mut f) = std::fs::File::open(&tmp_path) {
                let mut buf = Vec::new();
                if f.read_to_end(&mut buf).is_ok() {
                    let buf = ensure_screenshot_size_limit(buf);
                    screenshot_b64 = base64::engine::general_purpose::STANDARD.encode(&buf);
                }
            }
        }
    }
    let _ = std::fs::remove_file(&tmp_path);

    let ax_script = r#"
tell application "System Events"
    set frontApp to first application process whose frontmost is true
    set appName to name of frontApp
    set winTitle to ""
    try
        set winTitle to name of window 1 of frontApp
    end try
    set textParts to {}
    try
        set uiElements to entire contents of window 1 of frontApp
        set maxElements to (count of uiElements)
        if maxElements > 500 then set maxElements to 500
        repeat with i from 1 to maxElements
            set elem to item i of uiElements
            try
                set elemRole to role of elem
                if elemRole is in {"AXTextField", "AXTextArea", "AXStaticText"} then
                    set elemValue to value of elem
                    if elemValue is not missing value and elemValue is not "" then
                        set end of textParts to elemValue
                    end if
                end if
            end try
        end repeat
    end try
    set AppleScript's text item delimiters to linefeed
    return appName & "|||" & winTitle & "|||" & (textParts as string)
end tell
"#;

    let (mut window_title, mut extracted_text, mut needs_permission) =
        (String::new(), String::new(), false);

    if let Ok(output) = Command::new("osascript").args(["-e", ax_script]).output() {
        if output.status.success() {
            let result = String::from_utf8_lossy(&output.stdout).trim().to_string();
            let parts: Vec<&str> = result.splitn(3, "|||").collect();
            window_title = parts.first().unwrap_or(&"").to_string();
            if parts.len() > 1 {
                window_title = format!("{} - {}", window_title, parts[1]);
            }
            if parts.len() > 2 {
                extracted_text = parts[2].to_string();
            }
        } else {
            let stderr = String::from_utf8_lossy(&output.stderr);
            if stderr.contains("不允许辅助访问")
                || stderr.to_lowercase().contains("not allowed assistive")
            {
                needs_permission = true;
            }
            if let Ok(title_out) = Command::new("osascript")
                .args(["-e", r#"tell application "System Events" to get name of first application process whose frontmost is true"#])
                .output()
            {
                if title_out.status.success() {
                    window_title = String::from_utf8_lossy(&title_out.stdout).trim().to_string();
                }
            }
        }
    }

    (
        screenshot_b64,
        window_title,
        extracted_text,
        needs_permission,
    )
}

#[cfg(target_os = "windows")]
mod win {
    use super::ensure_screenshot_size_limit;
    use base64::Engine;
    use std::ffi::OsString;
    use std::os::windows::ffi::OsStringExt;
    use windows_sys::Win32::Foundation::{HWND, RECT};
    use windows_sys::Win32::Graphics::Gdi::{
        BitBlt, CreateCompatibleBitmap, CreateCompatibleDC, DeleteDC, DeleteObject, GetDIBits,
        SelectObject, BITMAPINFO, BITMAPINFOHEADER, BI_RGB, DIB_RGB_COLORS, SRCCOPY,
    };
    use windows_sys::Win32::System::ProcessStatus::GetModuleFileNameExW;
    use windows_sys::Win32::System::Threading::{OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION};
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetClientRect, GetForegroundWindow, GetWindowTextLengthW, GetWindowTextW,
        GetWindowThreadProcessId, PrintWindow, PW_CLIENTONLY,
    };

    /// 获取前台窗口所属进程的可执行文件名（不含路径和后缀）
    pub fn get_foreground_app_name() -> String {
        unsafe {
            let hwnd = GetForegroundWindow();
            if hwnd == 0 {
                return String::new();
            }
            let mut pid: u32 = 0;
            GetWindowThreadProcessId(hwnd, &mut pid);
            if pid == 0 {
                return String::new();
            }
            let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
            if handle == 0 {
                return String::new();
            }
            let mut buf = [0u16; 1024];
            let len = GetModuleFileNameExW(handle, 0, buf.as_mut_ptr(), buf.len() as u32);
            windows_sys::Win32::Foundation::CloseHandle(handle);
            if len == 0 {
                return String::new();
            }
            let path = OsString::from_wide(&buf[..len as usize]);
            let path = path.to_string_lossy();
            path.rsplit('\\')
                .next()
                .unwrap_or("")
                .trim_end_matches(".exe")
                .trim_end_matches(".EXE")
                .to_string()
        }
    }

    fn get_window_title(hwnd: HWND) -> String {
        unsafe {
            let len = GetWindowTextLengthW(hwnd);
            if len <= 0 {
                return String::new();
            }
            let mut buf = vec![0u16; (len + 1) as usize];
            let copied = GetWindowTextW(hwnd, buf.as_mut_ptr(), buf.len() as i32);
            if copied <= 0 {
                return String::new();
            }
            OsString::from_wide(&buf[..copied as usize])
                .to_string_lossy()
                .into_owned()
        }
    }

    /// PrintWindow 截取前台窗口客户区，返回 JPEG base64
    fn capture_foreground_window() -> String {
        unsafe {
            let hwnd = GetForegroundWindow();
            if hwnd == 0 {
                return String::new();
            }

            let mut rect = RECT {
                left: 0,
                top: 0,
                right: 0,
                bottom: 0,
            };
            if GetClientRect(hwnd, &mut rect) == 0 {
                return String::new();
            }
            let width = rect.right - rect.left;
            let height = rect.bottom - rect.top;
            if width <= 0 || height <= 0 {
                return String::new();
            }

            let hdc_screen = windows_sys::Win32::Graphics::Gdi::GetDC(hwnd);
            if hdc_screen == 0 {
                return String::new();
            }
            let hdc_mem = CreateCompatibleDC(hdc_screen);
            let hbm = CreateCompatibleBitmap(hdc_screen, width, height);
            let old = SelectObject(hdc_mem, hbm);

            // PW_CLIENTONLY: 只截客户区，排除标题栏
            let printed = PrintWindow(hwnd, hdc_mem, PW_CLIENTONLY);
            if printed == 0 {
                // PrintWindow 失败时回退到 BitBlt
                BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, 0, 0, SRCCOPY);
            }

            let mut bmi = std::mem::zeroed::<BITMAPINFO>();
            bmi.bmiHeader.biSize = std::mem::size_of::<BITMAPINFOHEADER>() as u32;
            bmi.bmiHeader.biWidth = width;
            bmi.bmiHeader.biHeight = -height; // top-down DIB
            bmi.bmiHeader.biPlanes = 1;
            bmi.bmiHeader.biBitCount = 32;
            bmi.bmiHeader.biCompression = BI_RGB;

            let pixel_count = (width * height) as usize;
            let mut pixels = vec![0u8; pixel_count * 4];
            GetDIBits(
                hdc_mem,
                hbm,
                0,
                height as u32,
                pixels.as_mut_ptr() as *mut _,
                &mut bmi,
                DIB_RGB_COLORS,
            );

            SelectObject(hdc_mem, old);
            DeleteObject(hbm);
            DeleteDC(hdc_mem);
            windows_sys::Win32::Graphics::Gdi::ReleaseDC(hwnd, hdc_screen);

            // BGRA -> RGBA
            for chunk in pixels.chunks_exact_mut(4) {
                chunk.swap(0, 2);
            }

            let img = image::RgbaImage::from_raw(width as u32, height as u32, pixels);
            let Some(img) = img else {
                return String::new();
            };

            let mut jpeg_buf = std::io::Cursor::new(Vec::new());
            if image::DynamicImage::ImageRgba8(img)
                .write_to(&mut jpeg_buf, image::ImageFormat::Jpeg)
                .is_err()
            {
                return String::new();
            }

            let jpeg_bytes = ensure_screenshot_size_limit(jpeg_buf.into_inner());
            base64::engine::general_purpose::STANDARD.encode(&jpeg_bytes)
        }
    }

    /// 通过 PowerShell + UI Automation .NET API 提取前台窗口文本元素
    fn extract_ui_text() -> String {
        let ps_script = r#"
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$auto = [System.Windows.Automation.AutomationElement]
$root = $auto::FocusedElement
if ($null -eq $root) { exit }
try { $root = [System.Windows.Automation.TreeWalker]::RawViewWalker.GetParent($root) } catch {}
if ($null -eq $root) { exit }
$textCondition = New-Object System.Windows.Automation.OrCondition(
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Text)),
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)),
    (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::Document))
)
$elements = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, $textCondition)
$count = 0
foreach ($el in $elements) {
    if ($count -ge 500) { break }
    try {
        $name = $el.Current.Name
        if ($name -and $name.Trim().Length -gt 0) {
            Write-Output $name.Trim()
            $count++
            continue
        }
        $vp = $el.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        if ($null -ne $vp) {
            $val = $vp.Current.Value
            if ($val -and $val.Trim().Length -gt 0) {
                Write-Output $val.Trim()
                $count++
            }
        }
    } catch {}
}
"#;
        let mut cmd = Command::new("powershell");
        cmd.args(["-NoProfile", "-NonInteractive", "-Command", ps_script]);
        super::suppress_console_window(&mut cmd);
        let output = cmd.output();

        match output {
            Ok(out) if out.status.success() => {
                String::from_utf8_lossy(&out.stdout).trim().to_string()
            }
            _ => String::new(),
        }
    }

    pub fn capture_appshot() -> (String, String, String, bool) {
        let hwnd = unsafe { GetForegroundWindow() };
        let window_title = if hwnd != 0 {
            let app_name = get_foreground_app_name();
            let title = get_window_title(hwnd);
            if !app_name.is_empty() && !title.is_empty() {
                format!("{} - {}", app_name, title)
            } else if !title.is_empty() {
                title
            } else {
                app_name
            }
        } else {
            String::new()
        };

        let screenshot_b64 = capture_foreground_window();
        let extracted_text = extract_ui_text();

        (screenshot_b64, window_title, extracted_text, false)
    }
}

#[cfg(target_os = "windows")]
fn capture_appshot_windows() -> (String, String, String, bool) {
    win::capture_appshot()
}
