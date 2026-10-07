//! 视觉审批高亮页：协议名、入口 URL 的查询参数编解码、HTML 模板，以及承载页面的自定义协议。
//!
//! 页面无状态：高亮框几何与标签全部随入口 URL 的查询参数传入，协议响应只依据请求渲染。
//! 每个高亮窗口因此各带各的页面，窗口之间没有共享槽位，重建或并存时不会互相串页。
//! 页面不走 `data:` URL 的原因见 `utils::protocol_page`。
//!
//! [INPUT]
//! - utils::protocol_page（POS: 自定义协议页面共用的入口 URL / HTML 转义 / 不缓存响应）
//!
//! [OUTPUT]
//! - HighlightBox: 窗口内的高亮框几何
//! - SCHEME / url / response: 自定义协议名、带高亮参数的入口 URL、协议响应（app/mod.rs 注册协议，visual_approval_overlay.rs 建窗）
//!
//! [POS]
//! 审批高亮"显示什么"的唯一来源；几何换算、窗口生命周期与 IPC 命令在 `visual_approval_overlay.rs`。

use tauri::http::{Request, Response};

use crate::utils::protocol_page::{html_escape, html_response, page_url};

/// 自定义协议名；`app/mod.rs` 注册协议与本模块 `url` 共用同一常量。
pub(crate) const SCHEME: &str = "myrm-overlay";

/// 参数缺失或非法时的占位页：完全透明，不画任何东西。
const BLANK_HTML: &str = r#"<!DOCTYPE html><html><head><meta charset="utf-8" /></head><body style="margin:0;background:transparent"></body></html>"#;

/// 窗口内的高亮框（CSS 像素，相对窗口左上角）。
#[derive(Debug, Clone, Copy)]
pub(crate) struct HighlightBox {
    pub(crate) x: f64,
    pub(crate) y: f64,
    pub(crate) width: f64,
    pub(crate) height: f64,
}

/// 高亮窗口的入口 URL：框几何与标签全部放进查询参数。
pub(crate) fn url(highlight: HighlightBox, label: Option<&str>) -> Result<tauri::Url, String> {
    let [x, y, w, h] = [highlight.x, highlight.y, highlight.width, highlight.height]
        .map(|value| format!("{value:.2}"));
    let mut query = vec![
        ("x", x.as_str()),
        ("y", y.as_str()),
        ("w", w.as_str()),
        ("h", h.as_str()),
    ];
    if let Some(label) = label {
        query.push(("label", label));
    }
    page_url(SCHEME, &query)
}

/// 自定义协议的响应：依据请求的查询参数渲染高亮页；参数缺失或非法时返回透明占位页。
pub(crate) fn response(request: &Request<Vec<u8>>) -> Response<Vec<u8>> {
    html_response(render(&request.uri().to_string()))
}

fn render(request_url: &str) -> String {
    tauri::Url::parse(request_url)
        .ok()
        .and_then(|url| parse_query(&url))
        .map_or_else(
            || BLANK_HTML.to_string(),
            |(highlight, label)| highlight_html(highlight, label.as_deref()),
        )
}

fn parse_query(url: &tauri::Url) -> Option<(HighlightBox, Option<String>)> {
    let (mut x, mut y, mut width, mut height, mut label) = (None, None, None, None, None);
    for (key, value) in url.query_pairs() {
        match key.as_ref() {
            "x" => x = finite(&value),
            "y" => y = finite(&value),
            "w" => width = finite(&value),
            "h" => height = finite(&value),
            "label" => label = Some(value.into_owned()),
            _ => {}
        }
    }
    Some((
        HighlightBox {
            x: x?,
            y: y?,
            width: width?,
            height: height?,
        },
        label,
    ))
}

fn finite(value: &str) -> Option<f64> {
    value
        .parse::<f64>()
        .ok()
        .filter(|number| number.is_finite())
}

fn highlight_html(highlight: HighlightBox, label: Option<&str>) -> String {
    let HighlightBox {
        x,
        y,
        width,
        height,
    } = highlight;
    let label = label.unwrap_or("").trim();
    let label_html = if label.is_empty() {
        String::new()
    } else {
        format!(
            r#"<div class="label" style="left:{:.2}px;top:{:.2}px;">{}</div>"#,
            x,
            (y - 24.0).max(0.0),
            html_escape(label),
        )
    };

    format!(
        r#"<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html, body {{
      margin: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: transparent;
    }}
    .shade {{
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.18);
      pointer-events: none;
    }}
    .box {{
      position: fixed;
      border: 3px solid #ef4444;
      border-radius: 6px;
      box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.35), 0 0 24px rgba(239, 68, 68, 0.45);
      pointer-events: none;
      box-sizing: border-box;
    }}
    .label {{
      position: fixed;
      color: #fff;
      background: rgba(220, 38, 38, 0.92);
      font: 600 12px/1.2 system-ui, -apple-system, sans-serif;
      padding: 4px 8px;
      border-radius: 6px;
      pointer-events: none;
      max-width: 320px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
  </style>
</head>
<body>
  <div class="shade"></div>
  <div class="box" style="left:{x:.2}px;top:{y:.2}px;width:{width:.2}px;height:{height:.2}px;"></div>
  {label_html}
</body>
</html>"#
    )
}

#[cfg(test)]
mod tests {
    use super::{render, response, url, HighlightBox, BLANK_HTML};
    use tauri::http::{header, Request};

    const BOX: HighlightBox = HighlightBox {
        x: 120.0,
        y: 80.5,
        width: 260.0,
        height: 40.0,
    };

    fn page_for(highlight: HighlightBox, label: Option<&str>) -> String {
        render(url(highlight, label).expect("page url").as_str())
    }

    #[test]
    fn the_url_carries_everything_the_page_needs() {
        let html = page_for(BOX, Some("Save"));
        assert!(html.contains("left:120.00px;top:80.50px;width:260.00px;height:40.00px;"));
        assert!(html.contains(">Save</div>"));
    }

    #[test]
    fn hostile_label_text_survives_the_url_and_is_escaped_in_the_page() {
        let html = page_for(BOX, Some("<img src=x onerror=alert(1)> & \"q\" 'a' 中文"));
        assert!(!html.contains("<img"));
        assert!(html
            .contains("&lt;img src=x onerror=alert(1)&gt; &amp; &quot;q&quot; &#39;a&#39; 中文"));
    }

    #[test]
    fn a_missing_or_blank_label_draws_no_label() {
        assert!(!page_for(BOX, None).contains("class=\"label\""));
        assert!(!page_for(BOX, Some("   ")).contains("class=\"label\""));
    }

    #[test]
    fn the_label_sits_above_the_box_and_never_leaves_the_window() {
        let near_top = HighlightBox { y: 10.0, ..BOX };
        assert!(page_for(near_top, Some("Save")).contains("left:120.00px;top:0.00px;"));
        assert!(page_for(BOX, Some("Save")).contains("left:120.00px;top:56.50px;"));
    }

    #[test]
    fn incomplete_or_invalid_parameters_render_a_blank_page() {
        let base = "myrm-overlay://localhost/";
        for query in [
            "",
            "?x=1&y=2&w=3",
            "?x=1&y=2&w=3&h=abc",
            "?x=NaN&y=2&w=3&h=4",
            "?x=1&y=inf&w=3&h=4",
        ] {
            assert_eq!(
                render(&format!("{base}{query}")),
                BLANK_HTML,
                "query: {query:?}"
            );
        }
        assert_eq!(render("not a url"), BLANK_HTML);
    }

    #[test]
    fn the_response_is_an_uncached_html_page() {
        let request = Request::builder()
            .uri(url(BOX, None).expect("page url").as_str())
            .body(Vec::new())
            .expect("request");
        let response = response(&request);
        assert_eq!(
            response.headers()[header::CONTENT_TYPE],
            "text/html; charset=utf-8"
        );
        assert_eq!(response.headers()[header::CACHE_CONTROL], "no-store");
        assert!(response.body().starts_with(b"<!DOCTYPE html>"));
    }
}
