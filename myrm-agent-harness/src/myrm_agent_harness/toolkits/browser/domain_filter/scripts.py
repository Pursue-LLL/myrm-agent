"""Page-side scripts of the domain filter: the CSP policy and its guard (Layer 0), the hardening (Layer 2).

[INPUT]
- domain_filter::DomainAllowlist (POS: immutable domain pattern matcher; only its ``patterns`` are read here)
- stdlib json (POS: the policy text is embedded as a JSON string literal)

[OUTPUT]
- build_csp_meta_script: script that puts the allowlist's Content-Security-Policy ``<meta>`` at the top of a
  document's head and puts it there again before a page opens a WebSocket or Worker; raises ``ValueError`` for an
  empty allowlist. As an init script its value is dropped; evaluated as an expression it is a function that makes the
  current document carry the policy and says whether it does
- build_init_script: init script that hardens WebRTC, WebTransport and Service Worker registration

[POS]
The two scripts ``install_domain_filter`` registers with ``BrowserContext.add_init_script`` for the page's main world,
and that ``domain_filter.agent_world`` runs again in the world the agent's own JavaScript runs in. The browser runs an
init script in every document it creates, before the page's own scripts, whatever fetched the document. A popup that
keeps its opener is the exception: the driver lets its page start before the init scripts are registered, so the page's
first script can run first, and a same-origin popup's reused window runs them once, on ``about:blank``; the Layer 0
script covers the reused-window case itself (see Layer 0 in the package docstring and ``BROWSER_SYSTEM.md`` section 10).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.browser.domain_filter import DomainAllowlist


_CSP_SCRIPT_TEMPLATE = """(function() {
  'use strict';
  var policy = __POLICY__;
  var construct = Reflect.construct;
  var carriers = new WeakSet();

  function carries(doc) {
    var held = doc.head ? doc.head.querySelectorAll('meta[http-equiv="Content-Security-Policy" i]') : [];
    for (var i = 0; i < held.length; i++) {
      if (held[i].content === policy) return true;
    }
    return false;
  }

  function ensurePolicy() {
    var doc = document;
    if (carriers.has(doc) || !doc.head) return;
    if (!carries(doc)) {
      var meta = doc.createElement('meta');
      meta.httpEquiv = 'Content-Security-Policy';
      meta.content = policy;
      doc.head.insertBefore(meta, doc.head.firstChild);
    }
    carriers.add(doc);
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
    """Generate the script that gives every document the allowlist's CSP ``<meta>`` and keeps it there.

    The policy is enforced by the browser for the connections the document itself makes, and cannot be bypassed
    by page scripts. Directives:
    - connect-src: Restricts network connections (fetch/XHR/WebSocket/EventSource/sendBeacon)
    - script-src: Restricts script loading (allows inline/eval for compatibility); also decides which Workers may start,
      so a Worker whose script comes from a blob or data URL is refused
    - frame-src: Restricts iframe loading
    - object-src: Blocks plugins (Flash/Java)

    Note: img-src/style-src/font-src/media-src are not restricted (allow CDN resources).

    An init script runs before the parser has created the document's ``<head>``, so the script waits for it: a
    ``MutationObserver`` on the document inserts the policy as the head's first child, ahead of the page's own scripts,
    and is dropped once it has done so or the document is fully parsed (a document that never gets a head, such as an SVG,
    gets no policy and no lingering observer; one that is already parsed when the script runs gets no observer at all).
    Creating a head here instead would leave a stray element in such documents.

    A window the browser reuses for a same-origin popup keeps what this script set on it, but its new document normally
    gets no init-script run of its own and so no policy. WebSocket, Worker and SharedWorker are the channels no request
    filter sees, so their constructors are wrapped in a ``Proxy`` that puts the policy on the current document before
    the real constructor runs. The wrapper neither throws nor filters by itself: the refusal is the browser's, delivered
    the way it is in a document that had the policy from the start. A page can tell the wrapper from the native
    constructor in two ways: the ``toString`` text lacks the function name, and a ``TypeError`` the native constructor
    throws gains a stack frame.

    The page's world and the agent's world (``domain_filter.agent_world`` runs this script there too) each keep a record
    of the documents they have dealt with and cannot see the other's, so the DOM decides: a document gets the policy
    only when none of its head's ``<meta>`` elements already carries it. The script evaluates to a function that does
    the same for the current document and returns whether the document then carries the policy; a document that cannot
    hold the element never does (SVG has no head, and an element created in an XML document is not a ``meta`` element).

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
