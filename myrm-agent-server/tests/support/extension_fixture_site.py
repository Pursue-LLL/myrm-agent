"""The cookie-gated fixture site the real-browser extension tests browse as a user.

[INPUT]
- aiohttp.web (POS: serves the pages on an ephemeral loopback port)

[OUTPUT]
- FixtureSite: a loopback site that answers under every host name the browser resolves to loopback and gates its pages on
  a login cookie: a secret page, an orders page, a portal whose controls open those pages in new tabs and raise a
  confirm dialog, an outbound page whose link a test points at any address, and two pages that send the browser on to any
  address they are given: a bounce that redirects at once and a late bounce whose script moves on after a set delay

[POS]
The pages the Agent reads in the e2e tests. Signing in is one request that sets the cookie; every other page answers 401
without it, so reading a page's content proves the request carried the user's session.
"""

from __future__ import annotations

import json

from aiohttp import web

_PAGE = "<!doctype html><html><head><meta charset='utf-8'><title>{title}</title></head><body>{body}</body></html>"


class FixtureSite:
    """Loopback site reachable under every fixture host name; its pages need the cookie ``/login`` hands out."""

    def __init__(self) -> None:
        self.port = 0
        self._runner: web.AppRunner | None = None

    def url(self, host: str, path: str = "/") -> str:
        return f"http://{host}:{self.port}{path}"

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/login", self._login)
        app.router.add_get("/secret", self._secret)
        app.router.add_get("/orders", self._orders)
        app.router.add_get("/portal", self._portal)
        app.router.add_get("/outbound", self._outbound)
        app.router.add_get("/bounce", self._bounce)
        app.router.add_get("/late-bounce", self._late_bounce)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        await web.TCPSite(self._runner, "127.0.0.1", 0).start()
        self.port = self._runner.addresses[0][1]

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    @staticmethod
    def _host(request: web.Request) -> str:
        return request.host.split(":")[0]

    @staticmethod
    def _html(title: str, body: str, *, status: int = 200) -> web.Response:
        return web.Response(text=_PAGE.format(title=title, body=body), content_type="text/html", status=status)

    async def _login(self, request: web.Request) -> web.Response:
        response = self._html("Signed in", f"<p id='who'>{request.query.get('user', 'alice')} on {self._host(request)}</p>")
        response.set_cookie("sid", request.query.get("user", "alice"), httponly=True, path="/")
        return response

    def _gated(self, request: web.Request, title: str, body: str) -> web.Response:
        """A page only a signed-in user sees: without the cookie ``/login`` hands out, the site answers 401."""
        if not request.cookies.get("sid"):
            return self._html("Login required", "<p id='denied'>login required</p>", status=401)
        return self._html(title, body)

    async def _secret(self, request: web.Request) -> web.Response:
        user = request.cookies.get("sid", "")
        body = f"<h1 id='who'>{user}</h1><p id='data'>private-data-42</p><a id='orders-link' href='/orders'>Orders</a>"
        return self._gated(request, "Secret", body)

    async def _portal(self, request: web.Request) -> web.Response:
        body = (
            "<a id='open-orders' href='/orders' target='_blank'>Orders</a>"
            "<button id='open-secret' onclick=\"window.open('/secret')\">Secret</button>"
            "<button id='ask' onclick=\"document.title = confirm('sure?') ? 'yes' : 'no'\">Ask</button>"
        )
        return self._gated(request, "Portal", body)

    async def _outbound(self, request: web.Request) -> web.Response:
        """A page whose first link opens a new tab, left without a destination for a test to point at an address."""
        body = "<a id='leave' href='/' target='_blank'>Leave</a><a id='open-orders' href='/orders' target='_blank'>Orders</a>"
        return self._gated(request, "Outbound", body)

    async def _bounce(self, request: web.Request) -> web.Response:
        """Redirects to the address in ``to``: a page that looks like part of the site until the browser reaches the end."""
        raise web.HTTPFound(request.query.get("to", "/"))

    async def _late_bounce(self, request: web.Request) -> web.Response:
        """A page that loads, then moves on to the address in ``to`` after ``after`` milliseconds."""
        target = json.dumps(request.query.get("to", "/")).replace("</", "<\\/")
        delay = int(request.query.get("after", "0"))
        body = f"<p id='bounce'>moving on</p><script>setTimeout(() => location.replace({target}), {delay})</script>"
        return self._html("Moving on", body)

    async def _orders(self, request: web.Request) -> web.Response:
        body = "<p id='orders'>Order 1001</p><button id='confirm' onclick=\"document.title='confirmed'\">Confirm</button>"
        return self._gated(request, "Orders", body)
