//! WebUI Remote 模式的 Setup Token 状态

use std::sync::Mutex;
use tauri::State;

/// 前端 WebView 查询后跳转 setup 页面
pub struct SetupTokenState {
    pub token: Mutex<Option<String>>,
}

/// 获取 Setup Token（仅 Tauri WebView 可调用，远程浏览器无法触发）
#[tauri::command]
pub fn get_setup_token(state: State<'_, SetupTokenState>) -> Result<Option<String>, String> {
    let guard = state
        .token
        .lock()
        .map_err(|e| format!("Lock error: {}", e))?;
    Ok(guard.clone())
}
