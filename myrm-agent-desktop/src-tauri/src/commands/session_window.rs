//! Session detach window — opens a chat session in a focused standalone window.
//!
//! Session window — spawns a secondary WebviewWindow for multi-session CLI agents.
//! Uses the same WebviewWindowBuilder pattern as `pet_surface.rs` but loads the
//! frontend in focused mode (no sidebar, session-only view).

use tauri::{AppHandle, Manager, State, Url, WebviewUrl, WebviewWindowBuilder};

use crate::runtime::ProductOrigin;

const SESSION_WINDOW_PREFIX: &str = "session-";

fn session_window_label(session_id: &str) -> String {
    format!("{SESSION_WINDOW_PREFIX}{session_id}")
}

/// 会话窗口页面地址：产品页来源上的 `/<session_id>?mode=focused`。发布版的 `WebviewUrl::App`
/// 会回落到壳页（其后跳转只回产品根路径），必须给出完整来源；会话 ID 经百分号编码，逃不出所在路径段。
fn session_window_url(origin: &ProductOrigin, session_id: &str) -> Url {
    origin.page_url(&[session_id], &[("mode", "focused")])
}

#[tauri::command]
pub fn open_session_window(
    app: AppHandle,
    origin: State<'_, ProductOrigin>,
    session_id: String,
) -> Result<(), String> {
    let label = session_window_label(&session_id);

    if let Some(existing) = app.get_webview_window(&label) {
        existing.set_focus().map_err(|e| e.to_string())?;
        return Ok(());
    }

    let url = session_window_url(&origin, &session_id);

    let _window = WebviewWindowBuilder::new(&app, &label, WebviewUrl::External(url))
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

#[cfg(test)]
mod tests {
    use super::session_window_url;
    use crate::runtime::ProductOrigin;

    #[test]
    fn session_window_opens_the_focused_session_route() {
        let url = session_window_url(&ProductOrigin::new(3777), "chat-1");
        assert_eq!(url.as_str(), "http://127.0.0.1:3777/chat-1?mode=focused");
    }

    #[test]
    fn session_id_cannot_redirect_the_window_off_the_product_origin() {
        let url = session_window_url(&ProductOrigin::new(3777), "x/../?y#z@evil.example");
        assert_eq!(url.host_str(), Some("127.0.0.1"));
        assert_eq!(url.port(), Some(3777));
        assert_eq!(url.fragment(), None);
        assert_eq!(url.query(), Some("mode=focused"));
        assert_eq!(url.path_segments().map(Iterator::count), Some(1));
    }
}
