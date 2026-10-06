//! 工位防窥帷幕——窗口呈现层：让帷幕盖住"他应用全屏 Space"与菜单栏。
//!
//! 无人值守场景下用户离机前常停在某个全屏应用的 Space；server 解锁后桌面直接露出
//! 该 Space。macOS 上 Regular 应用的窗口不会出现在他应用的全屏 Space（即便设置了
//! 全空间可见），且 `always_on_top` 只到浮动层级、低于菜单栏——帷幕因此既可能整块
//! 缺席也可能留出一条菜单栏。本模块把这些平台差异收口，非 macOS 全部为空实现，
//! 调用方（`privacy_curtain.rs`）无需任何 `cfg`。
//!
//! [INPUT]
//! - tauri AppHandle / WebviewWindow (POS: 激活策略、主线程调度、原生窗口句柄)
//! - objc2 (POS: 向 NSWindow 发 `setLevel:`，tauri/tao 未暴露窗口层级；仅 macOS)
//!
//! [OUTPUT]
//! - enter_overlay_mode: 创建帷幕窗口前切到 Accessory 策略
//! - raise_above_menu_bar: 把帷幕窗抬到菜单栏之上
//! - leave_overlay_mode: 帷幕窗全部销毁后按主窗口是否在场恢复激活策略
//!
//! 三者失败均以 `Err(原因)` 返回，由调用方记审计：呈现层失败只影响覆盖范围与观感，
//! 不构成放弃遮蔽的理由。
//!
//! [POS]
//! 激活策略的语义由应用既有约定决定：Accessory = 主窗口隐藏（托盘常驻 / 开机自启），
//! Regular = 主窗口在场（app/tray.rs、runtime/appshot、runtime/inline_input 同此）。
//! 因此退出时不能无条件恢复 Regular（会让托盘常驻的应用凭空冒出 Dock 图标），
//! 也不能记住"进入前的策略"（帷幕期间别处可能已翻转），而是按退出时刻主窗口事实推导。

use tauri::AppHandle;

/// `kCGScreenSaverWindowLevel`：高于菜单栏（24）与 Dock（20），低于辅助功能与光标层。
#[cfg(target_os = "macos")]
const CURTAIN_WINDOW_LEVEL: isize = 1000;

/// 主窗口"在场"（可见或已最小化到 Dock）时应用必须保持 Regular：
/// 最小化窗口 `is_visible` 为 false，却仍依赖 Dock 图标恢复，误切 Accessory 会让它再也找不回。
#[cfg(any(target_os = "macos", test))]
fn main_window_present(visible: bool, minimized: bool) -> bool {
    visible || minimized
}

/// 创建帷幕窗口之前调用：Accessory 应用的窗口才能进入他应用的全屏 Space。
/// 策略切换与窗口创建经同一条主线程消息通道，调用顺序即生效顺序。
#[cfg(target_os = "macos")]
pub(crate) fn enter_overlay_mode(app: &AppHandle) -> Result<(), String> {
    app.set_activation_policy(tauri::ActivationPolicy::Accessory)
        .map_err(|error| error.to_string())
}

#[cfg(not(target_os = "macos"))]
pub(crate) fn enter_overlay_mode(_app: &AppHandle) -> Result<(), String> {
    Ok(())
}

/// 全部帷幕窗口销毁之后调用：按主窗口当前是否在场恢复激活策略。
#[cfg(target_os = "macos")]
pub(crate) fn leave_overlay_mode(app: &AppHandle) -> Result<(), String> {
    use tauri::Manager;

    let present = app.get_webview_window("main").is_some_and(|window| {
        main_window_present(
            window.is_visible().unwrap_or(false),
            window.is_minimized().unwrap_or(false),
        )
    });
    let policy = if present {
        tauri::ActivationPolicy::Regular
    } else {
        tauri::ActivationPolicy::Accessory
    };
    app.set_activation_policy(policy)
        .map_err(|error| error.to_string())
}

#[cfg(not(target_os = "macos"))]
pub(crate) fn leave_overlay_mode(_app: &AppHandle) -> Result<(), String> {
    Ok(())
}

/// 把帷幕窗抬到菜单栏之上（窗口创建后调用）。
///
/// `NSWindow` 只能在主线程操作：句柄在主线程任务内现取现用，窗口若已被销毁则
/// 取句柄失败并直接放弃，不会持有悬垂指针。
#[cfg(target_os = "macos")]
pub(crate) fn raise_above_menu_bar(window: &tauri::WebviewWindow) -> Result<(), String> {
    use objc2::{msg_send, runtime::AnyObject};

    let target = window.clone();
    window
        .run_on_main_thread(move || {
            let Ok(handle) = target.ns_window() else {
                return;
            };
            // SAFETY: `handle` 是本主线程任务内刚取得的存活 NSWindow（销毁同样发生在主线程，
            // 不会与此并发）；`setLevel:` 入参为 NSInteger，无返回值。
            unsafe {
                let ns_window = handle as *mut AnyObject;
                let _: () = msg_send![ns_window, setLevel: CURTAIN_WINDOW_LEVEL];
            }
        })
        .map_err(|error| error.to_string())
}

#[cfg(not(target_os = "macos"))]
pub(crate) fn raise_above_menu_bar(_window: &tauri::WebviewWindow) -> Result<(), String> {
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::main_window_present;

    #[test]
    fn hidden_main_window_means_tray_resident() {
        assert!(!main_window_present(false, false));
    }

    #[test]
    fn visible_main_window_keeps_dock_presence() {
        assert!(main_window_present(true, false));
    }

    /// 最小化窗口 is_visible 为 false，但只能经 Dock 图标恢复：必须视为在场。
    #[test]
    fn minimized_main_window_still_counts_as_present() {
        assert!(main_window_present(false, true));
    }
}
