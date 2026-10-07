//! 工位防窥帷幕——看板页面：文案缓存、HTML 模板，以及承载页面的自定义协议。
//!
//! 页面经应用自注册的自定义协议（`myrm-curtain`）提供，而不是 `data:` URL（原因见
//! `utils::protocol_page`）：页内的 `curtain_report_physical_input` 只有在 Local 来源下才被
//! `capabilities/curtain.json` 放行，`data:` 页的输入上报会被拒，帷幕将失去"交互即回锁"。
//!
//! [INPUT]
//! - 前端经 `set_texts` 注入的看板文案（POS: 按当前 locale 缓存，Rust 侧仅存默认英文兜底）
//! - utils::protocol_page（POS: 自定义协议页面共用的入口 URL / HTML 转义 / 不缓存响应）
//!
//! [OUTPUT]
//! - CurtainTexts / set_texts: 看板三段文案及其缓存
//! - SCHEME / url / response: 自定义协议名、页面入口 URL、协议响应（app/mod.rs 注册协议，privacy_curtain.rs 建窗）
//!
//! [POS]
//! 帷幕"显示什么"的唯一来源；窗口生命周期与 IPC 命令在 `privacy_curtain.rs`。
//! 页面在每次协议请求时按最新文案渲染，watcher 自动拉起时无前端调用方在场也能展示用户语言。

use std::sync::Mutex;

use tauri::http::Response;

use crate::utils::protocol_page::{html_escape, html_response, page_url};

/// 自定义协议名；`app/mod.rs` 注册协议与本模块 `url` 共用同一常量。
pub(crate) const SCHEME: &str = "myrm-curtain";

/// 看板三段文案（由前端按当前 locale 注入缓存，Rust 侧仅存默认英文兜底）。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CurtainTexts {
    pub primary: String,
    pub sub: String,
    pub hint: String,
}

fn default_texts() -> CurtainTexts {
    CurtainTexts {
        primary: "AI is working — screen protected".to_string(),
        sub: "This workstation is running an automated session. Content stays hidden until the owner returns.".to_string(),
        hint: "Any interaction locks this screen instantly".to_string(),
    }
}

static CACHED_TEXTS: Mutex<Option<CurtainTexts>> = Mutex::new(None);

fn current_texts() -> CurtainTexts {
    CACHED_TEXTS
        .lock()
        .ok()
        .and_then(|guard| guard.clone())
        .unwrap_or_else(default_texts)
}

/// 前端按当前 locale 注入看板文案（watcher 自动拉起时无前端调用方在场，靠此缓存）。
pub(crate) fn set_texts(texts: CurtainTexts) {
    if let Ok(mut guard) = CACHED_TEXTS.lock() {
        *guard = Some(texts);
    }
}

// ── 看板 HTML ──────────────────────────────────────────────────────

fn curtain_html(texts: &CurtainTexts) -> String {
    format!(
        r#"<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{ margin: 0; width: 100%; height: 100%; background: #000; overflow: hidden; }}
    .wrap {{
      position: fixed; inset: 0; display: flex; flex-direction: column;
      align-items: center; justify-content: center; gap: 18px;
      font-family: -apple-system, "SF Pro Display", system-ui, sans-serif;
      color: #e5e7eb; user-select: none; cursor: default;
    }}
    .brand {{ font-size: 15px; letter-spacing: 0.35em; color: #6b7280; text-transform: uppercase; }}
    .dot {{ width: 10px; height: 10px; border-radius: 50%; background: #10b981;
           animation: pulse 2.4s ease-in-out infinite; }}
    .primary {{ font-size: 28px; font-weight: 600; color: #f9fafb; text-align: center; padding: 0 24px; }}
    .sub {{ font-size: 15px; color: #9ca3af; max-width: 560px; text-align: center;
           line-height: 1.6; padding: 0 24px; }}
    .hint {{ margin-top: 26px; font-size: 12px; color: #4b5563; border: 1px solid #1f2937;
            border-radius: 999px; padding: 8px 18px; letter-spacing: 0.02em; }}
    @keyframes pulse {{ 0%, 100% {{ opacity: 0.35; }} 50% {{ opacity: 1; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="brand">Myrm</div>
    <div class="dot"></div>
    <div class="primary">{}</div>
    <div class="sub">{}</div>
    <div class="hint">{}</div>
  </div>
  <script>
    var throttled = 0;
    function report(source) {{
      try {{ window.__TAURI_INTERNALS__.invoke('curtain_report_physical_input', {{ source: source }}); }} catch (e) {{}}
    }}
    ['pointerdown', 'keydown', 'wheel'].forEach(function (ev) {{
      addEventListener(ev, function () {{ report(ev); }}, true);
    }});
    addEventListener('pointermove', function () {{
      var now = Date.now();
      if (now - throttled > 500) {{ throttled = now; report('pointermove'); }}
    }}, true);
  </script>
</body>
</html>"#,
        html_escape(&texts.primary),
        html_escape(&texts.sub),
        html_escape(&texts.hint),
    )
}

// ── 自定义协议 ─────────────────────────────────────────────────────

/// 帷幕窗口的入口 URL。
pub(crate) fn url() -> Result<tauri::Url, String> {
    page_url(SCHEME, &[])
}

/// 自定义协议的响应：按最新文案渲染看板页面（文案随语言切换而变，响应不缓存）。
pub(crate) fn response() -> Response<Vec<u8>> {
    html_response(curtain_html(&current_texts()))
}

#[cfg(test)]
mod tests {
    use super::{curtain_html, default_texts, response, set_texts, url, CurtainTexts, SCHEME};

    #[test]
    fn html_escapes_untrusted_texts() {
        let texts = CurtainTexts {
            primary: "<script>alert(1)</script>".to_string(),
            sub: "a & b".to_string(),
            hint: "\"quoted\"".to_string(),
        };
        let html = curtain_html(&texts);
        assert!(html.contains("&lt;script&gt;"));
        assert!(html.contains("a &amp; b"));
        assert!(!html.contains("\"quoted\""));
    }

    #[test]
    fn default_texts_are_non_empty() {
        let texts = default_texts();
        assert!(!texts.primary.is_empty());
        assert!(!texts.sub.is_empty());
        assert!(!texts.hint.is_empty());
    }

    #[test]
    fn page_url_targets_the_registered_scheme() {
        let url = url().expect("page url");
        if cfg!(windows) {
            assert_eq!(url.scheme(), "http");
            assert_eq!(url.host_str(), Some("myrm-curtain.localhost"));
        } else {
            assert_eq!(url.scheme(), SCHEME);
            assert_eq!(url.host_str(), Some("localhost"));
        }
    }

    /// 仅本用例触碰进程级文案缓存，其余用例走纯函数，互不干扰。
    #[test]
    fn served_page_reflects_injected_texts() {
        set_texts(CurtainTexts {
            primary: "primary-token".to_string(),
            sub: "sub-token".to_string(),
            hint: "hint-token".to_string(),
        });
        let body = String::from_utf8(response().into_body()).expect("utf-8 body");
        assert!(body.contains("primary-token"));
        assert!(body.contains("sub-token"));
        assert!(body.contains("hint-token"));
    }
}
