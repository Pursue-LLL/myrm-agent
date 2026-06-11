//! Session detach window — opens a chat session in a focused standalone window.
//!
//! Uses the same WebviewWindowBuilder pattern as `pet_overlay.rs` but loads the
//! frontend in focused mode (no sidebar, session-only view).

use tauri::{AppHandle, Manager, WebviewUrl, WebviewWindowBuilder};

const SESSION_WINDOW_PREFIX: &str = "session-";

fn session_window_label(session_id: &str) -> String {
    format!("{SESSION_WINDOW_PREFIX}{session_id}")
}

#[tauri::command]
pub fn open_session_window(app: AppHandle, session_id: String) -> Result<(), String> {
    let label = session_window_label(&session_id);

    if let Some(existing) = app.get_webview_window(&label) {
        existing.set_focus().map_err(|e| e.to_string())?;
        return Ok(());
    }

    let url = format!("/{}?mode=focused", session_id);

    let _window = WebviewWindowBuilder::new(&app, &label, WebviewUrl::App(url.into()))
        .title("MyrmAgent")
        .inner_size(900.0, 700.0)
        .min_inner_size(600.0, 400.0)
        .resizable(true)
        .maximizable(true)
        .minimizable(true)
        .closable(true)
        .focused(true)
        .visible(true)
        .build()
        .map_err(|e| e.to_string())?;

    Ok(())
}

#[tauri::command]
pub fn close_session_window(app: AppHandle, session_id: String) -> Result<(), String> {
    let label = session_window_label(&session_id);
    if let Some(window) = app.get_webview_window(&label) {
        window.close().map_err(|e| e.to_string())?;
    }
    Ok(())
}
