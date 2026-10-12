//! 产品页来源：主窗口所在的 WebUI 来源，发布版是 Next.js Sidecar 的本机回环地址。
//!
//! [INPUT]
//! - config::FrontendConfig::port (POS: 本次运行固定的 Next.js 监听端口)
//! - tauri 配置 `build.devUrl` (POS: 开发版主窗口直连的开发服务器)
//!
//! [OUTPUT]
//! - ProductOrigin: 产品页来源（受管状态），提供 capability 远程来源模式与产品页 URL 构造
//!
//! [POS]
//! 产品页所在位置的唯一事实源：IPC capability 的 Remote 来源与所有须落到产品路由的窗口
//! 共用同一个值，二者不会漂移。发布版与 `frontend-shell` 占位页跳转的是同一来源（同样固定
//! `127.0.0.1`）；开发版主窗口不经占位页，子窗口须与它同源，故取 `build.devUrl`。

use tauri::Url;

/// 与 `frontend-shell` 跳转目标一致；刻意不用 `localhost`（可能解析为 `::1`，而 Next 绑定 IPv4）。
const PRODUCT_HOST: &str = "127.0.0.1";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProductOrigin {
    base: Url,
}

impl ProductOrigin {
    /// 发布版来源：`port` 即 `FrontendConfig::port`，本次运行内不变。
    pub fn new(port: u16) -> Self {
        // 协议、固定主机与 u16 端口拼出的 URL 恒合法。
        let base = Url::parse(&format!("http://{PRODUCT_HOST}:{port}/"))
            .expect("loopback origin built from a fixed scheme, host and u16 port is valid");
        Self { base }
    }

    /// 本次运行的产品页来源。开发版的主窗口直连 `build.devUrl`（`localhost`），而浏览器存储与
    /// `BroadcastChannel` 按来源隔离，子窗口若落到 `127.0.0.1` 就与主窗口各成一套存储；
    /// 因此开发版取 devUrl，发布版取 Sidecar 回环地址。
    pub fn resolve(dev_url: Option<&Url>, port: u16) -> Self {
        Self::select(dev_url, tauri::is_dev(), port)
    }

    fn select(dev_url: Option<&Url>, is_dev: bool, port: u16) -> Self {
        match dev_url {
            Some(url) if is_dev => Self { base: url.clone() },
            _ => Self::new(port),
        }
    }

    /// 不带路径的精确来源（`http://127.0.0.1:<port>`），即 capability 远程来源模式；不含通配。
    pub fn exact_origin(&self) -> String {
        self.base.origin().ascii_serialization()
    }

    /// 产品页绝对 URL。每个路径段与查询参数都经百分号编码：调用方传入的会话 ID 之类的
    /// 动态值无法逃出所在段，也无法改写主机、端口或片段。
    pub fn page_url(&self, segments: &[&str], query: &[(&str, &str)]) -> Url {
        let mut url = self.base.clone();
        url.path_segments_mut()
            .expect("an http origin always has path segments")
            .clear()
            .extend(segments);
        if !query.is_empty() {
            url.query_pairs_mut().extend_pairs(query);
        }
        url
    }
}

#[cfg(test)]
mod tests {
    use tauri::Url;

    use super::{ProductOrigin, PRODUCT_HOST};

    /// 壳页跳转的主机若与这里不一致，发布版 capability 的 Remote 来源就对不上实际页面。
    #[test]
    fn frontend_shell_navigates_to_the_same_host() {
        const SHELL_PAGE: &str = include_str!("../../frontend-shell/index.html");
        assert!(SHELL_PAGE.contains(&format!("const host = \"{PRODUCT_HOST}\";")));
    }

    #[test]
    fn exact_origin_follows_the_configured_port_without_wildcards() {
        assert_eq!(
            ProductOrigin::new(3000).exact_origin(),
            "http://127.0.0.1:3000"
        );
        assert_eq!(
            ProductOrigin::new(4321).exact_origin(),
            "http://127.0.0.1:4321"
        );
    }

    #[test]
    fn development_shares_the_dev_server_origin_with_the_main_window() {
        let dev_url: Url = "http://localhost:3000".parse().expect("dev url");

        let origin = ProductOrigin::select(Some(&dev_url), true, 4321);

        assert_eq!(origin.exact_origin(), "http://localhost:3000");
        assert_eq!(
            origin.page_url(&["pet-overlay"], &[]).as_str(),
            "http://localhost:3000/pet-overlay"
        );
    }

    #[test]
    fn release_uses_the_sidecar_loopback_whatever_the_dev_url_says() {
        let dev_url: Url = "http://localhost:3000".parse().expect("dev url");

        assert_eq!(
            ProductOrigin::select(Some(&dev_url), false, 4321).exact_origin(),
            "http://127.0.0.1:4321"
        );
        assert_eq!(
            ProductOrigin::select(None, true, 4321).exact_origin(),
            "http://127.0.0.1:4321"
        );
    }

    #[test]
    fn page_url_lands_on_the_requested_route() {
        let origin = ProductOrigin::new(3777);
        assert_eq!(
            origin.page_url(&["pet-overlay"], &[]).as_str(),
            "http://127.0.0.1:3777/pet-overlay"
        );
        assert_eq!(
            origin
                .page_url(&["chat-1"], &[("mode", "focused")])
                .as_str(),
            "http://127.0.0.1:3777/chat-1?mode=focused"
        );
    }

    #[test]
    fn dynamic_values_cannot_leave_their_path_segment_or_query_value() {
        let origin = ProductOrigin::new(3777);
        let hostile = "a/b?c=d#e%f g\\h@evil.example";

        let url = origin.page_url(&[hostile], &[("mode", hostile)]);

        assert_eq!(url.host_str(), Some("127.0.0.1"));
        assert_eq!(url.port(), Some(3777));
        assert_eq!(url.fragment(), None);
        assert_eq!(url.path_segments().map(Iterator::count), Some(1));
        let pairs: Vec<(String, String)> = url
            .query_pairs()
            .map(|(key, value)| (key.into_owned(), value.into_owned()))
            .collect();
        assert_eq!(pairs, vec![("mode".to_string(), hostile.to_string())]);
    }
}
