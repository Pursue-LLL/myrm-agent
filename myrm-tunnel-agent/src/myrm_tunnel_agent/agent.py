"""Tunnel Agent — long-poll relay client for MCP private reverse tunnel.

Connects to the Myrm Control Plane relay endpoint via outbound HTTP,
fetches pending MCP requests, forwards them to the local upstream MCP
server, and posts responses back. All connections are outbound-only —
no inbound firewall rules required.

Usage:
    myrm-tunnel-agent --relay-url https://cp.example.com --tunnel-id abc123 --token <auth_token> --upstream http://localhost:8080/mcp
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from dataclasses import dataclass

import httpx

logger = logging.getLogger("myrm_tunnel_agent")

_POLL_RETRY_DELAY_SEC = 2.0
_POLL_MAX_RETRY_DELAY_SEC = 60.0
_UPSTREAM_TIMEOUT_SEC = 90.0
_HTTP_TIMEOUT_SEC = 35.0


@dataclass(frozen=True, slots=True)
class TunnelConfig:
    relay_url: str
    tunnel_id: str
    auth_token: str
    upstream_url: str
    poll_retry_delay: float = _POLL_RETRY_DELAY_SEC
    max_retry_delay: float = _POLL_MAX_RETRY_DELAY_SEC
    upstream_timeout: float = _UPSTREAM_TIMEOUT_SEC


class TunnelAgent:
    """Outbound-only tunnel agent connecting local MCP to Myrm relay."""

    def __init__(self, config: TunnelConfig) -> None:
        self._cfg = config
        self._running = False
        self._retry_delay = config.poll_retry_delay
        self._consecutive_errors = 0

    @property
    def poll_url(self) -> str:
        base = self._cfg.relay_url.rstrip("/")
        return f"{base}/tunnel-relay/{self._cfg.tunnel_id}/poll"

    @property
    def respond_url(self) -> str:
        base = self._cfg.relay_url.rstrip("/")
        return f"{base}/tunnel-relay/{self._cfg.tunnel_id}/respond"

    @property
    def _auth_headers(self) -> dict[str, str]:
        return {"X-Tunnel-Token": self._cfg.auth_token}

    async def run(self) -> None:
        """Main event loop — poll for requests, forward to upstream, post responses."""
        self._running = True
        logger.info(
            "Tunnel agent starting: relay=%s tunnel_id=%s upstream=%s",
            self._cfg.relay_url,
            self._cfg.tunnel_id,
            self._cfg.upstream_url,
        )

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_shutdown)

        async with httpx.AsyncClient(timeout=httpx.Timeout(_HTTP_TIMEOUT_SEC)) as client:
            while self._running:
                try:
                    await self._poll_cycle(client)
                    self._consecutive_errors = 0
                    self._retry_delay = self._cfg.poll_retry_delay
                except httpx.HTTPStatusError as exc:
                    self._consecutive_errors += 1
                    if exc.response.status_code in (401, 403):
                        logger.error("Authentication failed (HTTP %d). Check your auth token.", exc.response.status_code)
                        self._running = False
                        break
                    logger.warning("HTTP error %d during poll, retrying in %.1fs", exc.response.status_code, self._retry_delay)
                    await asyncio.sleep(self._retry_delay)
                    self._retry_delay = min(self._retry_delay * 2, self._cfg.max_retry_delay)
                except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as exc:
                    self._consecutive_errors += 1
                    logger.warning("Connection error: %s, retrying in %.1fs", type(exc).__name__, self._retry_delay)
                    await asyncio.sleep(self._retry_delay)
                    self._retry_delay = min(self._retry_delay * 2, self._cfg.max_retry_delay)
                except asyncio.CancelledError:
                    break
                except Exception:
                    self._consecutive_errors += 1
                    logger.exception("Unexpected error in poll loop, retrying in %.1fs", self._retry_delay)
                    await asyncio.sleep(self._retry_delay)
                    self._retry_delay = min(self._retry_delay * 2, self._cfg.max_retry_delay)

        logger.info("Tunnel agent stopped")

    async def _poll_cycle(self, client: httpx.AsyncClient) -> None:
        resp = await client.get(self.poll_url, headers=self._auth_headers)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == "no_request":
            return

        request_id = data.get("request_id")
        mcp_payload = data.get("mcp_payload")
        if not request_id or not mcp_payload:
            logger.warning("Invalid poll response: missing request_id or mcp_payload")
            return

        logger.info("Received MCP request %s, method=%s", request_id, mcp_payload.get("method", "?"))
        mcp_response = await self._forward_to_upstream(client, mcp_payload)
        await self._post_response(client, request_id, mcp_response)

    async def _forward_to_upstream(self, client: httpx.AsyncClient, mcp_payload: dict) -> dict:
        """Forward MCP JSON-RPC request to the local upstream MCP server."""
        try:
            resp = await client.post(
                self._cfg.upstream_url,
                json=mcp_payload,
                timeout=httpx.Timeout(self._cfg.upstream_timeout),
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error("Upstream MCP request failed: %s", exc)
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32603, "message": f"Upstream error: {type(exc).__name__}: {exc}"},
                "id": mcp_payload.get("id"),
            }

    async def _post_response(self, client: httpx.AsyncClient, request_id: str, mcp_response: dict) -> None:
        """Post MCP response back to the relay."""
        try:
            resp = await client.post(
                self.respond_url,
                json={"request_id": request_id, "mcp_response": mcp_response},
                headers=self._auth_headers,
            )
            resp.raise_for_status()
            logger.info("MCP response %s delivered", request_id)
        except Exception as exc:
            logger.error("Failed to post response for %s: %s", request_id, exc)

    def _handle_shutdown(self) -> None:
        logger.info("Shutdown signal received")
        self._running = False


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Myrm Tunnel Agent — MCP Private Reverse Tunnel")
    parser.add_argument("--relay-url", required=True, help="Myrm Control Plane URL")
    parser.add_argument("--tunnel-id", required=True, help="Tunnel registration ID")
    parser.add_argument("--token", required=True, help="Tunnel auth token")
    parser.add_argument("--upstream", required=True, help="Local MCP server URL (e.g. http://localhost:8080/mcp)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = TunnelConfig(
        relay_url=args.relay_url,
        tunnel_id=args.tunnel_id,
        auth_token=args.token,
        upstream_url=args.upstream,
    )

    agent = TunnelAgent(config)
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
