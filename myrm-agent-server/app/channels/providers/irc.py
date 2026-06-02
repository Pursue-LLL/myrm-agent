"""IRC channel — bidirectional messaging via raw IRC protocol.

Inbound: TCP socket → PRIVMSG → strip control chars → _emit_inbound
Outbound: sanitize → PRIVMSG command

[INPUT]
- channels.core.base::BaseChannel (POS: Channel abstract base class)
- channels.types::OutboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- IRCChannel: IRC bidirectional messaging Channel

[POS]
IRC channel implementation. Raw asyncio TCP connection, supports SSL/TLS, NickServ authentication,
nick collision auto-recovery, control character filtering, outbound sanitization, collect_issues diagnostics.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Self

from app.channels.core.base import BaseChannel
from app.channels.core.credentials import credential_field, credential_spec, parse_bool
from app.channels.reliability.reconnect import reconnect_loop
from app.channels.rendering.renderer import render
from app.channels.types import (
    ChannelCapabilities,
    ChannelIssue,
    ChannelStatus,
    IssueKind,
    IssueSeverity,
    OutboundMessage,
    RenderStyle,
)

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 400
_IRC_CONTROL_CHARS_RE = re.compile(r"\x02|\x03(?:\d{1,2}(?:,\d{1,2})?)?|\x0f|\x16|\x1d|\x1e|\x1f")
_MAX_NICK_SUFFIX_RETRIES = 5


def _strip_irc_control_chars(text: str) -> str:
    """Remove mIRC color codes, bold, italic, underline, reverse, strikethrough, reset."""
    return _IRC_CONTROL_CHARS_RE.sub("", text)


def _sanitize_outbound(text: str) -> str:
    """Remove CR/LF and control chars to prevent IRC command injection."""
    cleaned = text.replace("\r", "").replace("\n", " ")
    return _strip_irc_control_chars(cleaned).strip()


class IRCChannel(BaseChannel):
    """IRC channel using raw asyncio TCP.

    Supports SSL/TLS, NickServ authentication, nick collision recovery,
    inbound control-char stripping, outbound sanitization, and QUIT shutdown.
    """

    name = "irc"
    credential_spec = credential_spec(
        "ircCredentials",
        server=credential_field("server", "IRC_SERVER"),
        nick=credential_field("nick", "IRC_NICK"),
        port=credential_field("port", "IRC_PORT", "6667"),
        channels=credential_field("channels", "IRC_CHANNELS"),
        password=credential_field("password", "IRC_PASSWORD"),
        use_ssl=credential_field("useSsl", "IRC_USE_SSL", "false"),
        nickserv_password=credential_field("nickservPassword", "IRC_NICKSERV_PASSWORD"),
    )
    capabilities = ChannelCapabilities(
        text=True,
        max_text_length=_MAX_TEXT_LENGTH,
    )
    render_style = RenderStyle(format="text", max_text_length=_MAX_TEXT_LENGTH)

    @classmethod
    def from_credentials(cls, creds: dict[str, str]) -> Self:
        channels_raw = creds.get("channels", "")
        channels = tuple(c.strip() for c in channels_raw.split(",") if c.strip()) if channels_raw else ()
        return cls(
            server=creds.get("server", ""),
            nick=creds.get("nick", ""),
            port=int(creds.get("port", "6667")),
            channels=channels,
            password=creds.get("password", ""),
            use_ssl=parse_bool(creds.get("use_ssl", "false")),
            nickserv_password=creds.get("nickserv_password", ""),
        )

    def __init__(
        self,
        server: str,
        nick: str,
        *,
        port: int = 6667,
        channels: tuple[str, ...] = (),
        password: str = "",
        use_ssl: bool = False,
        nickserv_password: str = "",
    ) -> None:
        super().__init__()
        self._server = server
        self._port = port
        self._nick = nick
        self._channels = channels
        self._password = password
        self._use_ssl = use_ssl
        self._nickserv_password = nickserv_password
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._recv_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if not self._server or not self._nick:
            logger.info("IRC not configured; channel idle")
            return
        self._bot_id = self._nick
        self._status = ChannelStatus.RUNNING
        self._recv_task = asyncio.create_task(
            reconnect_loop(
                self._connect_once,
                lambda: self._status,
                channel_name="IRCChannel",
            )
        )
        logger.info("IRCChannel: started (%s@%s)", self._nick, self._server)

    async def stop(self) -> None:
        self._set_connected(False)
        self._status = ChannelStatus.STOPPED
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        await self._quit_and_disconnect()

    async def health_check(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    def collect_issues(self) -> list[ChannelIssue]:
        issues: list[ChannelIssue] = []
        if not self._server or not self._nick:
            missing = []
            if not self._server:
                missing.append("server")
            if not self._nick:
                missing.append("nick")
            issues.append(
                ChannelIssue(
                    kind=IssueKind.CONFIG,
                    severity=IssueSeverity.ERROR,
                    message=f"{', '.join(missing)} not configured.",
                )
            )
            return issues
        if self._status == ChannelStatus.ERROR:
            issues.append(
                ChannelIssue(
                    kind=IssueKind.RUNTIME,
                    severity=IssueSeverity.ERROR,
                    message="IRC connection failed. Check server address and credentials.",
                )
            )
        return issues

    async def send(self, msg: OutboundMessage) -> str | None:
        if not self._writer:
            return None
        target = msg.recipient_id
        if msg.content:
            chunks = render(msg, self.render_style)
            for chunk in chunks:
                sanitized = _sanitize_outbound(chunk)
                if sanitized:
                    await self._send_raw(f"PRIVMSG {target} :{sanitized}")
        return None

    async def _connect_once(self) -> None:
        """Single IRC session. reconnect_loop handles retry on failure."""
        try:
            if self._use_ssl:
                import ssl as ssl_mod

                ctx = ssl_mod.create_default_context()
                self._reader, self._writer = await asyncio.open_connection(self._server, self._port, ssl=ctx)
            else:
                self._reader, self._writer = await asyncio.open_connection(self._server, self._port)

            if self._password:
                await self._send_raw(f"PASS {self._password}")
            await self._send_raw(f"NICK {self._nick}")
            await self._send_raw(f"USER {self._nick} 0 * :{self._nick}")

            await self._read_loop()
        finally:
            self._set_connected(False)
            await self._disconnect()

    async def _read_loop(self) -> None:
        assert self._reader is not None
        nick_retries = 0

        while self._status == ChannelStatus.RUNNING:
            raw = await self._reader.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            if line.startswith("PING"):
                token = line.split(" ", 1)[1] if " " in line else ""
                await self._send_raw(f"PONG {token}")
                continue

            parts = line.split(" ")

            if len(parts) >= 2 and parts[1] == "001":
                self._set_connected(True)
                if self._nickserv_password:
                    await self._send_raw(f"PRIVMSG NickServ :IDENTIFY {self._nick} {self._nickserv_password}")
                for ch in self._channels:
                    await self._send_raw(f"JOIN {ch}")
                nick_retries = 0
                continue

            if len(parts) >= 2 and parts[1] in ("433", "436"):
                if nick_retries < _MAX_NICK_SUFFIX_RETRIES:
                    nick_retries += 1
                    self._nick = f"{self._nick}_"
                    self._bot_id = self._nick
                    await self._send_raw(f"NICK {self._nick}")
                    logger.warning("IRCChannel: nick collision, retrying as %s", self._nick)
                continue

            if len(parts) >= 4 and parts[1] == "PRIVMSG":
                prefix = parts[0].lstrip(":")
                nick = prefix.split("!")[0] if "!" in prefix else prefix
                if nick == self._nick:
                    continue
                target = parts[2]
                text_raw = line.split(" :", 1)[1] if " :" in line else ""
                text = _strip_irc_control_chars(text_raw).strip()
                is_group = target.startswith("#") or target.startswith("&")
                chat_id = target if is_group else nick

                if text:
                    msg = self._build_inbound(
                        sender_id=nick,
                        content=text,
                        chat_id=chat_id,
                        is_group=is_group,
                        mentioned=self._nick.lower() in text.lower(),
                        media=(),
                        message_id=uuid.uuid4().hex,
                    )
                    await self._emit_inbound(msg)

    async def _send_raw(self, data: str) -> None:
        if self._writer and not self._writer.is_closing():
            self._writer.write((data + "\r\n").encode("utf-8"))
            await self._writer.drain()

    async def _quit_and_disconnect(self) -> None:
        """Send QUIT then close the TCP connection."""
        if self._writer and not self._writer.is_closing():
            try:
                self._writer.write(b"QUIT :shutdown\r\n")
                await self._writer.drain()
            except Exception:
                pass
        await self._disconnect()

    async def _disconnect(self) -> None:
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None
