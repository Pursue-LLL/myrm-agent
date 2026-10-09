//! Builder 链中与具体 Runtime 无关的部分：官方插件与窗口页自定义协议。
//!
//! [INPUT]
//! - tauri_plugin_{clipboard_manager, shell, dialog, fs, deep_link, notification, updater, autostart}
//! - tauri.conf.json#plugins（各插件在 `build()` 时反序列化自己的配置段）
//! - commands::{privacy_curtain_page, visual_approval_overlay_page}（协议名与响应）
//!
//! [OUTPUT]
//! - with_product_plugins: 在任意 Runtime 的 Builder 上追加产品使用的官方插件
//! - with_page_protocols: 注册帷幕看板与审批高亮的窗口页自定义协议
//!
//! [POS]
//! `run()` 与进程内契约测试（启动配置、ACL 授权）共用的 Builder 片段，避免测试与生产各写一份。
//! single-instance / window-state / global-shortcut 依赖具体 Runtime 或带进程级副作用，
//! 仍由 `run()` 直接注册。

use tauri::{Builder, Runtime};

use crate::commands::privacy_curtain_page as curtain_page;
use crate::commands::visual_approval_overlay_page as overlay_page;

/// 追加产品使用的官方插件。deep-link 须晚于 `run()` 中先行注册的 single-instance。
pub(crate) fn with_product_plugins<R: Runtime>(builder: Builder<R>) -> Builder<R> {
    builder
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(
            tauri_plugin_autostart::Builder::new()
                .args(["--auto-launched"])
                .build(),
        )
}

/// 窗口页面经自定义协议提供：`data:` URL 在本应用被 tauri 拒绝，且页内 IPC 属 Remote 来源。
pub(crate) fn with_page_protocols<R: Runtime>(builder: Builder<R>) -> Builder<R> {
    builder
        .register_uri_scheme_protocol(curtain_page::SCHEME, |_ctx, _request| {
            curtain_page::response()
        })
        .register_uri_scheme_protocol(overlay_page::SCHEME, |_ctx, request| {
            overlay_page::response(&request)
        })
}

#[cfg(test)]
mod tests {
    use regex::Regex;
    use tauri::test::mock_builder;

    use super::with_product_plugins;

    const TAURI_CONF: &str = include_str!("../../tauri.conf.json");

    /// 发布版在 `build()` 阶段让每个插件反序列化自己的配置段：任一段不被接受（例如
    /// tauri-plugin-fs 的 `deny_unknown_fields` 之于 `plugins.fs.scope`）就会令应用启动即 panic。
    /// 这里用真实 `generate_context!()`（真实 conf 与插件 ACL 清单）走同一条插件链。
    #[test]
    fn shipped_tauri_conf_is_accepted_by_every_product_plugin() {
        let built = with_product_plugins(mock_builder()).build(tauri::generate_context!());
        assert!(
            built.is_ok(),
            "a plugin rejected its tauri.conf.json section: {:?}",
            built.err()
        );
    }

    /// 反证：插件拒绝其配置段时 `build()` 必须返回 Err；否则上面的启动契约测试形同虚设。
    #[test]
    fn a_plugin_config_section_the_plugin_rejects_fails_the_build() {
        let mut context = tauri::generate_context!();
        context.config_mut().plugins.0.insert(
            "fs".to_string(),
            serde_json::json!({ "scope": ["$HOME/**"] }),
        );
        assert!(with_product_plugins(mock_builder()).build(context).is_err());
    }

    fn shell_open_validator() -> Regex {
        let conf: serde_json::Value =
            serde_json::from_str(TAURI_CONF).expect("tauri.conf.json must be valid JSON");
        let pattern = conf["plugins"]["shell"]["open"]
            .as_str()
            .expect("plugins.shell.open must be a validation regex");
        // tauri-plugin-shell 以 `^{pattern}$` 编译该字符串。
        Regex::new(&format!("^{pattern}$")).expect("plugins.shell.open must compile")
    }

    /// 产品页只需打开网页链接、邮件/电话链接、系统设置深链与「在 IDE 中打开」的唤起链接
    /// （前端 `ide-handoff.ts` 只给出裸协议）；其余协议（`file:`、`javascript:`、自定义协议）、
    /// 带路径的 IDE 链接（扩展安装、仓库克隆等）以及形如命令行开关的值一律拒绝。
    #[test]
    fn shell_open_scope_admits_product_links_only() {
        let validator = shell_open_validator();
        for allowed in [
            "https://example.com/docs?a=1#top",
            "http://127.0.0.1:3000/",
            "mailto:support@example.com",
            "tel:5551234",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            "ms-settings:privacy-webcam",
            "cursor://",
            "vscode://",
        ] {
            assert!(validator.is_match(allowed), "must be openable: {allowed}");
        }
        for denied in [
            "file:///etc/passwd",
            "javascript:alert(1)",
            "myrmagent://oauth/callback",
            "cursor://file/etc/passwd",
            "vscode://vscode.git/clone?url=https://example.com/r.git",
            "cursor:",
            "ftp://example.com/",
            "https://",
            "https://example.com/a b",
            "https://example.com/\nfile:///etc/passwd",
            "x-apple.systempreferences:",
            "--enable-debugging",
            "-i",
            "/R",
            "",
        ] {
            assert!(!validator.is_match(denied), "must be rejected: {denied:?}");
        }
    }
}
