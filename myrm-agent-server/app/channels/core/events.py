"""Generic event publish/subscribe system for channel inter-component communication.

[INPUT]
- collections.abc::Callable

[OUTPUT]
- EventEmitter: Generic event publish/subscribe base class
- EventListener: Type alias for event listener callbacks

[POS]
Channel event infrastructure. Channels emit events (status changes, group updates),
Gateway or other components subscribe. Provides better extensibility and decoupling
than traditional callback patterns.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

EventListener = Callable[[str, object], None]


class EventEmitter:
    """Generic event publish/subscribe system.

    Event names are string identifiers; listeners receive (emitter_name, event_data).

    Example:
        emitter = EventEmitter("my_channel")
        emitter.on("status_change", lambda name, data: print(f"{name}: {data}"))
        emitter.emit("status_change", {"old": "idle", "new": "running"})
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._listeners: dict[str, list[EventListener]] = {}

    def on(self, event_type: str, listener: EventListener) -> None:
        """Register an event listener."""
        self._listeners.setdefault(event_type, []).append(listener)

    def off(self, event_type: str, listener: EventListener) -> None:
        """Unregister an event listener."""
        listeners = self._listeners.get(event_type, [])
        if listener in listeners:
            listeners.remove(listener)

    def emit(self, event_type: str, data: object = None) -> None:
        """Emit an event to all registered listeners."""
        listeners = self._listeners.get(event_type, [])
        for listener in listeners:
            try:
                listener(self._name, data)
            except Exception as e:
                logger.error(
                    "EventEmitter: listener error for %s.%s: %s",
                    self._name,
                    event_type,
                    e,
                    exc_info=True,
                )

    def clear_listeners(self, event_type: str | None = None) -> None:
        """Clear all listeners for a specific event type, or all if None."""
        if event_type is None:
            self._listeners.clear()
        else:
            self._listeners.pop(event_type, None)
