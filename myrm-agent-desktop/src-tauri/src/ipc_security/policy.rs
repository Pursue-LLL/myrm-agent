use serde::Serialize;
use tauri::ipc::Invoke;

const MAIN_WEBVIEW_LABEL: &str = "main";
const SESSION_WEBVIEW_PREFIX: &str = "session-";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CommandRisk {
    ReadOnly,
    Stateful,
    Critical,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DenyMode {
    Reject,
    Drop,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SurfacePolicy {
    MainOnly,
    MainOrSession,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct CommandPolicy {
    surface: SurfacePolicy,
    risk: CommandRisk,
    deny_mode: DenyMode,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeniedInvoke {
    pub command: String,
    pub webview_label: String,
    pub reason_code: &'static str,
    pub reason: String,
    pub risk: CommandRisk,
    pub deny_mode: DenyMode,
}

#[derive(Debug, Serialize)]
struct InvokeDeniedPayload {
    code: &'static str,
    command: String,
    webview_label: String,
    message: String,
}

fn policy_for_command(command: &str) -> Option<CommandPolicy> {
    let read_only = matches!(
        command,
        "load_system_config"
            | "get_current_mode"
            | "get_local_ip"
            | "get_setup_token"
            | "check_backend_health"
            | "get_backend_status"
            | "detect_agents"
            | "list_agent_adapters"
            | "get_agent_sidecar_status"
            | "list_agent_sessions"
            | "get_agent_session"
            | "get_permission_mode"
            | "power_lock_status"
            | "screen_is_locked"
            | "screen_lock_has_password"
            | "screen_lock_platform_support"
    );

    let critical = matches!(
        command,
        "fix_quarantine_with_auth"
            | "save_system_config"
            | "reset_system_config"
            | "restart_app"
            | "update_global_shortcut"
            | "start_backend"
            | "stop_backend"
            | "stop_frontend"
            | "force_appshot_capture"
            | "migrate_data_dir"
            | "export_local_sqlite"
            | "reveal_app_folder"
            | "power_lock_acquire"
            | "power_lock_release"
            | "screen_unlock"
            | "screen_relock"
            | "screen_lock_store_password"
            | "screen_lock_delete_password"
            | "issue_sensitive_action_ticket"
    );

    let stateful = matches!(
        command,
        "inline_paste_back"
            | "create_agent_session"
            | "delete_agent_session"
            | "resume_agent_session"
            | "send_agent_message"
            | "stop_agent_message"
            | "respond_agent_permission"
            | "set_permission_mode"
            | "cycle_permission_mode"
            | "show_visual_approval_overlay"
            | "hide_visual_approval_overlay"
            | "show_pet_overlay"
            | "hide_pet_overlay"
            | "pet_overlay_set_row"
            | "open_session_window"
            | "close_session_window"
            | "set_tray_status"
    );

    if !(read_only || critical || stateful) {
        return None;
    }

    let risk = if critical {
        CommandRisk::Critical
    } else if read_only {
        CommandRisk::ReadOnly
    } else {
        CommandRisk::Stateful
    };

    let surface = if matches!(
        command,
        "fix_quarantine_with_auth"
            | "save_system_config"
            | "reset_system_config"
            | "restart_app"
            | "update_global_shortcut"
            | "start_backend"
            | "stop_backend"
            | "stop_frontend"
            | "open_session_window"
            | "close_session_window"
            | "force_appshot_capture"
            | "migrate_data_dir"
            | "export_local_sqlite"
            | "reveal_app_folder"
            | "issue_sensitive_action_ticket"
    ) {
        SurfacePolicy::MainOnly
    } else {
        SurfacePolicy::MainOrSession
    };

    let deny_mode = if command == "set_tray_status" {
        DenyMode::Drop
    } else {
        DenyMode::Reject
    };

    Some(CommandPolicy {
        surface,
        risk,
        deny_mode,
    })
}

pub(super) fn is_main_webview_label(label: &str) -> bool {
    label == MAIN_WEBVIEW_LABEL
}

fn is_session_webview_label(label: &str) -> bool {
    label.starts_with(SESSION_WEBVIEW_PREFIX)
}

pub fn authorize_request(command: &str, webview_label: &str) -> Result<(), DeniedInvoke> {
    let Some(policy) = policy_for_command(command) else {
        return Err(DeniedInvoke {
            command: command.to_string(),
            webview_label: webview_label.to_string(),
            reason_code: "unknown_command",
            reason: "IPC command is not in the registered allowlist".to_string(),
            risk: CommandRisk::Critical,
            deny_mode: DenyMode::Reject,
        });
    };

    let is_main = is_main_webview_label(webview_label);
    let is_session = is_session_webview_label(webview_label);

    if !is_main && !is_session {
        return Err(DeniedInvoke {
            command: command.to_string(),
            webview_label: webview_label.to_string(),
            reason_code: "untrusted_webview",
            reason: "IPC caller webview is not trusted".to_string(),
            risk: policy.risk,
            deny_mode: policy.deny_mode,
        });
    }

    if matches!(policy.surface, SurfacePolicy::MainOnly) && !is_main {
        return Err(DeniedInvoke {
            command: command.to_string(),
            webview_label: webview_label.to_string(),
            reason_code: "main_only_command",
            reason: "IPC command is restricted to main webview".to_string(),
            risk: policy.risk,
            deny_mode: policy.deny_mode,
        });
    }

    Ok(())
}

pub fn authorize_invoke(invoke: &Invoke) -> Result<(), DeniedInvoke> {
    let command = invoke.message.command();
    let webview_label = invoke.message.webview_ref().label();
    authorize_request(command, webview_label)
}

fn audit_denied(denied: &DeniedInvoke) {
    eprintln!(
        "[ipc-security] deny command={} webview={} reason={} risk={:?} mode={:?}",
        denied.command, denied.webview_label, denied.reason_code, denied.risk, denied.deny_mode
    );
}

pub fn handle_denied_invoke(invoke: Invoke, denied: DeniedInvoke) {
    audit_denied(&denied);
    match denied.deny_mode {
        DenyMode::Drop => {
            invoke.resolver.resolve(());
        }
        DenyMode::Reject => {
            invoke.resolver.reject(InvokeDeniedPayload {
                code: denied.reason_code,
                command: denied.command,
                webview_label: denied.webview_label,
                message: denied.reason,
            });
        }
    }
}
