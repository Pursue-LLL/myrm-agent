use std::time::Duration;

use super::confirmation::{
    build_confirmation_message, build_confirmation_request, classify_confirmation_error,
    confirmation_copy, execute_confirmation_request, parse_confirmation_locale, ConfirmationLocale,
    ConfirmationOutcome,
};
use super::policy::{authorize_request, CommandRisk, DeniedInvoke, DenyMode};
use super::ticket_store::{SensitiveAction, TicketStore, MAX_PENDING_SENSITIVE_TICKETS};

include!("../../command_registry_macro.in");

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
    assert_eq!(
        parse_confirmation_locale(Some("ja-JP")),
        ConfirmationLocale::Ja
    );
    assert_eq!(
        parse_confirmation_locale(Some("ko-KR")),
        ConfirmationLocale::Ko
    );
    assert_eq!(
        parse_confirmation_locale(Some("de-DE")),
        ConfirmationLocale::De
    );
    assert_eq!(
        parse_confirmation_locale(Some("en-US")),
        ConfirmationLocale::En
    );
    assert_eq!(
        parse_confirmation_locale(Some("unknown")),
        ConfirmationLocale::En
    );
}

#[test]
fn localizes_confirmation_copy_and_message_for_zh_hans() {
    let locale = ConfirmationLocale::ZhHans;
    let copy = confirmation_copy(locale);
    assert_eq!(copy.title, "敏感操作确认");
    assert_eq!(copy.continue_label, "继续");
    assert_eq!(copy.cancel_label, "取消");
    let message =
        build_confirmation_message(SensitiveAction::MigrateDataDir, Some("/tmp/myrm"), locale);
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

    assert_eq!(
        result.expect_err("cancel should fail"),
        "用户已取消敏感操作"
    );
}

#[tokio::test]
async fn confirmation_request_times_out_when_dialog_does_not_respond() {
    let locale = ConfirmationLocale::En;
    let request = build_confirmation_request(
        SensitiveAction::MigrateDataDir,
        Some("/tmp/path"),
        locale,
        true,
    );

    let result = execute_confirmation_request(request, Duration::from_millis(1), locale, |_, tx| {
        tauri::async_runtime::spawn(async move {
            tokio::time::sleep(Duration::from_millis(20)).await;
            drop(tx);
        });
    })
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

    let result = execute_confirmation_request(request, Duration::from_millis(50), locale, |_, tx| {
        drop(tx)
    })
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
        let issued = store.issue_with_ttl(SensitiveAction::MigrateDataDir, Duration::from_secs(60));
        assert!(issued.is_ok());
    }

    let overflow = store.issue_with_ttl(SensitiveAction::MigrateDataDir, Duration::from_secs(60));
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

    assert!(!commands.is_empty(), "command registry should not be empty");

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
