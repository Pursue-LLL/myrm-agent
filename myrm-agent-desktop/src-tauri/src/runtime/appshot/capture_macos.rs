//! macOS Appshot 截屏：screencapture + AppleScript AX 文本提取。

use std::io::Read;
use std::process::Command;

use base64::Engine;

use super::common::{ensure_screenshot_size_limit, truncate_utf8};

pub(crate) fn capture_macos() -> (String, String, String, bool, String) {
    capture_appshot_macos()
}

pub(super) fn capture_appshot_macos() -> (String, String, String, bool, String) {
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
    set selectedText to ""
    try
        set focusedElem to focused UI element of frontApp
        set selectedText to value of attribute "AXSelectedText" of focusedElem
        if selectedText is missing value then set selectedText to ""
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
    return appName & "|||" & winTitle & "|||" & (textParts as string) & "|||" & selectedText
end tell
"#;

    let (mut window_title, mut extracted_text, mut needs_permission, mut selected_text) =
        (String::new(), String::new(), false, String::new());

    if let Ok(output) = Command::new("osascript").args(["-e", ax_script]).output() {
        if output.status.success() {
            let result = String::from_utf8_lossy(&output.stdout).trim().to_string();
            let (main_part, sel_raw) = match result.rsplit_once("|||") {
                Some((main, sel)) => (main, sel.trim()),
                None => (result.as_str(), ""),
            };
            if !sel_raw.is_empty() {
                selected_text = truncate_utf8(sel_raw, 10_000);
            }
            let parts: Vec<&str> = main_part.splitn(3, "|||").collect();
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
        selected_text,
    )
}
