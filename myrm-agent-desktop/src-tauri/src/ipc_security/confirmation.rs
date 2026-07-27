use std::time::Duration;
use serde::Serialize;
use tauri::{Emitter, Manager};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
use tokio::sync::oneshot;
use super::ticket_store::SensitiveAction;

const IPC_SENSITIVE_CONFIRMATION_AUDIT_EVENT: &str = "ipc-sensitive-confirmation";
const MAIN_WEBVIEW_LABEL: &str = "main";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum ConfirmationLocale {
    En,
    ZhHans,
    ZhHant,
    Ja,
    Ko,
    De,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub(super) enum ConfirmationOutcome {
    Prompted,
    Confirmed,
    Cancelled,
    TimedOut,
    ChannelClosed,
}

#[derive(Debug, Clone, Serialize)]
struct SensitiveConfirmationAuditPayload {
    action: &'static str,
    locale: &'static str,
    parent_bound: bool,
    outcome: ConfirmationOutcome,
}

#[derive(Debug, Clone, Copy)]
pub(super) struct ConfirmationCopy {
    pub title: &'static str,
    pub continue_label: &'static str,
    pub cancel_label: &'static str,
    pub prompt_intro: &'static str,
    pub prompt_target: &'static str,
    pub prompt_hint: &'static str,
    pub timeout_error: &'static str,
    pub receive_error: &'static str,
    pub cancelled_error: &'static str,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) struct ConfirmationDialogRequest {
    pub message: String,
    pub title: String,
    pub continue_label: String,
    pub cancel_label: String,
    pub parent_bound: bool,
}

fn confirmation_action_label(action: SensitiveAction, locale: ConfirmationLocale) -> &'static str {
    match locale {
        ConfirmationLocale::ZhHans => match action {
            SensitiveAction::MigrateDataDir => "迁移数据目录",
            SensitiveAction::ExportLocalSqlite => "导出本地 SQLite",
        },
        ConfirmationLocale::ZhHant => match action {
            SensitiveAction::MigrateDataDir => "遷移資料目錄",
            SensitiveAction::ExportLocalSqlite => "匯出本機 SQLite",
        },
        ConfirmationLocale::Ja => match action {
            SensitiveAction::MigrateDataDir => "データディレクトリを移行",
            SensitiveAction::ExportLocalSqlite => "ローカル SQLite をエクスポート",
        },
        ConfirmationLocale::Ko => match action {
            SensitiveAction::MigrateDataDir => "데이터 디렉터리 이동",
            SensitiveAction::ExportLocalSqlite => "로컬 SQLite 내보내기",
        },
        ConfirmationLocale::De => match action {
            SensitiveAction::MigrateDataDir => "Datenverzeichnis migrieren",
            SensitiveAction::ExportLocalSqlite => "Lokale SQLite exportieren",
        },
        ConfirmationLocale::En => match action {
            SensitiveAction::MigrateDataDir => "Migrate Data Directory",
            SensitiveAction::ExportLocalSqlite => "Export Local SQLite",
        },
    }
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

pub(super) fn parse_confirmation_locale(raw: Option<&str>) -> ConfirmationLocale {
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

pub(super) fn confirmation_copy(locale: ConfirmationLocale) -> ConfirmationCopy {
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

pub(super) fn build_confirmation_message(
    action: SensitiveAction,
    target_path: Option<&str>,
    locale: ConfirmationLocale,
) -> String {
    let copy = confirmation_copy(locale);
    let target_preview = truncate_target_for_prompt(target_path);
    format!(
        "{}\n{}\n\n{}: {}\n\n{}",
        copy.prompt_intro,
        confirmation_action_label(action, locale),
        copy.prompt_target,
        target_preview,
        copy.prompt_hint
    )
}

pub(super) fn build_confirmation_request(
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

pub(super) async fn execute_confirmation_request<F>(
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

pub(super) fn classify_confirmation_error(
    error: &str,
    locale: ConfirmationLocale,
) -> ConfirmationOutcome {
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
    parent_bound: bool,
    outcome: ConfirmationOutcome,
) {
    let payload = SensitiveConfirmationAuditPayload {
        action: action.as_str(),
        locale: confirmation_locale_tag(locale),
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
                parent_bound,
                classify_confirmation_error(&error, locale),
            );
            Err(error)
        }
    }
}
