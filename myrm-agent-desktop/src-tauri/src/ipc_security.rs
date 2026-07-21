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

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::{ipc::Invoke, Emitter, Manager};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
use tokio::sync::oneshot;
use uuid::Uuid;

const MAIN_WEBVIEW_LABEL: &str = "main";
const SESSION_WEBVIEW_PREFIX: &str = "session-";
const SENSITIVE_TICKET_TTL: Duration = Duration::from_secs(30);
const MAX_PENDING_SENSITIVE_TICKETS: usize = 256;
const IPC_SENSITIVE_CONFIRMATION_AUDIT_EVENT: &str = "ipc-sensitive-confirmation";

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

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SensitiveAction {
    MigrateDataDir,
    ExportLocalSqlite,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ConfirmationLocale {
    En,
    ZhHans,
    ZhHant,
    Ja,
    Ko,
    De,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
enum ConfirmationOutcome {
    Prompted,
    Confirmed,
    Cancelled,
    TimedOut,
    ChannelClosed,
}

#[derive(Debug, Serialize)]
struct SensitiveConfirmationAuditPayload {
    action: &'static str,
    locale: &'static str,
    target_preview: String,
    parent_bound: bool,
    outcome: ConfirmationOutcome,
}

#[derive(Debug, Clone, Copy)]
struct ConfirmationCopy {
    title: &'static str,
    continue_label: &'static str,
    cancel_label: &'static str,
    prompt_intro: &'static str,
    prompt_target: &'static str,
    prompt_hint: &'static str,
    timeout_error: &'static str,
    receive_error: &'static str,
    cancelled_error: &'static str,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ConfirmationDialogRequest {
    message: String,
    title: String,
    continue_label: String,
    cancel_label: String,
    parent_bound: bool,
}

impl SensitiveAction {
    fn from_str(value: &str) -> Option<Self> {
        match value {
            "migrate_data_dir" => Some(Self::MigrateDataDir),
            "export_local_sqlite" => Some(Self::ExportLocalSqlite),
            _ => None,
        }
    }

    fn as_str(self) -> &'static str {
        match self {
            Self::MigrateDataDir => "migrate_data_dir",
            Self::ExportLocalSqlite => "export_local_sqlite",
        }
    }

    fn confirmation_label(self, locale: ConfirmationLocale) -> &'static str {
        match locale {
            ConfirmationLocale::ZhHans => match self {
                Self::MigrateDataDir => "迁移数据目录",
                Self::ExportLocalSqlite => "导出本地 SQLite",
            },
            ConfirmationLocale::ZhHant => match self {
                Self::MigrateDataDir => "遷移資料目錄",
                Self::ExportLocalSqlite => "匯出本機 SQLite",
            },
            ConfirmationLocale::Ja => match self {
                Self::MigrateDataDir => "データディレクトリを移行",
                Self::ExportLocalSqlite => "ローカル SQLite をエクスポート",
            },
            ConfirmationLocale::Ko => match self {
                Self::MigrateDataDir => "데이터 디렉터리 이동",
                Self::ExportLocalSqlite => "로컬 SQLite 내보내기",
            },
            ConfirmationLocale::De => match self {
                Self::MigrateDataDir => "Datenverzeichnis migrieren",
                Self::ExportLocalSqlite => "Lokale SQLite exportieren",
            },
            ConfirmationLocale::En => match self {
                Self::MigrateDataDir => "Migrate Data Directory",
                Self::ExportLocalSqlite => "Export Local SQLite",
            },
        }
    }
}

#[derive(Debug, Clone)]
struct TicketEntry {
    action: SensitiveAction,
    expires_at: Instant,
}

#[derive(Debug, Default)]
struct TicketStore {
    entries: HashMap<String, TicketEntry>,
}

impl TicketStore {
    fn issue(&mut self, action: SensitiveAction) -> Result<String, String> {
        self.issue_with_ttl(action, SENSITIVE_TICKET_TTL)
    }

    fn issue_with_ttl(&mut self, action: SensitiveAction, ttl: Duration) -> Result<String, String> {
        self.prune_expired();
        if self.entries.len() >= MAX_PENDING_SENSITIVE_TICKETS {
            return Err("Too many pending sensitive action tickets; please retry".to_string());
        }
        let ticket = Uuid::new_v4().to_string();
        let entry = TicketEntry {
            action,
            expires_at: Instant::now() + ttl,
        };
        self.entries.insert(ticket.clone(), entry);
        Ok(ticket)
    }

    fn consume(&mut self, action: SensitiveAction, ticket: &str) -> Result<(), String> {
        self.prune_expired();
        let entry = self.entries.remove(ticket).ok_or_else(|| {
            "Sensitive action ticket is missing, expired, or already used".to_string()
        })?;

        if entry.action != action {
            return Err(format!(
                "Sensitive action ticket mismatch: expected {}, got {}",
                action.as_str(),
                entry.action.as_str()
            ));
        }

        Ok(())
    }

    fn prune_expired(&mut self) {
        let now = Instant::now();
        self.entries.retain(|_, entry| entry.expires_at > now);
    }
}

static TICKETS: OnceLock<Mutex<TicketStore>> = OnceLock::new();

fn ticket_store() -> &'static Mutex<TicketStore> {
    TICKETS.get_or_init(|| Mutex::new(TicketStore::default()))
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

fn is_main_webview_label(label: &str) -> bool {
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

pub fn issue_sensitive_ticket(action: SensitiveAction) -> Result<String, String> {
    let mut store = ticket_store()
        .lock()
        .map_err(|_| "Failed to lock sensitive ticket store".to_string())?;
    store.issue(action)
}

pub fn consume_sensitive_ticket(action: SensitiveAction, ticket: &str) -> Result<(), String> {
    let mut store = ticket_store()
        .lock()
        .map_err(|_| "Failed to lock sensitive ticket store".to_string())?;
    store.consume(action, ticket)
}

fn truncate_target_for_prompt(target_path: Option<&str>) -> String {
    let Some(path) = target_path.map(str::trim).filter(|value| !value.is_empty()) else {
        return "N/A".to_string();
    };
    if path.chars().count() <= 160 {
        return path.to_string();
    }
    let mut truncated = path.chars().take(157).collect::<String>();
    truncated.push_str("...");
    truncated
}

fn parse_confirmation_locale(raw: Option<&str>) -> ConfirmationLocale {
    let Some(raw_value) = raw else {
        return ConfirmationLocale::En;
    };
    let normalized = raw_value.trim().replace('_', "-").to_ascii_lowercase();
    if normalized.is_empty() {
        return ConfirmationLocale::En;
    }
    if normalized.starts_with("zh") {
        if normalized.contains("hant")
            || normalized.contains("tw")
            || normalized.contains("hk")
            || normalized.contains("mo")
        {
            return ConfirmationLocale::ZhHant;
        }
        return ConfirmationLocale::ZhHans;
    }
    if normalized.starts_with("ja") {
        return ConfirmationLocale::Ja;
    }
    if normalized.starts_with("ko") {
        return ConfirmationLocale::Ko;
    }
    if normalized.starts_with("de") {
        return ConfirmationLocale::De;
    }
    ConfirmationLocale::En
}

fn resolve_confirmation_locale() -> ConfirmationLocale {
    for candidate in [
        std::env::var("MYRM_UI_LOCALE").ok(),
        std::env::var("MYRM_LOCALE").ok(),
        std::env::var("LC_ALL").ok(),
        std::env::var("LC_MESSAGES").ok(),
        std::env::var("LANG").ok(),
    ]
    .into_iter()
    .flatten()
    {
        let trimmed = candidate.trim();
        if trimmed.is_empty() {
            continue;
        }
        let normalized = trimmed.replace('_', "-").to_ascii_lowercase();
        let parsed = parse_confirmation_locale(Some(trimmed));
        if parsed != ConfirmationLocale::En || normalized.starts_with("en") {
            return parsed;
        }
    }
    ConfirmationLocale::En
}

fn confirmation_locale_tag(locale: ConfirmationLocale) -> &'static str {
    match locale {
        ConfirmationLocale::En => "en",
        ConfirmationLocale::ZhHans => "zh-Hans",
        ConfirmationLocale::ZhHant => "zh-Hant",
        ConfirmationLocale::Ja => "ja",
        ConfirmationLocale::Ko => "ko",
        ConfirmationLocale::De => "de",
    }
}

fn confirmation_copy(locale: ConfirmationLocale) -> ConfirmationCopy {
    match locale {
        ConfirmationLocale::ZhHans => ConfirmationCopy {
            title: "敏感操作确认",
            continue_label: "继续",
            cancel_label: "取消",
            prompt_intro: "请确认敏感操作：",
            prompt_target: "目标路径",
            prompt_hint: "仅当此操作确实由你主动触发时才继续。",
            timeout_error: "敏感操作确认已超时",
            receive_error: "无法接收敏感操作确认结果",
            cancelled_error: "用户已取消敏感操作",
        },
        ConfirmationLocale::ZhHant => ConfirmationCopy {
            title: "敏感操作確認",
            continue_label: "繼續",
            cancel_label: "取消",
            prompt_intro: "請確認敏感操作：",
            prompt_target: "目標路徑",
            prompt_hint: "僅在此操作確實由你主動觸發時才繼續。",
            timeout_error: "敏感操作確認已逾時",
            receive_error: "無法接收敏感操作確認結果",
            cancelled_error: "使用者已取消敏感操作",
        },
        ConfirmationLocale::Ja => ConfirmationCopy {
            title: "機密操作の確認",
            continue_label: "続行",
            cancel_label: "キャンセル",
            prompt_intro: "機密操作を確認してください：",
            prompt_target: "対象パス",
            prompt_hint: "この操作があなた自身によって開始された場合のみ続行してください。",
            timeout_error: "機密操作の確認がタイムアウトしました",
            receive_error: "機密操作確認結果の受信に失敗しました",
            cancelled_error: "ユーザーが機密操作をキャンセルしました",
        },
        ConfirmationLocale::Ko => ConfirmationCopy {
            title: "민감 작업 확인",
            continue_label: "계속",
            cancel_label: "취소",
            prompt_intro: "민감 작업을 확인하세요:",
            prompt_target: "대상 경로",
            prompt_hint: "이 작업이 본인에 의해 시작된 경우에만 계속하세요.",
            timeout_error: "민감 작업 확인 시간이 초과되었습니다",
            receive_error: "민감 작업 확인 결과를 받지 못했습니다",
            cancelled_error: "사용자가 민감 작업을 취소했습니다",
        },
        ConfirmationLocale::De => ConfirmationCopy {
            title: "Bestätigung sensibler Aktion",
            continue_label: "Fortfahren",
            cancel_label: "Abbrechen",
            prompt_intro: "Bitte sensible Aktion bestätigen:",
            prompt_target: "Zielpfad",
            prompt_hint: "Nur fortfahren, wenn diese Aktion von dir selbst ausgelöst wurde.",
            timeout_error: "Zeitüberschreitung bei der Bestätigung sensibler Aktion",
            receive_error: "Bestätigungsergebnis für sensible Aktion konnte nicht empfangen werden",
            cancelled_error: "Sensible Aktion wurde vom Benutzer abgebrochen",
        },
        ConfirmationLocale::En => ConfirmationCopy {
            title: "Sensitive Action Confirmation",
            continue_label: "Continue",
            cancel_label: "Cancel",
            prompt_intro: "Confirm sensitive action:",
            prompt_target: "Target",
            prompt_hint: "Only continue if this was triggered by you.",
            timeout_error: "Sensitive action confirmation timed out",
            receive_error: "Failed to receive sensitive action confirmation result",
            cancelled_error: "Sensitive action cancelled by user",
        },
    }
}

fn build_confirmation_message(
    action: SensitiveAction,
    target_path: Option<&str>,
    locale: ConfirmationLocale,
) -> String {
    let copy = confirmation_copy(locale);
    let target_preview = truncate_target_for_prompt(target_path);
    format!(
        "{}\n{}\n\n{}: {}\n\n{}",
        copy.prompt_intro,
        action.confirmation_label(locale),
        copy.prompt_target,
        target_preview,
        copy.prompt_hint
    )
}

fn build_confirmation_request(
    action: SensitiveAction,
    target_path: Option<&str>,
    locale: ConfirmationLocale,
    parent_bound: bool,
) -> ConfirmationDialogRequest {
    let copy = confirmation_copy(locale);
    ConfirmationDialogRequest {
        message: build_confirmation_message(action, target_path, locale),
        title: copy.title.to_string(),
        continue_label: copy.continue_label.to_string(),
        cancel_label: copy.cancel_label.to_string(),
        parent_bound,
    }
}

async fn execute_confirmation_request<F>(
    request: ConfirmationDialogRequest,
    timeout: Duration,
    locale: ConfirmationLocale,
    show_dialog: F,
) -> Result<(), String>
where
    F: FnOnce(ConfirmationDialogRequest, oneshot::Sender<bool>),
{
    let copy = confirmation_copy(locale);
    let (tx, rx) = oneshot::channel::<bool>();
    show_dialog(request, tx);

    let confirmed = tokio::time::timeout(timeout, rx)
        .await
        .map_err(|_| copy.timeout_error.to_string())?
        .map_err(|_| copy.receive_error.to_string())?;
    if confirmed {
        Ok(())
    } else {
        Err(copy.cancelled_error.to_string())
    }
}

fn classify_confirmation_error(error: &str, locale: ConfirmationLocale) -> ConfirmationOutcome {
    let copy = confirmation_copy(locale);
    if error == copy.cancelled_error {
        return ConfirmationOutcome::Cancelled;
    }
    if error == copy.timeout_error {
        return ConfirmationOutcome::TimedOut;
    }
    if error == copy.receive_error {
        return ConfirmationOutcome::ChannelClosed;
    }
    ConfirmationOutcome::ChannelClosed
}

fn emit_confirmation_audit(
    app: &tauri::AppHandle,
    action: SensitiveAction,
    locale: ConfirmationLocale,
    target_path: Option<&str>,
    parent_bound: bool,
    outcome: ConfirmationOutcome,
) {
    let payload = SensitiveConfirmationAuditPayload {
        action: action.as_str(),
        locale: confirmation_locale_tag(locale),
        target_preview: truncate_target_for_prompt(target_path),
        parent_bound,
        outcome,
    };
    if let Err(error) = app.emit(IPC_SENSITIVE_CONFIRMATION_AUDIT_EVENT, payload) {
        eprintln!(
            "[ipc-security] failed to emit confirmation audit event: {}",
            error
        );
    }
}

pub async fn require_sensitive_action_confirmation(
    app: &tauri::AppHandle,
    action: SensitiveAction,
    target_path: Option<&str>,
) -> Result<(), String> {
    let locale = resolve_confirmation_locale();
    let parent_window = app.get_webview_window(MAIN_WEBVIEW_LABEL);
    let parent_bound = parent_window.is_some();
    let request = build_confirmation_request(action, target_path, locale, parent_bound);
    emit_confirmation_audit(
        app,
        action,
        locale,
        target_path,
        parent_bound,
        ConfirmationOutcome::Prompted,
    );

    let result = execute_confirmation_request(
        request,
        Duration::from_secs(120),
        locale,
        move |request, tx| {
            let mut sender = Some(tx);
            let mut dialog_builder = app
                .dialog()
                .message(request.message)
                .title(request.title)
                .kind(MessageDialogKind::Warning)
                .buttons(MessageDialogButtons::OkCancelCustom(
                    request.continue_label,
                    request.cancel_label,
                ));
            if let Some(parent_window) = parent_window.as_ref() {
                dialog_builder = dialog_builder.parent(parent_window);
            }
            dialog_builder.show(move |confirmed| {
                if let Some(tx) = sender.take() {
                    let _ = tx.send(confirmed);
                }
            });
        },
    )
    .await;

    match result {
        Ok(()) => {
            emit_confirmation_audit(
                app,
                action,
                locale,
                target_path,
                parent_bound,
                ConfirmationOutcome::Confirmed,
            );
            Ok(())
        }
        Err(error) => {
            emit_confirmation_audit(
                app,
                action,
                locale,
                target_path,
                parent_bound,
                classify_confirmation_error(&error, locale),
            );
            Err(error)
        }
    }
}

#[tauri::command]
pub fn issue_sensitive_action_ticket(
    webview_window: tauri::WebviewWindow,
    action: String,
) -> Result<String, String> {
    if !is_main_webview_label(webview_window.label()) {
        return Err("Sensitive action ticket can only be issued from main webview".to_string());
    }

    let parsed_action = SensitiveAction::from_str(action.as_str())
        .ok_or_else(|| format!("Unsupported sensitive action: {action}"))?;

    issue_sensitive_ticket(parsed_action)
}

#[cfg(test)]
mod tests {
    use super::*;

    include!("../command_registry_macro.in");

    #[test]
    fn parses_confirmation_locale_variants() {
        assert_eq!(
            parse_confirmation_locale(Some("zh-CN")),
            ConfirmationLocale::ZhHans
        );
        assert_eq!(
            parse_confirmation_locale(Some("zh_Hant_TW")),
            ConfirmationLocale::ZhHant
        );
        assert_eq!(parse_confirmation_locale(Some("ja-JP")), ConfirmationLocale::Ja);
        assert_eq!(parse_confirmation_locale(Some("ko-KR")), ConfirmationLocale::Ko);
        assert_eq!(parse_confirmation_locale(Some("de-DE")), ConfirmationLocale::De);
        assert_eq!(parse_confirmation_locale(Some("en-US")), ConfirmationLocale::En);
        assert_eq!(parse_confirmation_locale(Some("unknown")), ConfirmationLocale::En);
    }

    #[test]
    fn localizes_confirmation_copy_and_message_for_zh_hans() {
        let locale = ConfirmationLocale::ZhHans;
        let copy = confirmation_copy(locale);
        assert_eq!(copy.title, "敏感操作确认");
        assert_eq!(copy.continue_label, "继续");
        assert_eq!(copy.cancel_label, "取消");
        let message = build_confirmation_message(
            SensitiveAction::MigrateDataDir,
            Some("/tmp/myrm"),
            locale,
        );
        assert!(message.contains("请确认敏感操作"));
        assert!(message.contains("迁移数据目录"));
        assert!(message.contains("目标路径"));
    }

    #[test]
    fn classifies_confirmation_error_by_locale_copy() {
        let locale = ConfirmationLocale::ZhHans;
        let copy = confirmation_copy(locale);
        assert_eq!(
            classify_confirmation_error(copy.cancelled_error, locale),
            ConfirmationOutcome::Cancelled
        );
        assert_eq!(
            classify_confirmation_error(copy.timeout_error, locale),
            ConfirmationOutcome::TimedOut
        );
        assert_eq!(
            classify_confirmation_error(copy.receive_error, locale),
            ConfirmationOutcome::ChannelClosed
        );
    }

    #[tokio::test]
    async fn confirmation_request_accepts_and_tracks_parent_binding() {
        let locale = ConfirmationLocale::En;
        let request = build_confirmation_request(
            SensitiveAction::MigrateDataDir,
            Some("/tmp/myrm"),
            locale,
            true,
        );

        let result = execute_confirmation_request(
            request,
            Duration::from_millis(50),
            locale,
            |request, tx| {
                assert!(request.parent_bound);
                assert_eq!(request.title, "Sensitive Action Confirmation");
                assert_eq!(request.continue_label, "Continue");
                let _ = tx.send(true);
            },
        )
        .await;

        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn confirmation_request_returns_localized_cancel_error() {
        let locale = ConfirmationLocale::ZhHans;
        let request = build_confirmation_request(
            SensitiveAction::ExportLocalSqlite,
            Some("/tmp/export"),
            locale,
            false,
        );

        let result = execute_confirmation_request(
            request,
            Duration::from_millis(50),
            locale,
            |request, tx| {
                assert!(!request.parent_bound);
                assert_eq!(request.cancel_label, "取消");
                let _ = tx.send(false);
            },
        )
        .await;

        assert_eq!(result.expect_err("cancel should fail"), "用户已取消敏感操作");
    }

    #[tokio::test]
    async fn confirmation_request_times_out_when_dialog_does_not_respond() {
        let locale = ConfirmationLocale::En;
        let request =
            build_confirmation_request(SensitiveAction::MigrateDataDir, Some("/tmp/path"), locale, true);

        let result = execute_confirmation_request(
            request,
            Duration::from_millis(1),
            locale,
            |_, tx| {
                tauri::async_runtime::spawn(async move {
                    tokio::time::sleep(Duration::from_millis(20)).await;
                    drop(tx);
                });
            },
        )
        .await;

        assert_eq!(
            result.expect_err("timeout should fail"),
            "Sensitive action confirmation timed out"
        );
    }

    #[tokio::test]
    async fn confirmation_request_returns_receive_error_when_channel_closes() {
        let locale = ConfirmationLocale::En;
        let request = build_confirmation_request(SensitiveAction::ExportLocalSqlite, None, locale, false);

        let result = execute_confirmation_request(
            request,
            Duration::from_millis(50),
            locale,
            |_, tx| drop(tx),
        )
        .await;

        assert_eq!(
            result.expect_err("closed channel should fail"),
            "Failed to receive sensitive action confirmation result"
        );
    }

    #[test]
    fn allows_main_webview_for_critical_command() {
        let result = authorize_request("migrate_data_dir", "main");
        assert!(result.is_ok());
    }

    #[test]
    fn blocks_session_webview_for_main_only_command() {
        let result = authorize_request("migrate_data_dir", "session-123");
        assert!(result.is_err());
        let denied = result.expect_err("session webview should be blocked");
        assert_eq!(denied.reason_code, "main_only_command");
        assert_eq!(denied.risk, CommandRisk::Critical);
    }

    #[test]
    fn allows_session_webview_for_agent_message_command() {
        let result = authorize_request("send_agent_message", "session-abc");
        assert!(result.is_ok());
    }

    #[test]
    fn blocks_unknown_webview_label() {
        let result = authorize_request("send_agent_message", "overlay-window");
        assert!(result.is_err());
        let denied = result.expect_err("unknown webview should be blocked");
        assert_eq!(denied.reason_code, "untrusted_webview");
    }

    #[test]
    fn marks_drop_mode_for_tray_status() {
        let result = authorize_request("set_tray_status", "overlay-window");
        assert!(result.is_err());
        let denied = result.expect_err("untrusted tray caller should be denied");
        assert_eq!(denied.deny_mode, DenyMode::Drop);
    }

    #[test]
    fn issues_and_consumes_ticket() {
        let mut store = TicketStore::default();
        let ticket = store
            .issue(SensitiveAction::MigrateDataDir)
            .expect("ticket should be issued");
        let result = store.consume(SensitiveAction::MigrateDataDir, &ticket);
        assert!(result.is_ok());
    }

    #[test]
    fn rejects_ticket_action_mismatch() {
        let mut store = TicketStore::default();
        let ticket = store
            .issue(SensitiveAction::MigrateDataDir)
            .expect("ticket should be issued");
        let result = store.consume(SensitiveAction::ExportLocalSqlite, &ticket);
        assert!(result.is_err());
        let message = result.expect_err("ticket mismatch should fail");
        assert!(message.contains("ticket mismatch"));
    }

    #[test]
    fn expires_ticket_after_ttl() {
        let mut store = TicketStore::default();
        let ticket = store
            .issue_with_ttl(SensitiveAction::ExportLocalSqlite, Duration::from_millis(0))
            .expect("ticket should be issued");
        std::thread::sleep(Duration::from_millis(1));
        let result = store.consume(SensitiveAction::ExportLocalSqlite, &ticket);
        assert!(result.is_err());
        let message = result.expect_err("expired ticket should fail");
        assert!(message.contains("expired"));
    }

    #[test]
    fn enforces_pending_ticket_cap() {
        let mut store = TicketStore::default();
        for _ in 0..MAX_PENDING_SENSITIVE_TICKETS {
            let issued = store.issue_with_ttl(
                SensitiveAction::MigrateDataDir,
                Duration::from_secs(60),
            );
            assert!(issued.is_ok());
        }

        let overflow = store.issue_with_ttl(
            SensitiveAction::MigrateDataDir,
            Duration::from_secs(60),
        );
        assert!(overflow.is_err());
        let message = overflow.expect_err("overflow should be blocked");
        assert!(message.contains("pending sensitive action tickets"));
    }

    #[test]
    fn build_manifest_commands_are_covered_by_policy() {
        macro_rules! command_name_vec {
            ($(($name:literal, $handler:path)),* $(,)?) => {
                vec![$($name.to_string()),*]
            };
        }
        let commands: Vec<String> = tauri_command_registry!(command_name_vec);

        assert!(
            !commands.is_empty(),
            "command registry should not be empty"
        );

        let unknown: Vec<String> = commands
            .into_iter()
            .filter(|command| {
                matches!(
                    authorize_request(command, "main"),
                    Err(DeniedInvoke {
                        reason_code: "unknown_command",
                        ..
                    })
                )
            })
            .collect();

        assert!(
            unknown.is_empty(),
            "commands missing sender policy coverage: {:?}",
            unknown
        );
    }

    #[test]
    fn command_registry_has_no_duplicate_names() {
        macro_rules! command_name_vec {
            ($(($name:literal, $handler:path)),* $(,)?) => {
                vec![$($name),*]
            };
        }
        let commands: Vec<&'static str> = tauri_command_registry!(command_name_vec);
        let mut seen = std::collections::HashSet::new();
        let mut duplicates = Vec::new();
        for command in commands {
            if !seen.insert(command) {
                duplicates.push(command);
            }
        }
        assert!(
            duplicates.is_empty(),
            "duplicate command names found in registry: {:?}",
            duplicates
        );
    }
}
