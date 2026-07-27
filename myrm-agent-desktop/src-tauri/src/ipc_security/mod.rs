//! Centralized desktop IPC sender gate and sensitive-action ticketing.
//!
//! [INPUT]
//! - Tauri invoke metadata (`tauri::ipc::Invoke`, webview label, command name)
//! - Sensitive action ticket requests from trusted main webview
//!
//! [OUTPUT]
//! - `authorize_invoke`: unified invoke sender validation
//! - `handle_denied_invoke`: consistent reject/drop + audit behavior
//! - `issue_sensitive_action_ticket` / `consume_sensitive_ticket`: short-lived intent proof
//! - `ipc-sensitive-confirmation` runtime audit events for sensitive confirmation outcomes
//!
//! [POS]
//! Desktop IPC security boundary.

mod confirmation;
mod policy;
mod ticket_store;

pub use confirmation::require_sensitive_action_confirmation;
pub use policy::{authorize_invoke, handle_denied_invoke};
pub use ticket_store::{consume_sensitive_ticket, issue_sensitive_ticket, SensitiveAction};

#[tauri::command]
pub fn issue_sensitive_action_ticket(
    webview_window: tauri::WebviewWindow,
    action: String,
) -> Result<String, String> {
    if !policy::is_main_webview_label(webview_window.label()) {
        return Err("Sensitive action ticket can only be issued from main webview".to_string());
    }

    let parsed_action = SensitiveAction::from_str(action.as_str())
        .ok_or_else(|| format!("Unsupported sensitive action: {action}"))?;

    issue_sensitive_ticket(parsed_action)
}

#[cfg(test)]
mod tests;
