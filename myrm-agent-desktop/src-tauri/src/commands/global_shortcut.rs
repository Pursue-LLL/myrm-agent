//! 全局快捷键 Tauri 命令
//!
//! [INPUT]
//! - crate::config::ConfigManager (POS: 桌面配置持久化管理，提供回滚用的旧快捷键配置)
//! - crate::runtime::{APPSHOT_SHORTCUT_STR, VOICE_PTT_SHORTCUT_STR, INLINE_INPUT_SHORTCUT_STR} (POS: 各快捷键当前生效值的展示缓存)
//!
//! [OUTPUT]
//! - `update_global_shortcut`: 注销全部旧快捷键后重新注册 toggle + appshot + voice PTT + inline input，注册失败回滚到旧配置
//!
//! [POS]
//! 桌面端全局快捷键 IPC 命令接口。注册与回滚的原子性在此保证，快捷键触发后的分发在 `app/shortcut_handler.rs`。

use crate::config::ConfigManager;

/// 动态更新全局快捷键（注销所有旧快捷键后重新注册 toggle + appshot + voice PTT + inline input）。
/// 注册失败时自动回滚到旧配置，保证原子性。
#[tauri::command]
pub fn update_global_shortcut(
    app: tauri::AppHandle,
    shortcut: String,
    appshot_shortcut: Option<String>,
    voice_ptt_shortcut: Option<String>,
    inline_input_shortcut: Option<String>,
) -> Result<(), String> {
    use tauri::Manager;
    use tauri_plugin_global_shortcut::GlobalShortcutExt;

    let old_config = app.state::<ConfigManager>().load();

    if let Err(e) = app.global_shortcut().unregister_all() {
        eprintln!("Failed to unregister old shortcuts: {}", e);
    }

    let result = register_shortcuts(
        &app,
        &shortcut,
        &appshot_shortcut,
        &voice_ptt_shortcut,
        &inline_input_shortcut,
    );

    if let Err(ref err_msg) = result {
        eprintln!("Shortcut registration failed: {err_msg}, rolling back to old config");
        let _ = app.global_shortcut().unregister_all();
        let _ = register_shortcuts(
            &app,
            &old_config.global_shortcut,
            &Some(old_config.appshot_shortcut),
            &Some(old_config.voice_ptt_shortcut),
            &Some(old_config.inline_input_shortcut),
        );
    }

    result
}

fn register_shortcuts(
    app: &tauri::AppHandle,
    shortcut: &str,
    appshot_shortcut: &Option<String>,
    voice_ptt_shortcut: &Option<String>,
    inline_input_shortcut: &Option<String>,
) -> Result<(), String> {
    use std::str::FromStr;
    use tauri_plugin_global_shortcut::GlobalShortcutExt;

    if !shortcut.is_empty() {
        if let Ok(s) = tauri_plugin_global_shortcut::Shortcut::from_str(shortcut) {
            if let Err(e) = app.global_shortcut().register(s) {
                return Err(format!("Failed to register global shortcut: {}", e));
            }
        } else {
            return Err(format!("Invalid shortcut format: {}", shortcut));
        }
    }

    if let Some(ref appshot) = appshot_shortcut {
        if !appshot.is_empty() {
            if let Ok(s) = tauri_plugin_global_shortcut::Shortcut::from_str(appshot) {
                if let Err(e) = app.global_shortcut().register(s) {
                    return Err(format!("Failed to register appshot shortcut: {}", e));
                }
                if let Ok(mut guard) = crate::runtime::APPSHOT_SHORTCUT_STR.lock() {
                    *guard = format!("{s}");
                }
            } else {
                return Err(format!("Invalid appshot shortcut format: {}", appshot));
            }
        }
    }

    if let Some(ref voice_ptt) = voice_ptt_shortcut {
        if !voice_ptt.is_empty() {
            if let Ok(s) = tauri_plugin_global_shortcut::Shortcut::from_str(voice_ptt) {
                if let Err(e) = app.global_shortcut().register(s) {
                    return Err(format!("Failed to register voice PTT shortcut: {}", e));
                }
                if let Ok(mut guard) = crate::runtime::VOICE_PTT_SHORTCUT_STR.lock() {
                    *guard = format!("{s}");
                }
            } else {
                return Err(format!("Invalid voice PTT shortcut format: {}", voice_ptt));
            }
        }
    }

    if let Some(ref inline_input) = inline_input_shortcut {
        if !inline_input.is_empty() {
            if let Ok(s) = tauri_plugin_global_shortcut::Shortcut::from_str(inline_input) {
                if let Err(e) = app.global_shortcut().register(s) {
                    return Err(format!("Failed to register inline input shortcut: {}", e));
                }
                if let Ok(mut guard) = crate::runtime::INLINE_INPUT_SHORTCUT_STR.lock() {
                    *guard = format!("{s}");
                }
            } else {
                return Err(format!(
                    "Invalid inline input shortcut format: {}",
                    inline_input
                ));
            }
        }
    }

    Ok(())
}
