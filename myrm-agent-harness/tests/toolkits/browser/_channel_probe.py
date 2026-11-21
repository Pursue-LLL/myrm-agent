"""The page-side probe that tries every way a page can open a WebSocket or a Worker.

[INPUT]
- stdlib json (POS: the probe's arguments travel inside the expression as a JSON literal)

[OUTPUT]
- CHANNEL_ROUTES: the route names the probe accepts; ``allowed`` goes to the allowlisted site, every other route to
  the outside server
- CHANNEL_PROBE: the probe as a JavaScript async function taking ``[route, outsideBase, insideBase]``
- probe_expression: the probe called with its arguments, as one expression for a caller that cannot pass arguments

[POS]
Shared by the integration tests that prove the allowlist holds on the channels no request filter sees. A route is the
constructor itself, a way to the native constructor around a wrapper (``prototype.constructor``, an instance's
``constructor``, a subclass, ``Reflect.construct``, another realm) or a Worker whose script comes from a blob or data
URL and opens the socket itself. A refusal arrives as a policy violation, not as an exception, so the verdict keeps
both the outcome of the call and the violations the document reported.
"""

from __future__ import annotations

import json

CHANNEL_ROUTES = (
    "allowed",
    "direct",
    "prototype_constructor",
    "instance_constructor",
    "subclass",
    "reflect",
    "frame_realm",
    "blob_worker",
    "data_worker",
    "blob_shared_worker",
)

CHANNEL_PROBE = r"""
async ([route, outsideBase, insideBase]) => {
  const outside = (path) => `${outsideBase.replace('http', 'ws')}/${path}`;
  const inside = (path) => `${insideBase.replace('http', 'ws')}/${path}`;
  const script = `new WebSocket('${outside('worker')}')`;
  const blob = () => URL.createObjectURL(new Blob([script], {type: 'text/javascript'}));
  const routes = {
    allowed: () => new WebSocket(inside('allowed')),
    direct: () => new WebSocket(outside(route)),
    prototype_constructor: () => new WebSocket.prototype.constructor(outside(route)),
    instance_constructor: () => new (new WebSocket.prototype.constructor(inside('seed'))).constructor(outside(route)),
    subclass: () => { class Tap extends WebSocket {} return new Tap(outside(route)); },
    reflect: () => Reflect.construct(WebSocket, [outside(route)]),
    frame_realm: () => {
      const frame = document.body.appendChild(document.createElement('iframe'));
      return new frame.contentWindow.WebSocket(outside(route));
    },
    blob_worker: () => new Worker(blob()),
    data_worker: () => new Worker(`data:text/javascript,${encodeURIComponent(script)}`),
    blob_shared_worker: () => new SharedWorker(blob()),
  };
  const violations = [];
  document.addEventListener('securitypolicyviolation', (e) => violations.push(e.violatedDirective));
  let outcome;
  try { routes[route](); outcome = 'opened'; } catch (e) { outcome = e.name; }
  await new Promise((resolve) => setTimeout(resolve, 400));
  return {outcome, violations};
}
"""


def probe_expression(route: str, outside_base: str, inside_base: str) -> str:
    """The probe applied to one route and the two servers' base URLs."""
    return f"({CHANNEL_PROBE})({json.dumps([route, outside_base, inside_base])})"
