//! 视觉审批的 OS 级高亮 overlay（仅 macOS）：把 harness 的屏幕坐标或图像坐标映射到最匹配的显示器，
//! 在其上用透明、置顶、点击穿透的窗口画出红色高亮框。
//!
//! 窗口生命周期（页面内容见 `visual_approval_overlay_page.rs`）：
//! - 每次 show 以全新 label 建窗：销毁是异步的，旧窗的 label 在销毁完成前仍被占用，
//!   此时重建同名窗口会失败，高亮就此消失；
//! - 先建新窗再销毁旧窗，换目标时屏幕上没有空档；建窗失败则不留任何高亮窗口；
//! - hide 按 label 前缀销毁全部高亮窗口。销毁而非关闭：关闭只是一次可被拦截的请求，
//!   高亮必须无条件消失（帷幕同理）；
//! - 高亮窗口不受应用级窗口策略（托盘常驻 / 退出编排）管辖，见 `app/setup.rs`；
//! - 窗口点击穿透，因此不进截图排除集：排除集同时驱动 harness 的全局指针守卫，
//!   把它放进去会让 agent 自己的点击被判为被遮挡。
//!
//! 非 macOS 平台 show 返回明确错误（前端应 gate）：建窗只在 macOS 上验证过，且 tauri 文档指出
//! Windows 上在同步命令中建窗会死锁。
//!
//! [INPUT]
//! - 前端 `visualApprovalOsOverlay.ts` 的 payload（POS: 审批目标的屏幕/图像坐标）
//! - visual_approval_overlay_page（POS: 高亮页入口 URL 与高亮框类型）
//!
//! [OUTPUT]
//! - show_visual_approval_overlay / hide_visual_approval_overlay: Tauri 命令
//! - is_overlay_label: 窗口 label 是否属于审批高亮（app/setup.rs 据此豁免应用级窗口策略）
//!
//! [POS]
//! 视觉审批的原生辅助提示，不承担审批决策；overlay 缺席时审批照常在聊天内联界面完成。

use std::sync::atomic::{AtomicU64, Ordering};

use tauri::{AppHandle, Manager, Monitor, WebviewUrl, WebviewWindowBuilder};

use super::visual_approval_overlay_page::{self as page, HighlightBox};

const WINDOW_LABEL_PREFIX: &str = "visual-approval-overlay-";
const SCREEN_MONITOR_TOLERANCE: f64 = 0.05;

/// 窗口 label 的代号：每个高亮窗口独占一个，永不复用。
static WINDOW_GENERATION: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct VisualApprovalOverlayPayload {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
    pub viewport_width: f64,
    pub viewport_height: f64,
    pub coordinate_mode: String,
    pub screen_width: f64,
    pub screen_height: f64,
    pub label: Option<String>,
}

fn scaled_box(
    payload: &VisualApprovalOverlayPayload,
    screen_w: f64,
    screen_h: f64,
) -> HighlightBox {
    if payload.viewport_width <= 0.0 || payload.viewport_height <= 0.0 {
        return HighlightBox {
            x: payload.x,
            y: payload.y,
            width: payload.width,
            height: payload.height,
        };
    }

    let scale_x = screen_w / payload.viewport_width;
    let scale_y = screen_h / payload.viewport_height;

    HighlightBox {
        x: payload.x * scale_x,
        y: payload.y * scale_y,
        width: payload.width * scale_x,
        height: payload.height * scale_y,
    }
}

fn resolve_overlay_box(
    payload: &VisualApprovalOverlayPayload,
    screen_w: f64,
    screen_h: f64,
    monitor_origin_x: f64,
    monitor_origin_y: f64,
) -> HighlightBox {
    if payload.coordinate_mode == "screen" {
        return HighlightBox {
            x: payload.x - monitor_origin_x,
            y: payload.y - monitor_origin_y,
            width: payload.width,
            height: payload.height,
        };
    }

    scaled_box(payload, screen_w, screen_h)
}

fn monitor_dimensions_compatible(
    expected_w: f64,
    expected_h: f64,
    monitor_w: f64,
    monitor_h: f64,
) -> bool {
    if expected_w <= 0.0 || expected_h <= 0.0 {
        return false;
    }

    let width_delta = (monitor_w - expected_w).abs() / expected_w;
    let height_delta = (monitor_h - expected_h).abs() / expected_h;
    width_delta <= SCREEN_MONITOR_TOLERANCE && height_delta <= SCREEN_MONITOR_TOLERANCE
}

fn monitor_match_score(viewport_w: f64, viewport_h: f64, screen_w: f64, screen_h: f64) -> f64 {
    (screen_w - viewport_w).abs() + (screen_h - viewport_h).abs()
}

fn monitor_for_viewport(
    app: &AppHandle,
    viewport_w: f64,
    viewport_h: f64,
) -> Result<Monitor, String> {
    let monitors = app
        .available_monitors()
        .map_err(|error| error.to_string())?;

    monitors
        .into_iter()
        .min_by(|left, right| {
            let left_size = left.size();
            let right_size = right.size();
            let left_score = monitor_match_score(
                viewport_w,
                viewport_h,
                left_size.width as f64 / left.scale_factor(),
                left_size.height as f64 / left.scale_factor(),
            );
            let right_score = monitor_match_score(
                viewport_w,
                viewport_h,
                right_size.width as f64 / right.scale_factor(),
                right_size.height as f64 / right.scale_factor(),
            );
            left_score
                .partial_cmp(&right_score)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .ok_or_else(|| "No monitors available".to_string())
}

fn monitor_match_dimensions(payload: &VisualApprovalOverlayPayload) -> (f64, f64) {
    if payload.coordinate_mode == "screen" {
        return (payload.screen_width, payload.screen_height);
    }

    (payload.viewport_width, payload.viewport_height)
}

fn next_window_label() -> String {
    format!(
        "{WINDOW_LABEL_PREFIX}{}",
        WINDOW_GENERATION.fetch_add(1, Ordering::Relaxed)
    )
}

/// 窗口 label 是否属于审批高亮（label 前缀的唯一定义处）。
pub(crate) fn is_overlay_label(label: &str) -> bool {
    label.starts_with(WINDOW_LABEL_PREFIX)
}

/// 在匹配的显示器上建一扇点击穿透的高亮窗口，返回其 label。
fn open_overlay_window(
    app: &AppHandle,
    payload: &VisualApprovalOverlayPayload,
) -> Result<String, String> {
    let (match_w, match_h) = monitor_match_dimensions(payload);
    let monitor = monitor_for_viewport(app, match_w, match_h)?;

    let scale_factor = monitor.scale_factor();
    let position = monitor.position();
    let size = monitor.size();

    let screen_w = size.width as f64 / scale_factor;
    let screen_h = size.height as f64 / scale_factor;
    let pos_x = position.x as f64 / scale_factor;
    let pos_y = position.y as f64 / scale_factor;

    if payload.coordinate_mode == "screen"
        && !monitor_dimensions_compatible(
            payload.screen_width,
            payload.screen_height,
            screen_w,
            screen_h,
        )
    {
        return Err("Screen dimensions mismatch; overlay suppressed".to_string());
    }

    let highlight = resolve_overlay_box(payload, screen_w, screen_h, pos_x, pos_y);
    let page_url = page::url(highlight, payload.label.as_deref())?;
    let label = next_window_label();

    let window = WebviewWindowBuilder::new(app, &label, WebviewUrl::CustomProtocol(page_url))
        .title("Visual Approval Overlay")
        .transparent(true)
        .always_on_top(true)
        .decorations(false)
        .skip_taskbar(true)
        .focused(false)
        .visible(true)
        .resizable(false)
        .maximizable(false)
        .minimizable(false)
        .closable(false)
        .inner_size(screen_w, screen_h)
        .position(pos_x, pos_y)
        .build()
        .map_err(|error| error.to_string())?;

    window
        .set_ignore_cursor_events(true)
        .map_err(|error| error.to_string())?;

    Ok(label)
}

/// 销毁全部高亮窗口（label 前缀匹配），`keep` 指定的窗口除外。
fn destroy_overlay_windows(app: &AppHandle, keep: Option<&str>) -> Result<(), String> {
    for (label, window) in app.webview_windows() {
        if is_overlay_label(&label) && Some(label.as_str()) != keep {
            window.destroy().map_err(|error| error.to_string())?;
        }
    }
    Ok(())
}

#[tauri::command]
pub fn show_visual_approval_overlay(
    app: AppHandle,
    payload: VisualApprovalOverlayPayload,
) -> Result<(), String> {
    if !cfg!(target_os = "macos") {
        return Err(
            "visual approval OS overlay is only supported on macOS (Windows sync window creation can deadlock)"
                .to_string(),
        );
    }

    match open_overlay_window(&app, &payload) {
        Ok(label) => destroy_overlay_windows(&app, Some(label.as_str())),
        Err(error) => {
            // 失败后屏幕上也不应残留上一个审批目标的高亮，更不能留下一扇抢点击的半成品窗口。
            let _ = destroy_overlay_windows(&app, None);
            Err(error)
        }
    }
}

#[tauri::command]
pub fn hide_visual_approval_overlay(app: AppHandle) -> Result<(), String> {
    destroy_overlay_windows(&app, None)
}

#[cfg(test)]
mod tests {
    use super::{
        is_overlay_label, monitor_dimensions_compatible, monitor_match_score, next_window_label,
        resolve_overlay_box, scaled_box, VisualApprovalOverlayPayload,
    };

    fn sample_payload(coordinate_mode: &str) -> VisualApprovalOverlayPayload {
        VisualApprovalOverlayPayload {
            x: 100.0,
            y: 200.0,
            width: 50.0,
            height: 40.0,
            viewport_width: 1000.0,
            viewport_height: 500.0,
            coordinate_mode: coordinate_mode.to_string(),
            screen_width: 1440.0,
            screen_height: 900.0,
            label: None,
        }
    }

    #[test]
    fn scales_bbox_to_screen_coordinates_for_image_mode() {
        let payload = sample_payload("image");
        let bounds = scaled_box(&payload, 2000.0, 1000.0);
        assert!((bounds.x - 200.0).abs() < f64::EPSILON);
        assert!((bounds.y - 400.0).abs() < f64::EPSILON);
        assert!((bounds.width - 100.0).abs() < f64::EPSILON);
        assert!((bounds.height - 80.0).abs() < f64::EPSILON);
    }

    #[test]
    fn screen_mode_uses_absolute_coordinates_without_scaling() {
        let payload = VisualApprovalOverlayPayload {
            x: 500.0,
            y: 300.0,
            width: 40.0,
            height: 30.0,
            viewport_width: 1280.0,
            viewport_height: 800.0,
            coordinate_mode: "screen".to_string(),
            screen_width: 1440.0,
            screen_height: 900.0,
            label: None,
        };

        let bounds = resolve_overlay_box(&payload, 1440.0, 900.0, 0.0, 0.0);
        assert!((bounds.x - 500.0).abs() < f64::EPSILON);
        assert!((bounds.y - 300.0).abs() < f64::EPSILON);
        assert!((bounds.width - 40.0).abs() < f64::EPSILON);
        assert!((bounds.height - 30.0).abs() < f64::EPSILON);
    }

    #[test]
    fn screen_mode_offsets_bbox_by_monitor_origin() {
        let payload = VisualApprovalOverlayPayload {
            x: 500.0,
            y: 300.0,
            width: 40.0,
            height: 30.0,
            viewport_width: 1280.0,
            viewport_height: 800.0,
            coordinate_mode: "screen".to_string(),
            screen_width: 1440.0,
            screen_height: 900.0,
            label: None,
        };

        let bounds = resolve_overlay_box(&payload, 1440.0, 900.0, 100.0, 50.0);
        assert!((bounds.x - 400.0).abs() < f64::EPSILON);
        assert!((bounds.y - 250.0).abs() < f64::EPSILON);
    }

    #[test]
    fn prefers_monitor_with_closest_viewport_dimensions() {
        let exact = monitor_match_score(1920.0, 1080.0, 1920.0, 1080.0);
        let mismatch = monitor_match_score(1920.0, 1080.0, 2560.0, 1440.0);

        assert!(exact < mismatch);
    }

    #[test]
    fn rejects_monitor_when_screen_dimensions_differ_too_much() {
        assert!(!monitor_dimensions_compatible(
            1440.0, 900.0, 1920.0, 1080.0
        ));
        assert!(monitor_dimensions_compatible(1440.0, 900.0, 1450.0, 905.0));
    }

    /// 同名重建会撞上尚未异步销毁完的旧窗口，因此 label 永不复用；hide 与应用级窗口策略的豁免
    /// 都靠同一前缀识别高亮窗口。
    #[test]
    fn every_window_gets_a_fresh_label_the_overlay_predicate_recognises() {
        let first = next_window_label();
        let second = next_window_label();

        assert_ne!(first, second);
        assert!(is_overlay_label(&first));
        assert!(is_overlay_label(&second));
    }

    #[test]
    fn the_overlay_predicate_does_not_claim_other_windows() {
        for label in ["main", "pet-surface", "session-42", "privacy-curtain-1-0"] {
            assert!(!is_overlay_label(label), "{label}");
        }
    }
}
