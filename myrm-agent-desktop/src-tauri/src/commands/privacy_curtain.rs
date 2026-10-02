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
//! - config::{SystemConfig, ConfigManager} (POS: privacy_curtain_enabled 开关)
//!
//! [OUTPUT]
//! - show/hide/active/set_texts/report_physical_input IPC
//! - curtain_state.json 文件桥（server 无人值守 watcher 读写）
//! - curtain:state-changed / curtain:physical-input 事件
//!
//! [POS]
//! 帷幕是唯一视觉事实源：watcher 只按锁屏态+auto_engaged/pending 标记流转，
//! 手动帷幕（auto_engaged=false）不受 watcher 干涉，仅显式命令收起。
//! 输入感知=点击可靠（未聚焦窗口收不到键盘，锁屏态键盘落在登录窗无害），
//! 如实以看板文案告知"交互即锁定"。Linux 不支持帷幕（fail-fast），
//! Windows <2004 WDA 失败时降级为不拉帷幕（维持既有 Guardian 行为）。

use std::fs;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

use tauri::{AppHandle, Emitter, Manager, WebviewWindowBuilder};

use crate::utils::screen_lock;

const CURTAIN_LABEL_PREFIX: &str = "privacy-curtain-";
/// 帷幕状态桥文件名（server 侧经 MYRM_CURTAIN_STATE_FILE 环境变量定位）。
pub const CURTAIN_STATE_FILE: &str = "curtain_state.json";
const WATCHER_TICK_MS: u64 = 1000;

/// 文件桥状态：server 无人值守 watcher 与 Tauri 帷幕状态机的共享事实。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct CurtainState {
    /// 帷幕当前拉起。
    pub active: bool,
    /// 由锁屏 watcher 自动拉起（区别于手动拉起；解锁时仅 auto 帷幕自动收起）。
    pub auto_engaged: bool,
    /// 最近一次帷幕上物理输入的时间戳（server 静默期判定基准）。
    pub last_physical_input_ms: u64,
    /// server 即将代为解锁：Tauri watcher 消费后保持帷幕。
    pub pending_auto_unlock: bool,
}

impl Default for CurtainState {
    fn default() -> Self {
        Self {
            active: false,
            auto_engaged: false,
            last_physical_input_ms: 0,
            pending_auto_unlock: false,
        }
    }
}

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

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

fn log_audit(action: &str, success: bool, reason: &str) {
    println!(
        "[AUDIT] privacy_curtain: action={} success={} reason={} ts={}",
        action,
        success,
        reason,
        now_ms()
    );
}

// ── 文件桥 ────────────────────────────────────────────────────────

fn state_path(app: &AppHandle) -> PathBuf {
    app.path()
        .app_data_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .join(CURTAIN_STATE_FILE)
}

fn read_state(app: &AppHandle) -> CurtainState {
    fs::read_to_string(state_path(app))
        .ok()
        .and_then(|content| serde_json::from_str(&content).ok())
        .unwrap_or_default()
}

fn write_state(app: &AppHandle, state: &CurtainState) {
    let path = state_path(app);
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }
    if let Ok(content) = serde_json::to_string_pretty(state) {
        let _ = fs::write(&path, content);
    }
}

fn mutate_state(app: &AppHandle, apply: impl FnOnce(&mut CurtainState)) {
    let mut state = read_state(app);
    let before = state.active;
    apply(&mut state);
    write_state(app, &state);
    if before != state.active {
        let _ = app.emit("curtain:state-changed", state.clone());
    }
}

// ── 看板 HTML ──────────────────────────────────────────────────────

fn html_escape(input: &str) -> String {
    input
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
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

fn curtain_windows(app: &AppHandle) -> Vec<tauri::WebviewWindow> {
    app.webview_windows()
        .into_iter()
        .filter(|(label, _)| label.starts_with(CURTAIN_LABEL_PREFIX))
        .map(|(_, window)| window)
        .collect()
}

fn close_curtain_windows(app: &AppHandle) {
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
        .inner_size(
            size.width as f64 / scale,
            size.height as f64 / scale,
        )
        .position(position.x as f64 / scale, position.y as f64 / scale)
        .build()
        .map_err(|e| e.to_string())?;

    // 帷幕必须接收交互（点击→上报→回锁），不能穿透：穿透会让路过者操作底层真实窗口。
    apply_capture_exclusion(&window)?;
    Ok(window)
}

/// 幂等重建全部帷幕窗（每显示器一窗；先清孤儿窗再按当前显示器布局重建）。
fn deploy_curtain_windows(app: &AppHandle) -> Result<(), String> {
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
    let mut built = Vec::with_capacity(monitors.len());
    for (index, monitor) in monitors.iter().enumerate() {
        built.push(build_curtain_window(app, index, monitor, &html)?);
    }
    let _ = built; // 窗口由 Tauri 事件循环持有，此处仅确保创建成功
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

/// 帷幕上的物理输入上报：更新静默期基准、清除代解锁标记、立即回锁。
/// 帷幕输入不穿透到底层窗口，路过者交互唯一效果就是加固锁屏。
#[tauri::command]
pub fn curtain_report_physical_input(app: AppHandle, source: String) -> Result<(), String> {
    mutate_state(&app, |state| {
        state.last_physical_input_ms = now_ms();
        state.pending_auto_unlock = false;
    });
    log_audit("physical_input", true, &source);
    let _ = app.emit("curtain:physical-input", serde_json::json!({ "source": source }));
    let locked = screen_lock::lock_screen();
    log_audit("relock_on_input", locked.is_ok(), "curtain input guard");
    Ok(())
}

// ── 锁屏 watcher ─────────────────────────────────────────────────

fn curtain_enabled(app: &AppHandle) -> bool {
    app.try_state::<crate::config::ConfigManager>()
        .map(|manager| manager.load().privacy_curtain_enabled)
        .unwrap_or(false)
}

/// 锁屏触发的帷幕状态机（1s tick）：
/// - locked 且帷幕未拉 → 自动拉起（auto_engaged=true，静默期基准初始化）；
/// - unlocked 且 pending_auto_unlock → server 代解锁，保持帷幕并消费标记；
/// - unlocked 且 auto 帷幕在（无 pending）→ 用户本人解锁，收起帷幕；
/// - 手动帷幕（auto_engaged=false）与未启用开关时不干涉；
/// - 帷幕在且显示器数量变化 → 幂等重建（热插拔跟随）。
pub fn spawn_privacy_curtain_watcher(app: AppHandle) {
    std::thread::spawn(move || loop {
        std::thread::sleep(std::time::Duration::from_millis(WATCHER_TICK_MS));

        let enabled = curtain_enabled(&app);
        let state = read_state(&app);
        let windows = curtain_windows(&app);

        if !enabled {
            if state.active || !windows.is_empty() {
                close_curtain_windows(&app);
                mutate_state(&app, |s| {
                    s.active = false;
                    s.auto_engaged = false;
                });
                log_audit("auto_release", true, "curtain disabled");
            }
            continue;
        }

        let locked = screen_lock::is_screen_locked();

        if locked && !state.active && windows.is_empty() {
            match deploy_curtain_windows(&app) {
                Ok(()) => {
                    mutate_state(&app, |s| {
                        s.active = true;
                        s.auto_engaged = true;
                        s.last_physical_input_ms = now_ms();
                    });
                    log_audit("auto_engage", true, "screen locked");
                }
                Err(reason) => log_audit("auto_engage", false, &reason),
            }
            continue;
        }

        if !locked {
            if state.pending_auto_unlock {
                mutate_state(&app, |s| {
                    s.pending_auto_unlock = false;
                });
                log_audit("keep_on_unlock", true, "server-initiated unlock");
            } else if state.auto_engaged {
                close_curtain_windows(&app);
                mutate_state(&app, |s| {
                    s.active = false;
                    s.auto_engaged = false;
                });
                log_audit("auto_release", true, "user unlocked");
            }
            continue;
        }

        // locked 且帷幕已拉：显示器热插拔跟随（数量不一致才重建，避免闪烁）。
        let monitor_count = app
            .available_monitors()
            .map(|monitors| monitors.len())
            .unwrap_or(windows.len());
        if !windows.is_empty() && windows.len() != monitor_count {
            match deploy_curtain_windows(&app) {
                Ok(()) => log_audit("rebuild", true, "display layout changed"),
                Err(reason) => log_audit("rebuild", false, &reason),
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::{curtain_html, default_texts, CurtainState, CurtainTexts};

    #[test]
    fn state_defaults_to_inactive() {
        let state = CurtainState::default();
        assert!(!state.active);
        assert!(!state.auto_engaged);
        assert!(!state.pending_auto_unlock);
        assert_eq!(state.last_physical_input_ms, 0);
    }

    #[test]
    fn state_roundtrips_through_camel_case_json() {
        let state = CurtainState {
            active: true,
            auto_engaged: true,
            last_physical_input_ms: 42,
            pending_auto_unlock: true,
        };
        let json = serde_json::to_string(&state).expect("serialize");
        assert!(json.contains("\"active\":true"));
        assert!(json.contains("\"lastPhysicalInputMs\":42"));
        let parsed: CurtainState = serde_json::from_str(&json).expect("deserialize");
        assert!(parsed.active && parsed.pending_auto_unlock);
    }

    #[test]
    fn partial_state_json_deserializes_with_defaults() {
        let parsed: CurtainState =
            serde_json::from_str("{\"active\":true}").expect("deserialize partial");
        assert!(parsed.active);
        assert!(!parsed.auto_engaged);
    }

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
