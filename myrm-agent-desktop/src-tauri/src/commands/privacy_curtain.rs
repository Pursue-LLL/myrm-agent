//! 工位防窥帷幕（Privacy Curtain）——无人值守 CU 任务的屏幕隐私层。
//!
//! 场景：用户离机挂机跑 Computer Use 任务时，锁屏即断 CU、不锁屏则裸奔机密。
//! 帷幕在锁屏触发时自动拉起：每显示器一个全屏置顶黑幕+免扰看板，底层
//! 截图通道被排除（macOS: server 侧 Quartz below-window；Windows: WDA_EXCLUDEFROMCAPTURE），
//! 物理交互立即回锁，AI 会话经文件桥在静默期满后由 server 解锁续跑。
//!
//! [INPUT]
//! - tauri AppHandle (POS: 窗口/事件/app data 目录)
//! - utils::screen_lock (POS: 锁屏检测/回锁)
//! - commands::privacy_curtain_state (POS: 帷幕状态桥，curtain_state.json 的 Tauri 侧唯一读写入口)
//! - config::{SystemConfig, ConfigManager} (POS: privacy_curtain_enabled 开关)
//!
//! [OUTPUT]
//! - show/hide/active/set_texts/report_physical_input IPC
//! - curtain:state-changed / curtain:physical-input 事件
//! - spawn_privacy_curtain_watcher（见 privacy_curtain_watcher.rs）
//!
//! [POS]
//! 帷幕是唯一视觉事实源：watcher 只按锁屏态+auto_engaged/pending 标记流转，
//! 手动帷幕（auto_engaged=false）不受 watcher 干涉，仅显式命令收起。
//! 输入感知=点击可靠（未聚焦窗口收不到键盘，锁屏态键盘落在登录窗无害），
//! 如实以看板文案告知"交互即锁定"。Linux 不支持帷幕（fail-fast），
//! Windows <2004 WDA 失败时降级为不拉帷幕（由 Lock-Screen Guardian 兜底）。

use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tauri::{AppHandle, Emitter, Manager, WebviewWindowBuilder};

use crate::commands::privacy_curtain_state::{mutate_state, read_state};
use crate::utils::screen_lock;

const CURTAIN_LABEL_PREFIX: &str = "privacy-curtain-";
/// 输入守卫等待系统确认锁定的上限；超时视为锁屏请求未生效。
const LOCK_CONFIRM_TIMEOUT: Duration = Duration::from_secs(2);

/// 看板三段文案（由前端按当前 locale 注入缓存，Rust 侧仅存默认英文兜底）。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CurtainTexts {
    pub primary: String,
    pub sub: String,
    pub hint: String,
}

fn default_texts() -> CurtainTexts {
    CurtainTexts {
        primary: "AI is working — screen protected".to_string(),
        sub: "This workstation is running an automated session. Content stays hidden until the owner returns.".to_string(),
        hint: "Any interaction locks this screen instantly".to_string(),
    }
}

static CACHED_TEXTS: Mutex<Option<CurtainTexts>> = Mutex::new(None);

fn current_texts() -> CurtainTexts {
    CACHED_TEXTS
        .lock()
        .ok()
        .and_then(|guard| guard.clone())
        .unwrap_or_else(default_texts)
}

pub(crate) fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

pub(crate) fn log_audit(action: &str, success: bool, reason: &str) {
    println!(
        "[AUDIT] privacy_curtain: action={} success={} reason={} ts={}",
        action,
        success,
        reason,
        now_ms()
    );
}

// ── 看板 HTML ──────────────────────────────────────────────────────

fn html_escape(input: &str) -> String {
    input
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

fn curtain_html(texts: &CurtainTexts) -> String {
    format!(
        r#"<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{ margin: 0; width: 100%; height: 100%; background: #000; overflow: hidden; }}
    .wrap {{
      position: fixed; inset: 0; display: flex; flex-direction: column;
      align-items: center; justify-content: center; gap: 18px;
      font-family: -apple-system, "SF Pro Display", system-ui, sans-serif;
      color: #e5e7eb; user-select: none; cursor: default;
    }}
    .brand {{ font-size: 15px; letter-spacing: 0.35em; color: #6b7280; text-transform: uppercase; }}
    .dot {{ width: 10px; height: 10px; border-radius: 50%; background: #10b981;
           animation: pulse 2.4s ease-in-out infinite; }}
    .primary {{ font-size: 28px; font-weight: 600; color: #f9fafb; text-align: center; padding: 0 24px; }}
    .sub {{ font-size: 15px; color: #9ca3af; max-width: 560px; text-align: center;
           line-height: 1.6; padding: 0 24px; }}
    .hint {{ margin-top: 26px; font-size: 12px; color: #4b5563; border: 1px solid #1f2937;
            border-radius: 999px; padding: 8px 18px; letter-spacing: 0.02em; }}
    @keyframes pulse {{ 0%, 100% {{ opacity: 0.35; }} 50% {{ opacity: 1; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="brand">Myrm</div>
    <div class="dot"></div>
    <div class="primary">{}</div>
    <div class="sub">{}</div>
    <div class="hint">{}</div>
  </div>
  <script>
    var throttled = 0;
    function report(source) {{
      try {{ window.__TAURI_INTERNALS__.invoke('curtain_report_physical_input', {{ source: source }}); }} catch (e) {{}}
    }}
    ['pointerdown', 'keydown', 'wheel'].forEach(function (ev) {{
      addEventListener(ev, function () {{ report(ev); }}, true);
    }});
    addEventListener('pointermove', function () {{
      var now = Date.now();
      if (now - throttled > 500) {{ throttled = now; report('pointermove'); }}
    }}, true);
  </script>
</body>
</html>"#,
        html_escape(&texts.primary),
        html_escape(&texts.sub),
        html_escape(&texts.hint),
    )
}

// ── 帷幕窗口管理 ──────────────────────────────────────────────────

pub(crate) fn curtain_windows(app: &AppHandle) -> Vec<tauri::WebviewWindow> {
    app.webview_windows()
        .into_iter()
        .filter(|(label, _)| label.starts_with(CURTAIN_LABEL_PREFIX))
        .map(|(_, window)| window)
        .collect()
}

pub(crate) fn close_curtain_windows(app: &AppHandle) {
    for window in curtain_windows(app) {
        let _ = window.destroy();
    }
}

/// Windows：将帷幕窗从系统截图/投屏通道排除（WDA_EXCLUDEFROMCAPTURE）。
/// Win10 <2004 无此常量效果，SetWindowDisplayAffinity 返回失败 → 调用方降级。
#[cfg(target_os = "windows")]
fn apply_capture_exclusion(window: &tauri::WebviewWindow) -> Result<(), String> {
    use windows_sys::Win32::UI::WindowsAndMessaging::SetWindowDisplayAffinity;
    const WDA_EXCLUDEFROMCAPTURE: u32 = 0x0000_0011;
    let hwnd = window.hwnd().map_err(|e| e.to_string())?;
    let ok = unsafe { SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE) };
    if ok == 0 {
        return Err(
            "SetWindowDisplayAffinity failed: Windows build below 2004 cannot exclude curtain from capture".to_string(),
        );
    }
    Ok(())
}

#[cfg(not(target_os = "windows"))]
fn apply_capture_exclusion(_window: &tauri::WebviewWindow) -> Result<(), String> {
    Ok(())
}

fn build_curtain_window(
    app: &AppHandle,
    index: usize,
    monitor: &tauri::Monitor,
    html: &str,
) -> Result<tauri::WebviewWindow, String> {
    use base64::{engine::general_purpose::STANDARD, Engine as _};
    use tauri::{Url, WebviewUrl};

    let data_url = format!("data:text/html;base64,{}", STANDARD.encode(html.as_bytes()));
    let url = Url::parse(&data_url).map_err(|e| e.to_string())?;

    let scale = monitor.scale_factor();
    let size = monitor.size();
    let position = monitor.position();
    let label = format!("{CURTAIN_LABEL_PREFIX}{index}");

    let window = WebviewWindowBuilder::new(app, &label, WebviewUrl::CustomProtocol(url))
        .title("Privacy Curtain")
        .always_on_top(true)
        .decorations(false)
        .skip_taskbar(true)
        .focused(false)
        .visible(true)
        .resizable(false)
        .maximizable(false)
        .minimizable(false)
        .closable(false)
        .inner_size(size.width as f64 / scale, size.height as f64 / scale)
        .position(position.x as f64 / scale, position.y as f64 / scale)
        .build()
        .map_err(|e| e.to_string())?;

    // 帷幕必须接收交互（点击→上报→回锁），不能穿透：穿透会让路过者操作底层真实窗口。
    apply_capture_exclusion(&window)?;
    Ok(window)
}

/// 幂等重建全部帷幕窗（每显示器一窗；先清孤儿窗再按当前显示器布局重建）。
pub(crate) fn deploy_curtain_windows(app: &AppHandle) -> Result<(), String> {
    if cfg!(target_os = "linux") {
        return Err("Privacy curtain is not supported on Linux".to_string());
    }

    close_curtain_windows(app);

    let monitors = app
        .available_monitors()
        .map_err(|e| e.to_string())?
        .into_iter()
        .collect::<Vec<_>>();
    if monitors.is_empty() {
        return Err("No monitors available".to_string());
    }

    let html = curtain_html(&current_texts());
    for (index, monitor) in monitors.iter().enumerate() {
        // 逐窗构建并校验（任一显示器失败即整体回滚孤儿窗由调用方清理重试）。
        build_curtain_window(app, index, monitor, &html)?;
    }
    Ok(())
}

// ── IPC 命令 ──────────────────────────────────────────────────────

/// 手动拉起帷幕（托盘/设置页入口），不受 watcher 干涉，需显式收起。
#[tauri::command]
pub fn show_privacy_curtain(app: AppHandle, texts: Option<CurtainTexts>) -> Result<(), String> {
    if let Some(texts) = texts {
        if let Ok(mut guard) = CACHED_TEXTS.lock() {
            *guard = Some(texts);
        }
    }
    deploy_curtain_windows(&app)?;
    mutate_state(&app, |state| {
        state.active = true;
        state.auto_engaged = false;
        state.last_physical_input_ms = now_ms();
    });
    log_audit("show", true, "manual engage");
    Ok(())
}

/// 收起帷幕（托盘/设置页入口；手动帷幕的唯一自动路径不存在）。
#[tauri::command]
pub fn hide_privacy_curtain(app: AppHandle) -> Result<(), String> {
    close_curtain_windows(&app);
    mutate_state(&app, |state| {
        state.active = false;
        state.auto_engaged = false;
    });
    log_audit("hide", true, "manual release");
    Ok(())
}

/// 查询帷幕是否拉起（前端看板/设置页状态回显）。
#[tauri::command]
pub fn privacy_curtain_active(app: AppHandle) -> Result<bool, String> {
    Ok(read_state(&app).active)
}

/// 前端按当前 locale 注入看板文案缓存（watcher 自动拉起时无前端调用方在场）。
#[tauri::command]
pub fn curtain_set_texts(texts: CurtainTexts) -> Result<(), String> {
    if let Ok(mut guard) = CACHED_TEXTS.lock() {
        *guard = Some(texts);
    }
    Ok(())
}

/// 帷幕上的物理输入上报：更新静默期基准并回锁屏幕。
/// 帷幕输入不穿透到底层窗口，路过者交互唯一效果就是加固锁屏。
///
/// 代解锁租约位仅在系统确认已锁定后才清除：先清位会让 watcher 在锁屏生效前
/// 的 tick 里把解锁态判为用户解锁并收起帷幕（桌面闪现）；锁屏请求被拒时
/// 保留租约位，帷幕继续遮蔽。
#[tauri::command]
pub async fn curtain_report_physical_input(app: AppHandle, source: String) -> Result<(), String> {
    mutate_state(&app, |state| {
        state.last_physical_input_ms = now_ms();
    });
    log_audit("physical_input", true, &source);
    let _ = app.emit(
        "curtain:physical-input",
        serde_json::json!({ "source": source }),
    );

    let locked = tauri::async_runtime::spawn_blocking(|| {
        screen_lock::lock_screen_confirmed(LOCK_CONFIRM_TIMEOUT)
    })
    .await
    .map_err(|error| error.to_string())?;
    log_audit("relock_on_input", locked.is_ok(), "curtain input guard");
    if locked.is_ok() {
        mutate_state(&app, |state| {
            state.pending_auto_unlock = false;
        });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{curtain_html, default_texts, CurtainTexts};

    #[test]
    fn html_escapes_untrusted_texts() {
        let texts = CurtainTexts {
            primary: "<script>alert(1)</script>".to_string(),
            sub: "a & b".to_string(),
            hint: "\"quoted\"".to_string(),
        };
        let html = curtain_html(&texts);
        assert!(html.contains("&lt;script&gt;"));
        assert!(html.contains("a &amp; b"));
        assert!(!html.contains("\"quoted\""));
    }

    #[test]
    fn default_texts_are_non_empty() {
        let texts = default_texts();
        assert!(!texts.primary.is_empty());
        assert!(!texts.sub.is_empty());
        assert!(!texts.hint.is_empty());
    }
}
