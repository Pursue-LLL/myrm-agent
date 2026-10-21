//! Windows Appshot 截屏：PrintWindow + UI Automation 文本提取。

use std::ffi::OsString;
use std::os::windows::ffi::OsStringExt;
use std::process::Command;
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

use base64::Engine;

use super::common::{ensure_screenshot_size_limit, truncate_utf8};
use crate::runtime::suppress_console_window;

pub(super) fn get_foreground_app_name() -> String {
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

        let printed = PrintWindow(hwnd, hdc_mem, PW_CLIENTONLY);
        if printed == 0 {
            BitBlt(hdc_mem, 0, 0, width, height, hdc_screen, 0, 0, SRCCOPY);
        }

        let mut bmi = std::mem::zeroed::<BITMAPINFO>();
        bmi.bmiHeader.biSize = std::mem::size_of::<BITMAPINFOHEADER>() as u32;
        bmi.bmiHeader.biWidth = width;
        bmi.bmiHeader.biHeight = -height;
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
    suppress_console_window(&mut cmd);
    match cmd.output() {
        Ok(out) if out.status.success() => String::from_utf8_lossy(&out.stdout).trim().to_string(),
        _ => String::new(),
    }
}

fn capture_appshot() -> (String, String, String, bool) {
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

fn get_selected_text_via_clipboard() -> String {
    use std::thread;
    use std::time::Duration;

    let saved = {
        let mut cmd = Command::new("powershell");
        cmd.args(["-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard"]);
        suppress_console_window(&mut cmd);
        cmd.output().ok().and_then(|o| {
            if o.status.success() {
                Some(String::from_utf8_lossy(&o.stdout).trim().to_string())
            } else {
                None
            }
        })
    };

    {
        let mut cmd = Command::new("powershell");
        cmd.args([
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('^c')",
        ]);
        suppress_console_window(&mut cmd);
        let _ = cmd.output();
    }

    thread::sleep(Duration::from_millis(100));

    let selected = {
        let mut cmd = Command::new("powershell");
        cmd.args(["-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard"]);
        suppress_console_window(&mut cmd);
        cmd.output()
            .ok()
            .and_then(|o| {
                if o.status.success() {
                    let text = String::from_utf8_lossy(&o.stdout).trim().to_string();
                    if !text.is_empty() && saved.as_deref() != Some(&text) {
                        Some(text)
                    } else {
                        None
                    }
                } else {
                    None
                }
            })
            .unwrap_or_default()
    };

    if let Some(original) = saved {
        let mut cmd = Command::new("powershell");
        cmd.args([
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "$input | Set-Clipboard",
        ]);
        cmd.stdin(std::process::Stdio::piped());
        suppress_console_window(&mut cmd);
        if let Ok(mut child) = cmd.spawn() {
            if let Some(stdin) = child.stdin.as_mut() {
                use std::io::Write;
                let _ = stdin.write_all(original.as_bytes());
            }
            let _ = child.wait();
        }
    }

    truncate_utf8(&selected, 10_000)
}

pub(super) fn capture_windows() -> (String, String, String, bool, String) {
    let (screenshot, title, text, perm) = capture_appshot();
    let selected = get_selected_text_via_clipboard();
    (screenshot, title, text, perm, selected)
}

pub(super) fn capture_appshot_windows() -> (String, String, String, bool, String) {
    capture_windows()
}
