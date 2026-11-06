"""Create every channel type the product offers through the packaged backend, the way the settings page does.

PyInstaller bundles what its scan of `import` statements reaches, and the channel registry loads each provider by a
computed module name, so a bundle can start, answer `/health` and serve its data while the backend refuses most channel
types ("unavailable (missing SDK?)"). Only a request that creates a channel shows it.

Each type is created once without credentials, so nothing connects anywhere, and removed again, so a profile that is
not a throwaway one is left as it was. Standard library only.
"""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import NamedTuple

# The built-in types of `_BUILTIN_SPECS` in app/channels/providers/registry.py;
# tests/architecture/test_desktop_sidecar_modules.py pins the two to each other.
CHANNEL_TYPES = (
    "telegram",
    "webhook",
    "whatsapp",
    "discord",
    "feishu",
    "slack",
    "dingtalk",
    "qq",
    "onebot",
    "wecom",
    "wecom_aibot",
    "wechat",
    "wechat_official",
    "teams",
    "googlechat",
    "matrix",
    "email",
    "signal",
    "imessage",
    "line",
    "irc",
    "mattermost",
    "zalo",
    "voice",
    "sms",
    "github",
)
# The types a bundle may refuse: their provider imports an SDK at module level and the bundle leaves that SDK out
# (CHANNEL_SDKS_NOT_SHIPPED in myrm-agent-desktop/sidecar/bundle_inventory.py). The settings page lists them as
# unavailable; any other refusal is a module the bundle lost.
UNAVAILABLE_WITHOUT_SDK = frozenset({"discord"})

MANAGE_API = "/api/v1/channels/manage"
REQUEST_TIMEOUT_SEC = 30.0
# Right after `/health` the backend's own start-up work can still hold the SQLite lock, and a create answers 503. The
# window is shared by all types, so a lock that never lets go costs one window, not one per type.
LOCKED_RETRY_SEC = 60.0
RETRY_INTERVAL_SEC = 2.0
DETAIL_CHARS = 200

# Requests must reach 127.0.0.1 directly, whatever proxy a developer machine or runner exports.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class Answer(NamedTuple):
    status: int
    body: bytes


@dataclass(frozen=True)
class ChannelCheck:
    """`created` and `unavailable` are the types that behaved as designed, `problems` the ones that did not, and
    `leftovers` the created instances that could not be removed again."""

    created: tuple[str, ...]
    unavailable: tuple[str, ...]
    problems: tuple[str, ...]
    leftovers: tuple[str, ...]


def _send(method: str, url: str, payload: Mapping[str, str] | None = None) -> Answer | None:
    """The answer to a request, an error status included, or None when nothing answered."""
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(  # noqa: S310 - the loopback address of the backend under test plus a fixed path
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with _OPENER.open(request, timeout=REQUEST_TIMEOUT_SEC) as response:
            return Answer(response.status, response.read())
    except urllib.error.HTTPError as error:
        return Answer(error.code, error.read())
    except (OSError, http.client.HTTPException):
        return None


def _json_object(body: bytes) -> Mapping[str, object]:
    try:
        payload = json.loads(body)
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _create(base_url: str, channel_type: str, lock_deadline: float) -> Answer | None:
    """POST one instance; HTTP 503 is the lock of the backend's own start-up work, so it is asked again."""
    while True:
        answer = _send("POST", f"{base_url}{MANAGE_API}/instances", {"channelType": channel_type})
        if answer is None or answer.status != 503 or time.monotonic() >= lock_deadline:
            return answer
        time.sleep(RETRY_INTERVAL_SEC)


def _detail(answer: Answer) -> str:
    """The backend's own explanation: the `detail` of its error body, else the start of the body."""
    detail = _json_object(answer.body).get("detail")
    return str(detail if detail is not None else answer.body.decode("utf-8", errors="replace"))[:DETAIL_CHARS]


def _listed_unavailable(base_url: str) -> frozenset[str]:
    """The channel types the settings page reports as unavailable."""
    answer = _send("GET", f"{base_url}{MANAGE_API}/status")
    if answer is None or answer.status != 200:
        return frozenset()
    try:
        entries = json.loads(answer.body)
    except ValueError:
        return frozenset()
    if not isinstance(entries, list):
        return frozenset()
    return frozenset(
        entry["channelType"]
        for entry in entries
        if isinstance(entry, dict) and entry.get("status") == "unavailable" and isinstance(entry.get("channelType"), str)
    )


def _removed(base_url: str, instance_id: str) -> bool:
    answer = _send("DELETE", f"{base_url}{MANAGE_API}/instances/{instance_id}")
    return answer is not None and answer.status == 204


def create_every_channel(base_url: str) -> ChannelCheck:
    """Create one instance of each type, hold the refusals against the settings status, remove what was created."""
    created: dict[str, str | None] = {}
    refused: list[str] = []
    problems: list[str] = []
    backend_gone = False
    lock_deadline = time.monotonic() + LOCKED_RETRY_SEC
    for channel_type in CHANNEL_TYPES:
        answer = _create(base_url, channel_type, lock_deadline)
        if answer is None:
            problems.append(f"{channel_type}: no answer from the backend; the other types were not tried")
            backend_gone = True
            break
        if answer.status == 201:
            instance_id = _json_object(answer.body).get("instanceId")
            created[channel_type] = instance_id if isinstance(instance_id, str) else None
        elif answer.status == 400 and channel_type in UNAVAILABLE_WITHOUT_SDK:
            refused.append(channel_type)
        else:
            problems.append(f"{channel_type}: HTTP {answer.status} {_detail(answer)}")

    listed = _listed_unavailable(base_url) if refused else frozenset()
    problems.extend(
        f"{channel_type}: refused for a missing SDK, but the settings status does not list it as unavailable"
        for channel_type in refused
        if channel_type not in listed
    )
    leftovers: list[str] = []
    for channel_type, instance_id in created.items():
        # A backend that stopped answering would make every removal wait out its timeout.
        if backend_gone or instance_id is None or not _removed(base_url, instance_id):
            which = f"instance {instance_id}" if instance_id else "the answer named no instance"
            leftovers.append(f"{channel_type} ({which})")
    return ChannelCheck(
        created=tuple(created),
        unavailable=tuple(channel_type for channel_type in refused if channel_type in listed),
        problems=tuple(problems),
        leftovers=tuple(leftovers),
    )
