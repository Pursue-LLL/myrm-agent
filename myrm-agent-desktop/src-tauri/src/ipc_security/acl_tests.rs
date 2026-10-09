//! ACL 契约测试：在 tauri 的 mock runtime 中，用真实 `generate_context!()`（真实 tauri.conf.json、
//! build.rs 生成的应用命令 ACL 清单、帷幕 capability 与全部插件权限清单）和生产使用的
//! `register_product_capabilities`，走完整的 IPC 授权路径，钉住「窗口 × 页面来源 × 命令」。
//!
//! 不注册任何插件：被 ACL 放行的插件命令以 "plugin ... not found" 终结（不弹对话框、不读写文件、
//! 不联网），被 ACL 拒绝的以 "not allowed" 终结；应用命令由占位 handler 终结。

use tauri::ipc::{CallbackFn, Invoke, InvokeBody};
use tauri::test::{get_ipc_response, mock_builder, MockRuntime, INVOKE_KEY};
use tauri::webview::InvokeRequest;
use tauri::{App, Manager, WebviewUrl, WebviewWindow, WebviewWindowBuilder};

use super::capability::{register_product_capabilities, REGISTERED_COMMANDS};
use super::policy::authorize_request;
use crate::app::chain::with_page_protocols;
use crate::commands::privacy_curtain_page as curtain_page;
use crate::commands::visual_approval_overlay_page as overlay_page;
use crate::runtime::ProductOrigin;
use crate::utils::protocol_page::page_url;

const PRODUCT_PORT: u16 = 3777;

/// 产品页（主窗口与会话窗口共用同一套前端）被授予的内核与官方插件命令。
const PRODUCT_PAGE_GRANTED: &[&str] = &[
    "plugin:app|version",
    "plugin:event|listen",
    "plugin:event|unlisten",
    "plugin:event|emit",
    "plugin:event|emit_to",
    "plugin:resources|close",
    "plugin:window|is_visible",
    "plugin:window|outer_position",
    "plugin:window|show",
    "plugin:window|hide",
    "plugin:window|unminimize",
    "plugin:window|set_focus",
    "plugin:window|request_user_attention",
    "plugin:window|set_progress_bar",
    "plugin:dialog|open",
    "plugin:dialog|save",
    "plugin:dialog|message",
    "plugin:fs|read_file",
    "plugin:fs|write_file",
    "plugin:shell|open",
    "plugin:clipboard-manager|read_text",
    "plugin:clipboard-manager|write_text",
    "plugin:clipboard-manager|write_html",
    "plugin:notification|is_permission_granted",
    "plugin:notification|request_permission",
    "plugin:notification|notify",
    "plugin:deep-link|get_current",
    "plugin:updater|check",
    "plugin:updater|download",
    "plugin:updater|install",
];

/// 产品页明确不授予的命令：执行进程、任意文件读写与删改、自启动、窗口销毁与创建等。
const PRODUCT_PAGE_WITHHELD: &[&str] = &[
    "plugin:shell|execute",
    "plugin:shell|spawn",
    "plugin:shell|kill",
    "plugin:shell|stdin_write",
    "plugin:fs|read_text_file",
    "plugin:fs|read_dir",
    "plugin:fs|write_text_file",
    "plugin:fs|remove",
    "plugin:fs|rename",
    "plugin:fs|copy_file",
    "plugin:fs|mkdir",
    "plugin:fs|create",
    "plugin:autostart|enable",
    "plugin:autostart|disable",
    "plugin:updater|download_and_install",
    "plugin:clipboard-manager|read_image",
    "plugin:clipboard-manager|write_image",
    "plugin:clipboard-manager|clear",
    "plugin:deep-link|register",
    "plugin:deep-link|unregister",
    "plugin:window|close",
    "plugin:window|destroy",
    "plugin:window|create",
    "plugin:window|set_position",
    "plugin:webview|create_webview_window",
];

/// 宠物浮层被授予的内核与官方插件命令。
const PET_SURFACE_GRANTED: &[&str] = &[
    "plugin:event|listen",
    "plugin:event|unlisten",
    "plugin:event|emit",
    "plugin:event|emit_to",
    "plugin:window|outer_position",
    "plugin:window|outer_size",
    "plugin:window|set_position",
    "plugin:notification|is_permission_granted",
];

/// 壳页（`tauri://` 自带页）的地址：Local 来源。
fn shell_page_url() -> &'static str {
    if cfg!(windows) {
        "http://tauri.localhost/"
    } else {
        "tauri://localhost/"
    }
}

/// 发布版产品页的地址：Next 回环页，Remote 来源。
fn product_page_url() -> String {
    ProductOrigin::new(PRODUCT_PORT)
        .page_url(&["chat-1"], &[("mode", "focused")])
        .to_string()
}

/// 产品窗口会加载的两类页面：Local 壳页与 Remote 产品页。
fn product_pages() -> [String; 2] {
    [shell_page_url().to_string(), product_page_url()]
}

fn product_app() -> App<MockRuntime> {
    let app = with_page_protocols(mock_builder())
        .invoke_handler(|invoke: Invoke<MockRuntime>| {
            invoke.resolver.resolve("handler-reached");
            true
        })
        .build(tauri::generate_context!())
        .expect("the shipped tauri.conf.json must build");
    register_product_capabilities(&app, &ProductOrigin::new(PRODUCT_PORT))
        .expect("product capabilities must resolve against the shipped ACL manifests");
    app
}

fn window(app: &App<MockRuntime>, label: &str) -> WebviewWindow<MockRuntime> {
    app.get_webview_window(label).unwrap_or_else(|| {
        WebviewWindowBuilder::new(app, label, WebviewUrl::default())
            .build()
            .unwrap_or_else(|error| panic!("mock window {label}: {error}"))
    })
}

fn request(command: &str, page_url: &str) -> InvokeRequest {
    InvokeRequest {
        cmd: command.into(),
        callback: CallbackFn(0),
        error: CallbackFn(1),
        url: page_url.parse().expect("page url must parse"),
        body: InvokeBody::default(),
        headers: Default::default(),
        invoke_key: INVOKE_KEY.to_string(),
    }
}

/// 调用是否越过了 ACL（放行后被占位 handler 或「插件未注册」终结都算越过）。
fn passes_acl(window: &WebviewWindow<MockRuntime>, page: &str, command: &str) -> bool {
    match get_ipc_response(window, request(command, page)) {
        Ok(_) => true,
        Err(error) => !error.to_string().contains("not allowed"),
    }
}

fn assert_grants(
    app: &App<MockRuntime>,
    label: &str,
    pages: &[String],
    granted: &[&str],
    withheld: &[&str],
) {
    let window = window(app, label);
    for page in pages {
        for command in granted {
            assert!(
                passes_acl(&window, page, command),
                "{label} @ {page} must be granted {command}"
            );
        }
        for command in withheld {
            assert!(
                !passes_acl(&window, page, command),
                "{label} @ {page} must not be granted {command}"
            );
        }
    }
}

/// 窗口 × 来源 × 全部注册命令：ACL 的放行结果必须与应用级 IPC gate 一致；
/// 产品窗口在 Local 壳页与 Remote 产品页上得到同一张表（开发与发布一致）。
#[test]
fn acl_agrees_with_the_ipc_gate_for_every_registered_command() {
    let app = product_app();
    let product_page = product_page_url();
    let curtain_url = curtain_page::url().expect("curtain url").to_string();
    let overlay_url = page_url(overlay_page::SCHEME, &[])
        .expect("overlay url")
        .to_string();

    let cases: [(&str, &str); 12] = [
        ("main", shell_page_url()),
        ("main", &product_page),
        ("session-chat-1", shell_page_url()),
        ("session-chat-1", &product_page),
        ("pet-surface", shell_page_url()),
        ("pet-surface", &product_page),
        ("privacy-curtain-1-0", &curtain_url),
        ("visual-approval-overlay-0", &overlay_url),
        // 标签只在模式之外一步之遥时也不得沾光。
        ("main2", &product_page),
        ("session", &product_page),
        ("pet-surface-2", &product_page),
        ("mainframe", shell_page_url()),
    ];
    for (label, page) in cases {
        let window = window(&app, label);
        for command in REGISTERED_COMMANDS {
            assert_eq!(
                passes_acl(&window, page, command),
                authorize_request(command, label).is_ok(),
                "{label} @ {page} -> {command}: ACL and the IPC gate must agree"
            );
        }
    }
}

/// 手写期望，不经 `authorize_request` 派生：策略与 ACL 一起被改松时必须有测试喊停。
#[test]
fn critical_commands_stay_main_only_in_the_acl() {
    let app = product_app();
    let pages = product_pages();

    assert_grants(
        &app,
        "main",
        &pages,
        &[
            "load_system_config",
            "save_system_config",
            "migrate_data_dir",
            "restart_app",
            "open_session_window",
            "show_pet_surface",
            "issue_sensitive_action_ticket",
        ],
        &[],
    );
    assert_grants(
        &app,
        "session-chat-1",
        &pages,
        &[
            "load_system_config",
            "inline_paste_back",
            "show_pet_surface",
        ],
        &[
            "save_system_config",
            "migrate_data_dir",
            "restart_app",
            "open_session_window",
            "issue_sensitive_action_ticket",
            "show_privacy_curtain",
        ],
    );
    assert_grants(
        &app,
        "pet-surface",
        &pages,
        &[
            "pet_surface_set_ignore_cursor",
            "pet_surface_set_focusable",
            "pet_surface_focus_main_window",
            "pet_surface_toggle_main_window",
        ],
        &[
            "load_system_config",
            "show_pet_surface",
            "hide_pet_surface",
            "save_system_config",
        ],
    );
}

/// 帷幕页是唯一非受控前端：只能上报物理输入，内核与插件命令一概不给。
#[test]
fn curtain_page_can_only_report_physical_input() {
    let app = product_app();
    let pages = [curtain_page::url().expect("curtain url").to_string()];
    let everything_else: Vec<&str> = REGISTERED_COMMANDS
        .iter()
        .copied()
        .filter(|command| *command != "curtain_report_physical_input")
        .chain(PRODUCT_PAGE_GRANTED.iter().copied())
        .chain(PRODUCT_PAGE_WITHHELD.iter().copied())
        .collect();
    assert_grants(
        &app,
        "privacy-curtain-1-0",
        &pages,
        &["curtain_report_physical_input"],
        &everything_else,
    );
}

/// 内核与官方插件命令按前端实际用法授予：授予表之外（含高危动词）一律不给，
/// 且主窗口与会话窗口、Local 与 Remote 来源得到同一张表。
#[test]
fn native_grants_follow_the_least_privilege_table() {
    let app = product_app();
    let pages = product_pages();

    for label in ["main", "session-chat-1"] {
        assert_grants(
            &app,
            label,
            &pages,
            PRODUCT_PAGE_GRANTED,
            PRODUCT_PAGE_WITHHELD,
        );
    }

    let pet_withheld: Vec<&str> = PRODUCT_PAGE_GRANTED
        .iter()
        .chain(PRODUCT_PAGE_WITHHELD)
        .copied()
        .filter(|command| !PET_SURFACE_GRANTED.contains(command))
        .collect();
    assert_grants(
        &app,
        "pet-surface",
        &pages,
        PET_SURFACE_GRANTED,
        &pet_withheld,
    );
}

/// 产品页 capability 只绑定配置端口的回环源：其它端口、端口前缀、`localhost`、其它协议与外部站点
/// 即使落在主窗口里也什么都拿不到。
#[test]
fn foreign_origins_get_nothing_even_in_the_main_window() {
    let app = product_app();
    let main = window(&app, "main");
    let foreign_pages = [
        "http://127.0.0.1:3778/",
        "http://127.0.0.1:37770/",
        "http://localhost:3777/",
        "https://127.0.0.1:3777/",
        "http://127.0.0.1.evil.example:3777/",
        "https://evil.example/",
    ];
    for page in foreign_pages {
        for command in REGISTERED_COMMANDS
            .iter()
            .chain(PRODUCT_PAGE_GRANTED)
            .chain(PET_SURFACE_GRANTED)
        {
            assert!(
                !passes_acl(&main, page, command),
                "{page} must not reach {command}"
            );
        }
    }
}
