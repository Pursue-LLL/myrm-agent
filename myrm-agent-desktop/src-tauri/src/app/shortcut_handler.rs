//! 全局快捷键事件分发。

use tauri::AppHandle;
use tauri_plugin_global_shortcut::{Shortcut, ShortcutEvent, ShortcutState};

use crate::runtime::{
    handle_appshot_shortcut, handle_inline_input_shortcut, handle_toggle_window,
    handle_voice_ptt_start, handle_voice_ptt_stop, APPSHOT_SHORTCUT_STR, INLINE_INPUT_SHORTCUT_STR,
    VOICE_PTT_SHORTCUT_STR,
};

pub fn handle_global_shortcut(app: &AppHandle, shortcut: &Shortcut, event: ShortcutEvent) {
    let shortcut_str = format!("{shortcut}");

    let is_voice_ptt = VOICE_PTT_SHORTCUT_STR
        .lock()
        .map_or(false, |saved| !saved.is_empty() && *saved == shortcut_str);

    if is_voice_ptt {
        match event.state {
            ShortcutState::Pressed => handle_voice_ptt_start(app),
            ShortcutState::Released => handle_voice_ptt_stop(app),
        }
        return;
    }

    if event.state != ShortcutState::Pressed {
        return;
    }

    let is_appshot = APPSHOT_SHORTCUT_STR
        .lock()
        .map_or(false, |saved| *saved == shortcut_str);

    let is_inline_input = INLINE_INPUT_SHORTCUT_STR
        .lock()
        .map_or(false, |saved| !saved.is_empty() && *saved == shortcut_str);

    if is_appshot {
        handle_appshot_shortcut(app);
    } else if is_inline_input {
        handle_inline_input_shortcut(app);
    } else {
        handle_toggle_window(app);
    }
}
