//! Desktop pet surface — transparent always-on-top FE webview.
//! Loads `/pet-overlay` and receives live state via Tauri events from the main window.

use tauri::{
    AppHandle, LogicalPosition, LogicalSize, Manager, Position, Size, State, Url, WebviewUrl,
    WebviewWindowBuilder,
};

use crate::runtime::ProductOrigin;

const PET_SURFACE_LABEL: &str = "pet-surface";
const MAIN_WEBVIEW_LABEL: &str = "main";
const PET_OVERLAY_ROUTE: &str = "pet-overlay";

/// 浮层页面地址：产品页来源上的 `/pet-overlay`。发布版的 `WebviewUrl::App` 会回落到壳页
/// （其后跳转只回产品根路径），必须给出完整来源。
fn pet_overlay_url(origin: &ProductOrigin) -> Url {
    origin.page_url(&[PET_OVERLAY_ROUTE], &[])
}

#[derive(Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PetSurfaceBoundsPayload {
    pub x: f64,
    pub y: f64,
    pub width: f64,
    pub height: f64,
}

#[tauri::command]
pub fn show_pet_surface(
    app: AppHandle,
    origin: State<'_, ProductOrigin>,
    payload: PetSurfaceBoundsPayload,
) -> Result<(), String> {
    let width = payload.width.max(64.0);
    let height = payload.height.max(64.0);

    if let Some(window) = app.get_webview_window(PET_SURFACE_LABEL) {
        window
            .set_size(Size::Logical(LogicalSize::new(width, height)))
            .map_err(|error| error.to_string())?;
        window
            .set_position(Position::Logical(LogicalPosition::new(
                payload.x, payload.y,
            )))
            .map_err(|error| error.to_string())?;
        window.show().map_err(|error| error.to_string())?;
        return Ok(());
    }

    let _window = WebviewWindowBuilder::new(
        &app,
        PET_SURFACE_LABEL,
        WebviewUrl::External(pet_overlay_url(&origin)),
    )
    .title("Pet")
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
    .inner_size(width, height)
    .position(payload.x, payload.y)
    .build()
    .map_err(|error| error.to_string())?;

    Ok(())
}

#[tauri::command]
pub fn hide_pet_surface(app: AppHandle) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(PET_SURFACE_LABEL) {
        window.close().map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub fn pet_surface_set_ignore_cursor(app: AppHandle, ignore: bool) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(PET_SURFACE_LABEL) {
        window
            .set_ignore_cursor_events(ignore)
            .map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub fn pet_surface_set_focusable(app: AppHandle, focusable: bool) -> Result<(), String> {
    if let Some(window) = app.get_webview_window(PET_SURFACE_LABEL) {
        window
            .set_focusable(focusable)
            .map_err(|error| error.to_string())?;
        if focusable {
            let _ = window.set_focus();
        }
    }
    Ok(())
}

#[tauri::command]
pub fn pet_surface_focus_main_window(app: AppHandle) -> Result<(), String> {
    if let Some(main) = app.get_webview_window(MAIN_WEBVIEW_LABEL) {
        main.show().map_err(|error| error.to_string())?;
        main.set_focus().map_err(|error| error.to_string())?;
    }
    Ok(())
}

#[tauri::command]
pub fn pet_surface_toggle_main_window(app: AppHandle) -> Result<(), String> {
    if let Some(main) = app.get_webview_window(MAIN_WEBVIEW_LABEL) {
        let visible = main.is_visible().map_err(|error| error.to_string())?;
        if visible {
            main.hide().map_err(|error| error.to_string())?;
        } else {
            main.show().map_err(|error| error.to_string())?;
            main.set_focus().map_err(|error| error.to_string())?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::pet_overlay_url;
    use crate::runtime::ProductOrigin;

    #[test]
    fn pet_overlay_lives_on_the_product_origin() {
        let url = pet_overlay_url(&ProductOrigin::new(4123));
        assert_eq!(url.as_str(), "http://127.0.0.1:4123/pet-overlay");
    }
}
