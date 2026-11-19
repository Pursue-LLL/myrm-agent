"""Page-side scripts of the domain filter: the CSP policy (Layer 0) and the main-thread hardening (Layer 2).

[INPUT]
- domain_filter::DomainAllowlist (POS: immutable domain pattern matcher; only its ``patterns`` are read here)
- stdlib json (POS: the policy text is embedded as a JSON string literal)

[OUTPUT]
- build_csp_meta_script: init script that puts the allowlist's Content-Security-Policy ``<meta>`` at the top of a document's head
- build_init_script: init script that hardens WebRTC, WebTransport and Service Worker registration

[POS]
The two scripts ``install_domain_filter`` registers with ``BrowserContext.add_init_script``. The browser runs an init script
in every document of the context before the page's own scripts, whatever fetched the document; the one exception, the first
document of a same-origin popup, is described with Layer 0 in the package docstring.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.browser.domain_filter import DomainAllowlist


def build_csp_meta_script(allowlist: DomainAllowlist) -> str:
    """Generate the init script that puts the allowlist's CSP ``<meta>`` at the top of every document's ``<head>``.

    An init script runs before the parser has created the document's ``<head>``, so the script waits for it: a
    ``MutationObserver`` on the document inserts the policy as the head's first child, ahead of the page's own scripts,
    and is dropped once it has done so or the document is fully parsed (a document that never gets a head, such as an SVG,
    gets no policy and no lingering observer). Creating a head here instead would leave a stray element in such documents.

    The policy is enforced by the browser for the connections the document itself makes, and cannot be bypassed
    by page scripts. Directives:
    - connect-src: Restricts network connections (fetch/XHR/WebSocket/EventSource/sendBeacon)
    - script-src: Restricts script loading (allows inline/eval for compatibility)
    - frame-src: Restricts iframe loading
    - object-src: Blocks plugins (Flash/Java)

    Note: img-src/style-src/font-src/media-src are not restricted (allow CDN resources).
    """
    normalized_domains = []
    for p in allowlist.patterns:
        if p.startswith("*."):
            bare = p[2:]
            normalized_domains.append(bare)
            normalized_domains.append(p)
        else:
            normalized_domains.append(p)

    domains_list = " ".join(normalized_domains) if normalized_domains else ""

    directives = ["object-src 'none'"]
    if domains_list:
        directives.extend(
            [
                f"connect-src 'self' {domains_list}",
                f"script-src 'self' 'unsafe-inline' 'unsafe-eval' {domains_list}",
                f"frame-src 'self' {domains_list}",
            ]
        )
    else:
        directives.extend(
            [
                "connect-src 'self'",
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
                "frame-src 'self'",
            ]
        )

    csp_content = "; ".join(directives)

    return f"""(function() {{
  'use strict';
  var meta = document.createElement('meta');
  meta.httpEquiv = 'Content-Security-Policy';
  meta.content = {json.dumps(csp_content)};
  function insertPolicy() {{
    document.head.insertBefore(meta, document.head.firstChild);
  }}
  if (document.head) {{
    insertPolicy();
    return;
  }}
  var observer = new MutationObserver(function() {{
    if (document.head) {{
      observer.disconnect();
      insertPolicy();
    }}
  }});
  observer.observe(document, {{ childList: true, subtree: true }});
  document.addEventListener('DOMContentLoaded', function() {{ observer.disconnect(); }}, {{ once: true }});
}})();"""


def build_init_script() -> str:
    """Generate JavaScript IIFE that hardens special APIs not covered by CSP.

    Hardens:
    - RTCPeerConnection/webkitRTCPeerConnection (WebRTC Data Channel)
    - WebTransport (new standard)
    - Service Worker registration

    Web Workers are not hardened, which keeps anti-bot checks quiet; the Layer 1 route filter stops their requests.
    """
    return """(function() {
  'use strict';

  function _harden(obj, prop, value) {
    try {
      Object.defineProperty(obj, prop, {
        value: value,
        writable: false,
        configurable: false,
        enumerable: true
      });
    } catch(e) {
      obj[prop] = value;
    }
  }

  if (typeof RTCPeerConnection !== 'undefined') {
    _harden(window, 'RTCPeerConnection', function() {
      throw new DOMException(
        'RTCPeerConnection blocked by domain policy', 'SecurityError'
      );
    });
  }
  if (typeof webkitRTCPeerConnection !== 'undefined') {
    _harden(window, 'webkitRTCPeerConnection', function() {
      throw new DOMException(
        'RTCPeerConnection blocked by domain policy', 'SecurityError'
      );
    });
  }

  if (typeof WebTransport !== 'undefined') {
    _harden(window, 'WebTransport', function() {
      throw new DOMException(
        'WebTransport blocked by domain policy', 'SecurityError'
      );
    });
  }

  if (typeof navigator !== 'undefined' && navigator.serviceWorker) {
    _harden(navigator.serviceWorker, 'register', function() {
      return Promise.reject(new DOMException(
        'Service Worker registration blocked by domain policy', 'SecurityError'
      ));
    });
  }
})();"""
