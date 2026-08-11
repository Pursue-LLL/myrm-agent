"""Wire types for extension CDP relay (server ↔ MV3 extension ↔ Playwright).

[INPUT]
- typing::TypedDict, dataclasses (POS: Python stdlib wire types)

[OUTPUT]
- RelayTabInfo, RelayCommand variants, relay timing constants

[POS]
Shared wire types and constants for the extension CDP relay subpackage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

BROWSER_TARGET_ID = "myrm-extension-relay"
BROWSER_CONTEXT_ID = "myrm-extension-context"
RELAY_COMMAND_TIMEOUT_S = 15.0


@dataclass(frozen=True, slots=True)
class RelayTabInfo:
    tab_id: int
    url: str
    title: str
    active: bool = False


class RelayAttachCommand(TypedDict):
    type: Literal["attach"]
    tabId: int


class RelayDetachCommand(TypedDict):
    type: Literal["detach"]
    tabId: int


class RelayCdpCommand(TypedDict, total=False):
    type: Literal["cdp"]
    tabId: int
    sessionId: str
    method: str
    params: dict[str, object]


class RelayCreateTabCommand(TypedDict, total=False):
    type: Literal["createTab"]
    url: str
    background: bool


RelayCommand = RelayAttachCommand | RelayDetachCommand | RelayCdpCommand | RelayCreateTabCommand
