//! Native OS overlay for desktop visual tool approvals (BBox highlight).
//!
//! Maps screenshot viewport coordinates to the closest matching monitor and renders a
//! transparent always-on-top window with a red highlight frame.

use base64::{engine::general_purpose::STANDARD, Engine as _};
use tauri::{AppHandle, Manager, Monitor, Url, WebviewUrl, WebviewWindowBuilder};

const OVERLAY_WINDOW_LABEL: &str = "visual-approval-overlay";

#[derive(Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct VisualApprovalOverlayPayload {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
    pub viewport_width: f64,
    pub viewport_height: f64,
    pub label: Option<String>,
}

fn scaled_box(payload: &VisualApprovalOverlayPayload, screen_w: f64, screen_h: f64) -> (f64, f64, f64, f64) {
    if payload.viewport_width <= 0.0 || payload.viewport_height <= 0.0 {
        return (payload.x, payload.y, payload.width, payload.height);
    }

    let scale_x = screen_w / payload.viewport_width;
    let scale_y = screen_h / payload.viewport_height;

    (
        payload.x * scale_x,
        payload.y * scale_y,
        payload.width * scale_x,
        payload.height * scale_y,
    )
}

fn overlay_html(payload: &VisualApprovalOverlayPayload, screen_w: f64, screen_h: f64) -> String {
    let (bx, by, bw, bh) = scaled_box(payload, screen_w, screen_h);
    let label = payload.label.as_deref().unwrap_or("").trim();
    let label_html = if label.is_empty() {
        String::new()
    } else {
        format!(
            r#"<div class="label" style="left:{:.2}px;top:{:.2}px;">{}</div>"#,
            bx,
            (by - 24.0).max(0.0),
            html_escape(label),
        )
    };

    format!(
        r#"<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{
      margin: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: transparent;
    }}
    .shade {{
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.18);
      pointer-events: none;
    }}
    .box {{
      position: fixed;
      border: 3px solid #ef4444;
      border-radius: 6px;
      box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.35), 0 0 24px rgba(239, 68, 68, 0.45);
      pointer-events: none;
      box-sizing: border-box;
    }}
    .label {{
      position: fixed;
      color: #fff;
      background: rgba(220, 38, 38, 0.92);
      font: 600 12px/1.2 system-ui, -apple-system, sans-serif;
      padding: 4px 8px;
      border-radius: 6px;
      pointer-events: none;
      max-width: 320px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
  </style>
</head>
<body>
  <div class="shade"></div>
  <div class="box" style="left:{bx:.2}px;top:{by:.2}px;width:{bw:.2}px;height:{bh:.2}px;"></div>
  {label_html}
</body>
</html>"#
    )
}

fn html_escape(input: &str) -> String {
    input
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
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

#[tauri::command]
pub fn show_visual_approval_overlay(
    app: AppHandle,
    payload: VisualApprovalOverlayPayload,
) -> Result<(), String> {
    hide_visual_approval_overlay(app.clone())?;

    let monitor = monitor_for_viewport(
        &app,
        payload.viewport_width,
        payload.viewport_height,
    )?;

    let scale_factor = monitor.scale_factor();
    let position = monitor.position();
    let size = monitor.size();

    let screen_w = size.width as f64 / scale_factor;
    let screen_h = size.height as f64 / scale_factor;
    let pos_x = position.x as f64 / scale_factor;
    let pos_y = position.y as f64 / scale_factor;

    let html = overlay_html(&payload, screen_w, screen_h);
    let data_url = format!(
        "data:text/html;base64,{}",
        STANDARD.encode(html.as_bytes())
    );
    let overlay_url = Url::parse(&data_url).map_err(|error| error.to_string())?;

    let window = WebviewWindowBuilder::new(
        &app,
        OVERLAY_WINDOW_LABEL,
        WebviewUrl::CustomProtocol(overlay_url),
    )
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

    Ok(())
}

#[tauri::command]
pub fn hide_visual_approval_overlay(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(OVERLAY_WINDOW_LABEL) {
        window.close().map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{monitor_match_score, scaled_box, VisualApprovalOverlayPayload};

    #[test]
    fn scales_bbox_to_screen_coordinates() {
        let payload = VisualApprovalOverlayPayload {
            x: 100.0,
            y: 200.0,
            width: 50.0,
            height: 40.0,
            viewport_width: 1000.0,
            viewport_height: 500.0,
            label: None,
        };

        let (x, y, w, h) = scaled_box(&payload, 2000.0, 1000.0);
        assert!((x - 200.0).abs() < f64::EPSILON);
        assert!((y - 400.0).abs() < f64::EPSILON);
        assert!((w - 100.0).abs() < f64::EPSILON);
        assert!((h - 80.0).abs() < f64::EPSILON);
    }

    #[test]
    fn prefers_monitor_with_closest_viewport_dimensions() {
        let exact = monitor_match_score(1920.0, 1080.0, 1920.0, 1080.0);
        let mismatch = monitor_match_score(1920.0, 1080.0, 2560.0, 1440.0);

        assert!(exact < mismatch);
    }
}
