"""Channel registry and runtime instance management: register, hot-add, swap, remove, reload, enable, disable.

[INPUT]
- channels.core.gateway_health::ChannelHealthMixin (POS: runs each channel under supervision; the base of this mixin)
- channels.core.base::BaseChannel (POS: channel abstract base class)
- channels.core.channel_stop::stop_channel (POS: the capped, logged stop of one channel)
- channels.types::ChannelCapabilities, ChannelIssue, ChannelStatus, GroupInfo (POS: what a channel declares, reports and lists)

[OUTPUT]
- ChannelInstancesMixin: ``register`` with the channel event subscriptions and their callbacks, ``disable_channel`` /
  ``enable_channel`` / ``add_channel`` / ``swap_channel`` / ``remove_channel`` / ``reload_channel``, the per-type instance
  limit, and the read-side queries (status, issues, capabilities, groups, instance names)

[POS]
Registry segment of ``ChannelGateway``. Every change to the set of running channels goes through here, and each channel it
starts runs under the health supervision of ``ChannelHealthMixin``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from app.channels.core.base import BaseChannel
from app.channels.core.channel_stop import stop_channel
from app.channels.core.gateway_health import ChannelHealthMixin
from app.channels.types import ChannelCapabilities, ChannelIssue, ChannelStatus, GroupInfo

logger = logging.getLogger(__name__)


class ChannelInstancesMixin(ChannelHealthMixin):
    """Mixin: the registry of channels and their runtime hot-swap."""

    # Assigned in ``ChannelGateway.__init__``.
    _status_change_callback: Callable[[str, ChannelStatus, ChannelStatus], None] | None
    _groups_change_callback: Callable[[str, list[object]], None] | None
    _connection_change_callback: Callable[[str, bool], None] | None

    def register(self, channel: BaseChannel) -> None:
        """Register a channel provider and subscribe to its events."""
        self.bus.register_channel(channel)

        channel.on("status_change", self._on_status_change_event)
        channel.on("groups_change", self._on_groups_change_event)
        channel.on("connection_change", self._on_connection_change_event)

    def set_status_change_callback(self, callback: Callable[[str, ChannelStatus, ChannelStatus], None]) -> None:
        """Register a callback for channel status changes."""
        self._status_change_callback = callback

    def set_groups_change_callback(self, callback: Callable[[str, list[object]], None]) -> None:
        """Register a callback for groups list changes."""
        self._groups_change_callback = callback

    def set_connection_change_callback(self, callback: Callable[[str, bool], None]) -> None:
        """Register a callback for channel connection state changes."""
        self._connection_change_callback = callback

    def _on_status_change_event(self, channel_name: str, data: object) -> None:
        """Handle status_change event from channel."""
        if not isinstance(data, dict):
            return
        old_status = data.get("old_status")
        new_status = data.get("new_status")

        if not isinstance(old_status, ChannelStatus) or not isinstance(new_status, ChannelStatus):
            return

        logger.info(
            "ChannelGateway: %s status changed %s -> %s",
            channel_name,
            old_status.value,
            new_status.value,
        )
        if self._status_change_callback:
            self._status_change_callback(channel_name, old_status, new_status)

    def _on_connection_change_event(self, channel_name: str, data: object) -> None:
        """Handle connection_change event from channel."""
        if not isinstance(data, dict):
            return
        connected = bool(data.get("connected", False))
        logger.info("ChannelGateway: %s connection_change -> %s", channel_name, connected)
        if self._connection_change_callback:
            self._connection_change_callback(channel_name, connected)

    def _on_groups_change_event(self, channel_name: str, data: object) -> None:
        """Handle groups_change event from channel."""
        if not isinstance(data, list):
            return
        logger.info("ChannelGateway: %s groups updated (%d groups)", channel_name, len(data))
        if self._groups_change_callback:
            self._groups_change_callback(channel_name, data)

    async def disable_channel(self, name: str) -> bool:
        """Disable a channel at runtime (stop it and set DISABLED status).

        Returns True if the channel was found and disabled.
        """
        channel = self.bus.channels.get(name)
        if not channel:
            return False
        if channel.status == ChannelStatus.DISABLED:
            return True

        task = self._channel_tasks.pop(name, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await stop_channel(name, channel)

        channel._status = ChannelStatus.DISABLED
        logger.info("Channel '%s' disabled", name)
        return True

    async def enable_channel(self, name: str) -> bool:
        """Re-enable a previously disabled channel.

        Returns True if the channel was found and re-enabled.
        """
        channel = self.bus.channels.get(name)
        if not channel:
            return False
        if channel.status != ChannelStatus.DISABLED:
            return True

        channel._status = ChannelStatus.IDLE
        self._channel_tasks[name] = asyncio.create_task(
            self._run_channel(name, channel),
            name=f"channel-{name}",
        )
        logger.info("Channel '%s' enabled", name)
        if self.bus.durable_outbound.is_enabled():
            recovered = await self.bus.durable_outbound.recover_into_bus(self.bus)
            if recovered:
                logger.info(
                    "Recovered %d durable outbound deliveries after enabling channel '%s'",
                    recovered,
                    name,
                )
        return True

    _MAX_INSTANCES_PER_TYPE = 5

    @property
    def max_instances_per_type(self) -> int:
        """Maximum number of channel instances allowed per channel type."""
        return self._MAX_INSTANCES_PER_TYPE

    @staticmethod
    def _resolve_channel_type(channel: BaseChannel) -> str:
        """Extract the base channel type from the formal ``channel_type`` attribute."""
        return channel.channel_type or channel.__class__.name

    def _count_instances(self, channel_type: str) -> int:
        """Count existing instances (including the default) for a channel type."""
        return sum(1 for n, ch in self.bus.channels.items() if self._resolve_channel_type(ch) == channel_type)

    async def add_channel(self, channel: BaseChannel) -> str:
        """Hot-add a channel instance at runtime.

        Registers the channel in the bus, starts it, and begins health monitoring.
        Raises ValueError if the per-type instance limit is exceeded.
        Returns the channel name.
        """
        if not self._running:
            raise RuntimeError("Gateway not running; call start() first")

        channel_type = self._resolve_channel_type(channel)
        existing_count = self._count_instances(channel_type)
        if existing_count >= self._MAX_INSTANCES_PER_TYPE:
            raise ValueError(
                f"Instance limit reached: max {self._MAX_INSTANCES_PER_TYPE} instances for channel type '{channel_type}'"
            )

        self.bus.register_channel(channel)
        channel.on("status_change", self._on_status_change_event)
        channel.on("groups_change", self._on_groups_change_event)
        channel.on("connection_change", self._on_connection_change_event)

        self._channel_tasks[channel.name] = asyncio.create_task(
            self._run_channel(channel.name, channel),
            name=f"channel-{channel.name}",
        )
        logger.info("Channel '%s' hot-added", channel.name)
        return channel.name

    async def swap_channel(
        self,
        replacement: BaseChannel,
        previous: BaseChannel | None,
    ) -> None:
        """Atomically replace a registered channel instance at runtime.

        Removes ``previous`` (if any) and registers ``replacement`` with the
        same name; if the replacement fails to register, ``previous`` is
        restored so a bad swap never leaves a channel silently offline. The
        original error is re-raised after restoration so callers can surface
        or swallow the failed swap consistently.
        """
        if previous is not None:
            await self.remove_channel(previous.name)
        try:
            await self.add_channel(replacement)
        except Exception:
            if previous is not None:
                try:
                    await self.add_channel(previous)
                except Exception:
                    logger.warning(
                        "Failed to restore channel '%s' after a failed swap",
                        previous.name,
                        exc_info=True,
                    )
            raise

    async def remove_channel(self, name: str) -> bool:
        """Hot-remove a channel instance at runtime.

        Stops the channel, cancels its task, and unregisters from the bus.
        Returns True if the channel was found and removed.
        """
        channel = self.bus.channels.get(name)
        if not channel:
            return False

        self._channel_restart_not_before.pop(name, None)
        task = self._channel_tasks.pop(name, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await stop_channel(name, channel)

        channel.clear_listeners()
        self.bus.unregister_channel(name)
        logger.info("Channel '%s' hot-removed", name)
        return True

    def list_instances(self, channel_type: str) -> list[str]:
        """List all instance names for a given channel type."""
        return [n for n, ch in self.bus.channels.items() if self._resolve_channel_type(ch) == channel_type]

    def get_channel_capabilities(self, channel_name: str) -> ChannelCapabilities | None:
        """Get the declared capabilities of a registered channel."""
        channel = self.bus.get_channel(channel_name)
        return channel.capabilities if channel else None

    def get_status(self) -> dict[str, ChannelStatus]:
        """Get status of all registered channels."""
        return {name: channel.status for name, channel in self.bus.channels.items()}

    def collect_all_issues(self) -> dict[str, list[ChannelIssue]]:
        """Collect structured diagnostic issues from all registered channels."""
        result: dict[str, list[ChannelIssue]] = {}
        for name, channel in self.bus.channels.items():
            issues = channel.collect_issues()
            if issues:
                result[name] = issues
        return result

    async def reload_channel(self, name: str) -> bool:
        """Hot-reload a channel: stop the old instance and restart it.

        Returns True if the channel was found and reloaded.
        """
        channel = self.bus.channels.get(name)
        if not channel:
            return False

        self._channel_restart_not_before.pop(name, None)
        task = self._channel_tasks.pop(name, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await stop_channel(name, channel)

        channel._status = ChannelStatus.IDLE
        self._channel_tasks[name] = asyncio.create_task(
            self._run_channel(name, channel),
            name=f"channel-{name}",
        )
        logger.info("Channel '%s' reloaded", name)
        return True

    async def list_channel_groups(self, *, force_refresh: bool = False) -> list[GroupInfo]:
        """Aggregate group lists from all channels concurrently.

        Each provider's ``list_groups`` should set ``GroupInfo.channel``, but this
        method acts as a safety net: any ``GroupInfo`` with an empty ``channel``
        field is patched with the provider's registered name.

        Uses ``asyncio.gather`` for concurrent fetching — total latency equals
        the slowest channel rather than the sum of all channels.
        """
        group_channels: list[tuple[str, BaseChannel]] = [
            (name, ch) for name, ch in self.bus.channels.items() if hasattr(ch, "list_groups")
        ]
        if not group_channels:
            return []

        async def _fetch(name: str, channel: BaseChannel) -> list[GroupInfo]:
            try:
                return await channel.list_groups(force_refresh=force_refresh)
            except Exception:
                logger.warning("Failed to list groups for channel '%s'", name, exc_info=True)
                return []

        results = await asyncio.gather(*[_fetch(n, ch) for n, ch in group_channels])

        all_groups: list[GroupInfo] = []
        for (name, _), groups in zip(group_channels, results, strict=True):
            for g in groups:
                if not g.channel:
                    from dataclasses import replace

                    g = replace(g, channel=name)
                all_groups.append(g)
        return all_groups
