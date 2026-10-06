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
//! - commands::privacy_curtain_page (POS: 看板页面内容与承载它的自定义协议 URL)
//! - commands::privacy_curtain_presentation (POS: 跨 Space / 菜单栏覆盖的平台呈现层)
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
//! 帷幕窗口的生命周期同时托管应用的激活策略（见 privacy_curtain_presentation.rs）：
//! 创建前进入覆盖模式、全部销毁后恢复，二者只在本文件的 deploy/close 两处发生。

use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tauri::{AppHandle, Emitter, Manager, WebviewWindowBuilder};

use crate::commands::privacy_curtain_page::{self as page, CurtainTexts};
use crate::commands::privacy_curtain_presentation as presentation;
use crate::commands::privacy_curtain_state::{mutate_state, read_state};
use crate::utils::screen_lock;

const CURTAIN_LABEL_PREFIX: &str = "privacy-curtain-";
/// 输入守卫等待系统确认锁定的上限；超时视为锁屏请求未生效。
const LOCK_CONFIRM_TIMEOUT: Duration = Duration::from_secs(2);

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

// ── 帷幕窗口管理 ──────────────────────────────────────────────────

pub(crate) fn curtain_windows(app: &AppHandle) -> Vec<tauri::WebviewWindow> {
    app.webview_windows()
        .into_iter()
        .filter(|(label, _)| label.starts_with(CURTAIN_LABEL_PREFIX))
        .map(|(_, window)| window)
        .collect()
}

fn destroy_curtain_windows(app: &AppHandle) {
    for window in curtain_windows(app) {
        let _ = window.destroy();
    }
}

/// 收起全部帷幕窗并恢复应用的常规呈现（Dock 图标 / 菜单栏）。
pub(crate) fn close_curtain_windows(app: &AppHandle) {
    destroy_curtain_windows(app);
    presentation::leave_overlay_mode(app);
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

/// 建一扇覆盖单个显示器的帷幕窗。label 带代号：新旧两代窗口在重建期间并存，
/// 同名会在旧窗销毁完成前冲突。
fn build_curtain_window(
    app: &AppHandle,
    generation: u64,
    index: usize,
    monitor: &tauri::Monitor,
    page_url: &tauri::Url,
) -> Result<tauri::WebviewWindow, String> {
    use tauri::{window::Color, WebviewUrl};

    let scale = monitor.scale_factor();
    let size = monitor.size();
    let position = monitor.position();
    let label = format!("{CURTAIN_LABEL_PREFIX}{generation}-{index}");

    let window = WebviewWindowBuilder::new(app, &label, WebviewUrl::CustomProtocol(page_url.clone()))
        .title("Privacy Curtain")
        .always_on_top(true)
        // 用户离机前可能停在他应用的全屏 Space，帷幕必须跟到每个 Space（仅 macOS 有此概念）。
        .visible_on_all_workspaces(cfg!(target_os = "macos"))
        // 页面首帧绘制前窗口底色就是黑的：持租约期间重建时屏幕前有人，不能闪白。
        .background_color(Color(0, 0, 0, 255))
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

    // 抬升失败只会让菜单栏露在帷幕之外，窗口本身仍在遮蔽：记审计而不回滚整次拉起。
    if let Err(reason) = presentation::raise_above_menu_bar(&window) {
        log_audit("raise_level", false, &reason);
    }
    // 帷幕必须接收交互（点击→上报→回锁），不能穿透：穿透会让路过者操作底层真实窗口。
    if let Err(reason) = apply_capture_exclusion(&window) {
        // 排除不了截图通道的窗口不能留下：它会把"受保护"的假象带到屏幕上。
        let _ = window.destroy();
        return Err(reason);
    }
    Ok(window)
}

/// 按当前显示器布局重建全部帷幕窗（每显示器一窗）。先建后拆（make-before-break）：
/// 新一代全部建成才销毁旧一代，任一环节失败则撤销新窗、旧窗原样保留——
/// 持租约期间屏幕已解锁，重建的任何空窗期都会让桌面裸露。
pub(crate) fn deploy_curtain_windows(app: &AppHandle) -> Result<(), String> {
    static GENERATION: AtomicU64 = AtomicU64::new(0);

    if cfg!(target_os = "linux") {
        return Err("Privacy curtain is not supported on Linux".to_string());
    }

    let monitors = app.available_monitors().map_err(|e| e.to_string())?;
    if monitors.is_empty() {
        return Err("No monitors available".to_string());
    }

    // 入口 URL 先于任何副作用求值：失败时不碰激活策略与现有窗口。
    let page_url = page::url()?;
    let previous = curtain_windows(app);
    let generation = GENERATION.fetch_add(1, Ordering::Relaxed) + 1;
    // 覆盖模式必须先于建窗生效；重建不经 close_curtain_windows，策略不会来回闪动。
    presentation::enter_overlay_mode(app);

    let mut built = Vec::with_capacity(monitors.len());
    for (index, monitor) in monitors.iter().enumerate() {
        match build_curtain_window(app, generation, index, monitor, &page_url) {
            Ok(window) => built.push(window),
            Err(reason) => {
                for window in built {
                    let _ = window.destroy();
                }
                if previous.is_empty() {
                    // 没有旧窗也没有新窗，就不会有人来 close：不能让应用停在覆盖模式。
                    presentation::leave_overlay_mode(app);
                }
                return Err(reason);
            }
        }
    }
    for window in previous {
        let _ = window.destroy();
    }
    Ok(())
}

// ── IPC 命令 ──────────────────────────────────────────────────────

/// 手动拉起帷幕（托盘/设置页入口），不受 watcher 干涉，需显式收起。
#[tauri::command]
pub fn show_privacy_curtain(app: AppHandle, texts: Option<CurtainTexts>) -> Result<(), String> {
    if let Some(texts) = texts {
        page::set_texts(texts);
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
    page::set_texts(texts);
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
