//! 自定义协议页面共用原语：入口 URL、HTML 转义、不缓存的 HTML 响应。
//!
//! 窗口页面必须经应用自注册的自定义协议提供，而不是 `data:` URL：
//! - tauri 未启用 `webview-data-url` 特性，`data:` 页在建窗时就被拒绝；
//! - 自定义协议页属 Local 来源，`capabilities/*.json` 的 ACL 才会放行页内 IPC；
//!   `data:` 页属 Remote 来源，页内 IPC 会被拒。
//!
//! [INPUT]
//! - 各页面模块自有的协议名常量（POS: `app/mod.rs` 以同一常量注册协议）
//!
//! [OUTPUT]
//! - page_url: 自定义协议页面的入口 URL（可带查询参数）
//! - html_escape: 不可信文本的 HTML 转义
//! - html_response: 不缓存的 UTF-8 HTML 协议响应
//!
//! [POS]
//! 帷幕看板页（`commands::privacy_curtain_page`）与视觉审批高亮页
//! （`commands::visual_approval_overlay_page`）共用的传输细节；协议名与页面内容归各页面模块。

use tauri::http::{header, HeaderValue, Response};

/// 自定义协议页面的入口 URL；`query` 为空时不带 `?`。
///
/// Windows 上 WebView2 以 `http://<scheme>.localhost` 承载自定义协议，其余平台使用
/// `<scheme>://localhost`。
pub(crate) fn page_url(scheme: &str, query: &[(&str, &str)]) -> Result<tauri::Url, String> {
    let raw = if cfg!(windows) {
        format!("http://{scheme}.localhost/")
    } else {
        format!("{scheme}://localhost/")
    };
    let mut url = tauri::Url::parse(&raw).map_err(|error| error.to_string())?;
    if !query.is_empty() {
        url.query_pairs_mut().extend_pairs(query);
    }
    Ok(url)
}

/// 转义不可信文本，使其可安全置于 HTML 元素内容或带引号的属性值中。
pub(crate) fn html_escape(input: &str) -> String {
    input
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
}

/// 不缓存的 UTF-8 HTML 响应：页面随调用方状态（文案语言、审批目标）变化，webview 不得复用旧页。
pub(crate) fn html_response(html: String) -> Response<Vec<u8>> {
    let mut response = Response::new(html.into_bytes());
    let headers = response.headers_mut();
    headers.insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("text/html; charset=utf-8"),
    );
    headers.insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
    response
}

#[cfg(test)]
mod tests {
    use super::{html_escape, html_response, page_url};
    use tauri::http::header;

    #[test]
    fn page_url_targets_the_scheme_and_carries_no_query_by_default() {
        let url = page_url("myrm-test", &[]).expect("page url");
        if cfg!(windows) {
            assert_eq!(url.scheme(), "http");
            assert_eq!(url.host_str(), Some("myrm-test.localhost"));
        } else {
            assert_eq!(url.scheme(), "myrm-test");
            assert_eq!(url.host_str(), Some("localhost"));
        }
        assert_eq!(url.query(), None);
    }

    #[test]
    fn page_url_round_trips_query_values_verbatim() {
        let hostile = "a&b=c \"d\" <e> 中文";
        let url = page_url("myrm-test", &[("x", "1.50"), ("label", hostile)]).expect("page url");
        let pairs: Vec<(String, String)> = url.query_pairs().into_owned().collect();
        assert_eq!(
            pairs,
            vec![
                ("x".to_string(), "1.50".to_string()),
                ("label".to_string(), hostile.to_string()),
            ]
        );
    }

    #[test]
    fn html_escape_neutralises_markup_and_quotes() {
        assert_eq!(
            html_escape(r#"<a href="x" onclick='y'>&"#),
            "&lt;a href=&quot;x&quot; onclick=&#39;y&#39;&gt;&amp;"
        );
    }

    #[test]
    fn html_response_is_uncached_utf8_html() {
        let response = html_response("<!DOCTYPE html><p>hi</p>".to_string());
        assert_eq!(
            response.headers()[header::CONTENT_TYPE],
            "text/html; charset=utf-8"
        );
        assert_eq!(response.headers()[header::CACHE_CONTROL], "no-store");
        assert!(response.body().starts_with(b"<!DOCTYPE html>"));
    }
}
