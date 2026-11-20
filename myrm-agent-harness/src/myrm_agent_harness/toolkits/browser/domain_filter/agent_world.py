"""The domain policy in the world the agent's own JavaScript runs in.

[INPUT]
- domain_filter::DomainAllowlist (POS: immutable domain pattern matcher; hashable, so one built arm serves every context that holds the same patterns)
- domain_filter.context_lists::domain_lists_for (POS: the allow/block lists a context's filter was installed with)
- domain_filter.scripts::build_csp_meta_script, build_init_script (POS: the page-side scripts of Layers 0 and 2)
- stdlib functools, json

[OUTPUT]
- agent_world_expression: the expression ``page.evaluate`` is handed for the agent's JavaScript: the agent's text behind
  the policy arm when the context has an allowlist, the text as written otherwise

[POS]
``BrowserSession.evaluate`` is the one place the agent's own JavaScript enters a page. Under patchright ``page.evaluate``
runs it in an isolated world: constructors and a window of its own over the page's DOM. The init scripts of Layers 0 and 2
run in the page's main world, so neither their ``WebSocket`` / ``Worker`` wrappers nor their hardening are there, and a
document that carries no policy ``<meta>`` (a same-origin popup's reused window, a page that removed its head) lets the
expression open a WebSocket or a Worker to any host. The arm runs the same two scripts in the isolated world before the
expression: the document gets its policy (an SVG or XML document is given a head to hold it), the window's own
``RTCPeerConnection``, ``WebTransport`` and ``serviceWorker.register`` are hardened, and a document that still cannot
carry the policy (it has no root element) refuses the expression instead of running it unguarded. An engine whose driver
evaluates in the page's own world (stock Playwright, which Camoufox runs on) has run both scripts there already: the arm
finds the window hardened and leaves it as it is.
The arm covers the window the expression runs in. A frame or a popup window the expression reaches through a DOM handle
is another realm with constructors of its own: an ``RTCPeerConnection`` there is not hardened, and a WebSocket or Worker
there is refused only by the policy its document carries (an ``about:blank`` or ``srcdoc`` document inherits the
opener's; a document loaded from a URL has to have been given one; ``BROWSER_SYSTEM.md`` section 10).
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.browser.domain_filter.context_lists import domain_lists_for
from myrm_agent_harness.toolkits.browser.domain_filter.scripts import build_csp_meta_script, build_init_script

if TYPE_CHECKING:
    from patchright.async_api import BrowserContext

    from myrm_agent_harness.toolkits.browser.domain_filter import DomainAllowlist

_ARM_NAME = "__myrmDomainPolicy"
_REFUSAL = (
    "JS evaluation refused: this document cannot carry the domain allowlist (for example, it has no root element to "
    "hold the policy element); read the page with the snapshot or extract tools instead"
)

# The driver trims the text it evaluates and parenthesizes one that reads as a function expression, which ``eval`` would
# take for a declaration. The inner ``eval`` needs the same two steps. They run in the page's own JavaScript engine, the
# one the driver's rule runs in, so the two agree on what whitespace is.
_RUN_HEAD = (
    "globalThis.eval(((text) => {\n"
    "  text = text.trim();\n"
    "  return /^(async)?\\s*function(\\s|\\()/.test(text) ? '(' + text + ')' : text;\n"
    "})("
)
_RUN_TAIL = "));"


@lru_cache(maxsize=32)
def _arm(allowlist: DomainAllowlist) -> str:
    """The statements that put ``allowlist``'s policy on the current window and document, or throw.

    A window is set up once: the policy script wraps the window's constructors, and a second run would wrap the
    wrappers. What the setup leaves behind is defined non-writable and non-configurable, so the agent's own script
    cannot delete or replace the check for the calls that follow. The check itself runs for every call: the window
    outlives a same-origin popup's first document.
    """
    return (
        f"if (!globalThis.{_ARM_NAME}) {{\n"
        f"  const ensure = {build_csp_meta_script(allowlist)}\n"
        f"  Object.defineProperty(globalThis, '{_ARM_NAME}', {{value: ensure}});\n"
        f"  {build_init_script()}\n"
        "}\n"
        f"if (!globalThis.{_ARM_NAME}()) throw new Error({json.dumps(_REFUSAL)});\n"
    )


def agent_world_expression(context: BrowserContext, expression: str) -> str:
    """``expression`` as ``page.evaluate`` is to be handed it for a page of ``context``.

    A context with no allowlist, whether it has no lists at all or only a blocklist, leaves the text as written: only
    an allowlist becomes a policy ``<meta>`` and a hardened window, and Layer 1 judges a blocklist for every world.
    Otherwise the arm comes first and the agent's text follows as the JSON literal of an inner ``eval``. A literal
    cannot end early, and the text keeps its own semantics: a leading ``'use strict'`` still applies and a syntax
    error is reported against the text itself.
    """
    policy = domain_lists_for(context)
    if policy is None or policy.allowlist.is_empty:
        return expression
    return f"{_arm(policy.allowlist)}{_RUN_HEAD}{json.dumps(expression)}{_RUN_TAIL}"
