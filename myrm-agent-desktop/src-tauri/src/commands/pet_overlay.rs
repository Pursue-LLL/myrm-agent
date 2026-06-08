//! Desktop pet overlay — transparent always-on-top window for animated pet sprite.
//!
//! Reuses the Tauri transparent-window pattern from `visual_approval_overlay.rs`
//! but renders a self-contained HTML page with a Canvas 2D sprite engine.
//! The overlay receives pet events via Tauri `emit`/`listen`.

use base64::{engine::general_purpose::STANDARD, Engine as _};
use tauri::{AppHandle, Emitter, Manager, Url, WebviewUrl, WebviewWindowBuilder};

const PET_OVERLAY_LABEL: &str = "pet-overlay";
const PET_WINDOW_SIZE: f64 = 128.0;

#[derive(Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PetOverlayPayload {
    pub sheet_url: String,
    pub size: Option<f64>,
    pub initial_row: Option<u32>,
}

fn html_escape_attr(input: &str) -> String {
    input
        .replace('&', "&amp;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

fn pet_overlay_html(sheet_url: &str, size: f64, initial_row: u32) -> String {
    let safe_url = html_escape_attr(sheet_url);
    format!(
        r#"<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  html, body {{
    margin: 0; padding: 0;
    width: 100%; height: 100%;
    overflow: hidden;
    background: transparent;
    user-select: none;
    -webkit-user-select: none;
  }}
  canvas {{
    width: {size:.0}px;
    height: {size:.0}px;
    image-rendering: pixelated;
    image-rendering: crisp-edges;
  }}
</style>
</head>
<body data-sheet-url="{safe_url}" data-initial-row="{initial_row}">
<canvas id="pet" width="192" height="208"></canvas>
<script>
(function() {{
  var canvas = document.getElementById('pet');
  var ctx = canvas.getContext('2d', {{ alpha: true }});
  ctx.imageSmoothingEnabled = false;
  var img = new Image();
  var cols = 8, cellW = 192, cellH = 208;
  var currentRow = parseInt(document.body.dataset.initialRow, 10) || 0;
  var currentFrame = 0;
  var ready = false;

  img.crossOrigin = 'anonymous';
  img.onload = function() {{
    ready = true;
    renderFrame();
  }};
  img.onerror = function() {{
    ctx.fillStyle = 'rgba(255,0,0,0.3)';
    ctx.fillRect(0, 0, cellW, cellH);
    ctx.fillStyle = '#fff';
    ctx.font = '24px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('!', cellW/2, cellH/2 + 8);
  }};
  img.src = document.body.dataset.sheetUrl || '';

  function renderFrame() {{
    if (!ready) return;
    var col = currentFrame % cols;
    ctx.clearRect(0, 0, cellW, cellH);
    ctx.drawImage(img, col * cellW, currentRow * cellH, cellW, cellH, 0, 0, cellW, cellH);
  }}

  setInterval(function() {{
    if (!ready) return;
    currentFrame = (currentFrame + 1) % cols;
    renderFrame();
  }}, 166); // ~6fps

  // Listen for row changes from main window
  if (window.__TAURI__) {{
    window.__TAURI__.event.listen('pet-set-row', function(event) {{
      var row = Number(event.payload);
      if (!isNaN(row) && row >= 0) {{
        currentRow = row;
        currentFrame = 0;
        renderFrame();
      }}
    }});
    window.__TAURI__.event.listen('pet-update-sheet', function(event) {{
      var url = event.payload;
      if (typeof url === 'string' && url) {{
        ready = false;
        img.src = url;
      }}
    }});
  }}

  // Drag support
  var dragging = false, startX = 0, startY = 0;
  document.addEventListener('pointerdown', function(e) {{
    if (e.button !== 0) return;
    dragging = true;
    startX = e.screenX;
    startY = e.screenY;
    document.body.setPointerCapture(e.pointerId);
  }});
  document.addEventListener('pointermove', function(e) {{
    if (!dragging) return;
    var dx = e.screenX - startX;
    var dy = e.screenY - startY;
    if (Math.abs(dx) > 2 || Math.abs(dy) > 2) {{
      if (window.__TAURI__) {{
        window.__TAURI__.window.getCurrent().setPosition(
          new window.__TAURI__.window.PhysicalPosition(
            window.screenX + dx,
            window.screenY + dy
          )
        );
      }}
      startX = e.screenX;
      startY = e.screenY;
    }}
  }});
  document.addEventListener('pointerup', function(e) {{
    dragging = false;
    try {{ document.body.releasePointerCapture(e.pointerId); }} catch(ex) {{}}
  }});
}})();
</script>
</body>
</html>"#,
        safe_url = safe_url,
        size = size,
        initial_row = initial_row,
    )
}

#[tauri::command]
pub fn show_pet_overlay(
    app: AppHandle,
    payload: PetOverlayPayload,
) -> Result<(), String> {
    hide_pet_overlay(app.clone())?;

    let size = payload.size.unwrap_or(PET_WINDOW_SIZE);
    let initial_row = payload.initial_row.unwrap_or(0);

    let html = pet_overlay_html(&payload.sheet_url, size, initial_row);
    let data_url = format!(
        "data:text/html;base64,{}",
        STANDARD.encode(html.as_bytes())
    );
    let overlay_url = Url::parse(&data_url).map_err(|e| e.to_string())?;

    let _window = WebviewWindowBuilder::new(
        &app,
        PET_OVERLAY_LABEL,
        WebviewUrl::CustomProtocol(overlay_url),
    )
    .title("Pet Overlay")
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
    .inner_size(size, size)
    .build()
    .map_err(|e| e.to_string())?;

    Ok(())
}

#[tauri::command]
pub fn hide_pet_overlay(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(PET_OVERLAY_LABEL) {
        window.close().map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub fn pet_overlay_set_row(app: AppHandle, row: u32) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(PET_OVERLAY_LABEL) {
        window.emit("pet-set-row", row).map_err(|e| e.to_string())?;
    }
    Ok(())
}
