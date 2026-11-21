"""Page-side scripts of the domain filter: the CSP policy and its guard (Layer 0), the hardening (Layer 2).

[INPUT]
- domain_filter::DomainAllowlist (POS: immutable domain pattern matcher; only its ``patterns`` are read here)
- stdlib json (POS: the policy text is embedded as a JSON string literal)

[OUTPUT]
- build_csp_meta_script: script that puts the allowlist's Content-Security-Policy ``<meta>`` at the top of a
  document's head (a document with a root element but no head, such as an XML or SVG document, is given one) and
  puts it there again before a page opens a WebSocket or Worker; raises ``ValueError`` for an empty allowlist. As an
  init script its value is dropped; evaluated as an expression it is a function that makes the current document
  carry the policy and says whether it does
- build_init_script: init script that hardens WebRTC, WebTransport and Service Worker registration; a window that
  is already hardened keeps what it has

[POS]
The two scripts ``install_domain_filter`` registers with ``BrowserContext.add_init_script`` for the page's main world,
and that ``domain_filter.agent_world`` runs again in the world the agent's own JavaScript runs in. The browser runs an
init script in every document it creates before the page's own scripts, except in a popup that keeps its opener: the
driver lets that page start before the init scripts are registered, so its first script can run first, and a
same-origin popup's reused window runs them once, on ``about:blank``, which the Layer 0 script covers itself (see
Layer 0 in the package docstring and ``BROWSER_SYSTEM.md`` section 10).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.browser.domain_filter import DomainAllowlist


_CSP_SCRIPT_TEMPLATE = """(function() {
  'use strict';
  var policy = __POLICY__;
  var xhtml = 'http://www.w3.org/1999/xhtml';
  var construct = Reflect.construct;

  function carries(doc) {
    var held = doc.head ? doc.head.querySelectorAll('meta[http-equiv="Content-Security-Policy" i]') : [];
    for (var i = 0; i < held.length; i++) {
      if (held[i].content === policy) return true;
    }
    return false;
  }

  function headOf(doc) {
    if (!doc.head && doc.documentElement) {
      var created = doc.createElementNS(xhtml, 'head');
      doc.documentElement.insertBefore(created, doc.documentElement.firstChild);
      if (!doc.head) created.remove();
    }
    return doc.head;
  }

  function ensurePolicy() {
    var doc = document;
    var head = headOf(doc);
    if (!head) return;
    if (!carries(doc)) {
      var meta = doc.createElementNS(xhtml, 'meta');
      meta.httpEquiv = 'Content-Security-Policy';
      meta.content = policy;
      head.insertBefore(meta, head.firstChild);
    }
  }

  if (document.head) {
    ensurePolicy();
  } else if (document.readyState === 'loading') {
    var observer = new MutationObserver(function() {
      if (document.head) {
        observer.disconnect();
        ensurePolicy();
      }
    });
    observer.observe(document, { childList: true, subtree: true });
    document.addEventListener('DOMContentLoaded', function() { observer.disconnect(); }, { once: true });
  }

  ['WebSocket', 'Worker', 'SharedWorker'].forEach(function(name) {
    var Native = window[name];
    if (typeof Native !== 'function') return;
    var guarded = new Proxy(Native, {
      construct: function(target, args, newTarget) {
        ensurePolicy();
        return construct(target, args, newTarget === guarded ? target : newTarget);
      }
    });
    Object.defineProperty(Native.prototype, 'constructor', { value: guarded });
    Object.defineProperty(window, name, { value: guarded });
  });

  return function() {
    ensurePolicy();
    return carries(document);
  };
})();"""


def build_csp_meta_script(allowlist: DomainAllowlist) -> str:
    """Generate the script that puts the allowlist's CSP ``<meta>`` on a document that does not carry it.

    The browser enforces the policy for the connections the document itself makes, and keeps enforcing it after a page
    script removes the ``<meta>``, removes the head or rewrites the document (measured on Chromium; the Firefox family
    is untested). It is a page-level defence, not a security boundary: a channel the policy does not cover, and a page
    written to defeat the script that installs it (in a document with no head, or on an engine that runs the agent's
    JavaScript in the page's own world), are outside what it guarantees, so against a hostile page the boundary is the
    outbound network layer. Directives:
    - connect-src: Restricts network connections (fetch/XHR/WebSocket/EventSource/sendBeacon)
    - script-src: Restricts script loading (allows inline/eval for compatibility); also decides which Workers may start,
      so a Worker whose script comes from a blob or data URL is refused
    - frame-src: Restricts iframe loading
    - object-src: Blocks plugins (Flash/Java)

    Note: img-src/style-src/font-src/media-src are not restricted (allow CDN resources).

    An init script runs before the parser has created the document's ``<head>``, so the script waits for it: a
    ``MutationObserver`` on the document inserts the policy as the head's first child, ahead of the page's own scripts,
    and is dropped once it has done so or the document is fully parsed (one that is already parsed when the script
    runs gets no observer at all). A document that has a root element but never gets a head, such as an SVG or an
    XML document, is given one when the policy is needed, because a policy ``<meta>`` is enforced only inside
    the head; the observer never makes one, it waits for the head the parser builds. The head and the ``<meta>`` are
    created in the XHTML namespace, since ``createElement`` in an XML document makes an element without a namespace,
    which is not a ``meta`` element. A head the engine does not read as the document's head is removed again, so a
    document never keeps an element that does nothing.

    A window the browser reuses for a same-origin popup keeps what this script set on it, but its new document normally
    gets no init-script run of its own and so no policy. WebSocket, Worker and SharedWorker are the channels no request
    filter sees, so their constructors are wrapped in a ``Proxy`` that puts the policy on the current document before
    the real constructor runs. The wrapper neither throws nor filters by itself: the refusal is the browser's, delivered
    the way it is in a document that had the policy from the start. A page can tell the wrapper from the native
    constructor in two ways: the ``toString`` text lacks the function name, and a ``TypeError`` the native constructor
    throws gains a stack frame.

    The page's world and the agent's world (``domain_filter.agent_world`` runs this script there too) cannot see each
    other's variables, so the DOM decides, every time: a document gets the policy only when none of its head's
    ``<meta>`` elements already carries it, which also puts it back on a page that has rewritten its head. The script
    evaluates to a function that does the same for the current document and returns whether the document then carries
    the policy; a document with no root element to hold a head never does.

    Raises:
        ValueError: ``allowlist`` is empty. An empty allowlist installs no filter, so there is no policy to build.
    """
    if allowlist.is_empty:
        raise ValueError("An empty allowlist has no Content-Security-Policy; it installs no filter")

    sources: list[str] = []
    for pattern in allowlist.patterns:
        # ``*.example.com`` matches the apex for the host matcher; a CSP wildcard host source does not.
        if pattern.startswith("*."):
            sources.append(pattern[2:])
        sources.append(pattern)
    hosts = " ".join(sources)

    policy = "; ".join(
        (
            "object-src 'none'",
            f"connect-src 'self' {hosts}",
            f"script-src 'self' 'unsafe-inline' 'unsafe-eval' {hosts}",
            f"frame-src 'self' {hosts}",
        )
    )
    return _CSP_SCRIPT_TEMPLATE.replace("__POLICY__", json.dumps(policy))


def build_init_script() -> str:
    """Generate JavaScript IIFE that hardens special APIs not covered by CSP.

    Hardens:
    - RTCPeerConnection/webkitRTCPeerConnection (WebRTC Data Channel)
    - WebTransport (new standard)
    - Service Worker registration

    Web Workers are not hardened, which keeps anti-bot checks quiet; the Layer 1 route filter stops their HTTP requests.

    Both worlds of a window can run this script (``domain_filter.agent_world`` runs it in the world the agent's own
    JavaScript uses, which on some engines is the page's own), so a property that is already locked down is left as
    it is: defining it again would throw.
    """
    return """(function() {
  'use strict';

  function _harden(obj, prop, value) {
    var held = Object.getOwnPropertyDescriptor(obj, prop);
    if (held && !held.configurable && held.writable === false) return;
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
