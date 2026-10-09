//! 产品窗口的 Tauri ACL capability：应用命令授权与应用级 IPC gate 同源派生。
//!
//! [INPUT]
//! - command_registry_macro.in（应用命令全集，同时驱动 build.rs 的 ACL 清单与 generate_handler）
//! - policy::authorize_request（各窗口面可调用哪些应用命令的唯一事实源）
//! - runtime::ProductOrigin（发布版产品页所在的精确 Remote 来源）
//!
//! [OUTPUT]
//! - REGISTERED_COMMANDS: 注册表命令名全集
//! - register_product_capabilities: 向运行中的 App 注册 main / session-* / pet-surface 三个窗口面的 capability
//!
//! [POS]
//! ACL 层（Tauri 在命令入口按「窗口 × 来源」放行）与 `policy.rs`（应用层按窗口面放行）的接缝。
//! 应用命令的授权由 `authorize_request` 逐条派生，不手写第二份清单；本文件只声明内核与官方
//! 插件命令的授权。同一 capability 同时覆盖 Local 来源（`tauri://` 壳页、dev 服务）与发布版
//! 的 Next.js 回环页（Remote），因此开发与发布得到同一张权限表。

use tauri::ipc::CapabilityBuilder;
use tauri::{Manager, Runtime};

use super::policy::{
    authorize_request, MAIN_WEBVIEW_LABEL, PET_SURFACE_WEBVIEW_LABEL, SESSION_WEBVIEW_PREFIX,
};
use crate::runtime::ProductOrigin;

macro_rules! command_name_list {
    ($(($name:literal, $handler:path)),* $(,)?) => {
        &[$($name),*]
    };
}

include!("../../command_registry_macro.in");

/// 注册表命令名全集（与 build.rs 生成 ACL 清单、`generate_handler` 同源）。
pub(super) const REGISTERED_COMMANDS: &[&str] = tauri_command_registry!(command_name_list);

/// 产品页（主窗口与会话窗口承载同一套前端）实际调用的内核与官方插件命令，按前端用法逐条授予。
/// 应用版本、窗口元信息（只读）、事件通道与资源释放（更新器句柄）取各自的 default 集合，
/// 不取聚合的 `core:default`（它还含菜单与托盘的创建/改写）；改变窗口状态的动词、文件与链接、
/// 剪贴板、通知、深链、更新器各取所需。`fs` 与 `shell:allow-open` 不配静态 scope：文件路径由
/// 对话框与拖放授权，可打开的链接协议由 `tauri.conf.json#plugins.shell.open` 限定。
const PRODUCT_PAGE_NATIVE_PERMISSIONS: &[&str] = &[
    "core:app:default",
    "core:event:default",
    "core:resources:default",
    "core:window:default",
    "core:window:allow-show",
    "core:window:allow-hide",
    "core:window:allow-unminimize",
    "core:window:allow-set-focus",
    "core:window:allow-request-user-attention",
    "core:window:allow-set-progress-bar",
    "dialog:allow-open",
    "dialog:allow-save",
    // JS `ask` / `confirm` / `message` 都走 `plugin:dialog|message`。
    "dialog:allow-message",
    "fs:allow-read-file",
    "fs:allow-write-file",
    "shell:allow-open",
    "clipboard-manager:allow-read-text",
    "clipboard-manager:allow-write-text",
    "clipboard-manager:allow-write-html",
    "notification:allow-is-permission-granted",
    "notification:allow-request-permission",
    "notification:allow-notify",
    "deep-link:allow-get-current",
    "updater:allow-check",
    "updater:allow-download",
    "updater:allow-install",
];

/// 桌面宠物浮层只需事件通道与自身窗口的拖动（读位置/尺寸、改位置）。通知插件注入的
/// `window.Notification` 垫片在每个页面加载时都会查询授权状态，只读查询随之放行，免得每次
/// 开浮层都留下一条未处理的拒绝。
const PET_SURFACE_NATIVE_PERMISSIONS: &[&str] = &[
    "core:event:default",
    "core:window:allow-outer-position",
    "core:window:allow-outer-size",
    "core:window:allow-set-position",
    "notification:allow-is-permission-granted",
];

/// 承载产品前端的窗口面。帷幕窗由 `capabilities/curtain.json` 单独授权（其页面非产品前端）。
#[derive(Debug, Clone, Copy)]
enum Surface {
    Main,
    Session,
    Pet,
}

impl Surface {
    const ALL: [Surface; 3] = [Surface::Main, Surface::Session, Surface::Pet];

    fn capability_id(self) -> &'static str {
        match self {
            Surface::Main => "product-main",
            Surface::Session => "product-session",
            Surface::Pet => "product-pet-surface",
        }
    }

    /// ACL 的窗口标签模式。
    fn window_pattern(self) -> String {
        match self {
            Surface::Main => MAIN_WEBVIEW_LABEL.to_string(),
            Surface::Session => format!("{SESSION_WEBVIEW_PREFIX}*"),
            Surface::Pet => PET_SURFACE_WEBVIEW_LABEL.to_string(),
        }
    }

    /// 向 `authorize_request` 询问该面可调用哪些应用命令时使用的代表标签。
    fn probe_label(self) -> String {
        match self {
            Surface::Session => format!("{SESSION_WEBVIEW_PREFIX}probe"),
            Surface::Main | Surface::Pet => self.window_pattern(),
        }
    }

    fn native_permissions(self) -> &'static [&'static str] {
        match self {
            Surface::Main | Surface::Session => PRODUCT_PAGE_NATIVE_PERMISSIONS,
            Surface::Pet => PET_SURFACE_NATIVE_PERMISSIONS,
        }
    }

    /// 应用命令权限：应用级 gate 放行该面的命令，逐条对应 build.rs 生成的 `allow-<command>`。
    fn app_command_permissions(self) -> impl Iterator<Item = String> {
        let label = self.probe_label();
        REGISTERED_COMMANDS
            .iter()
            .filter(move |command| authorize_request(command, &label).is_ok())
            .map(|command| format!("allow-{}", command.replace('_', "-")))
    }

    fn capability(self, origin: &ProductOrigin) -> CapabilityBuilder {
        let builder = CapabilityBuilder::new(self.capability_id())
            .window(self.window_pattern())
            .remote(origin.exact_origin());
        self.app_command_permissions()
            .chain(self.native_permissions().iter().map(|p| (*p).to_string()))
            .fold(builder, CapabilityBuilder::permission)
    }
}

/// 注册产品窗口面的 capability。须在任一产品页发起 IPC 之前调用；权限标识符不存在时 tauri 在此 panic，
/// 由 `acl_tests` 以真实 ACL 清单在 CI 中拦截。
pub fn register_product_capabilities<R: Runtime>(
    app: &impl Manager<R>,
    origin: &ProductOrigin,
) -> tauri::Result<()> {
    for surface in Surface::ALL {
        app.add_capability(surface.capability(origin))?;
    }
    Ok(())
}
