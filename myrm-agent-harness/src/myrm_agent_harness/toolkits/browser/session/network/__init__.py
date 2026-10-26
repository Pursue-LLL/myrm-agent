"""Network recording of a browser session: the CDP request records and the driver-event request log.

[INPUT]
- intelligence::NetworkIntelligence, EMPTY_RESPONSE (POS: CDP-based API request outcomes and lazy response bodies)
- records::CdpRequestRecord (POS: one tracked request)
- logger::NetworkLogger, RequestInfo, safe_preview and the preview limits (POS: driver-event request log and the masked, bounded previews)

[OUTPUT]
- NetworkIntelligence, CdpRequestRecord, EMPTY_RESPONSE: what `network_log` numbers and `network_detail` / `network_replay` open
- NetworkLogger, RequestInfo: the XHR/Fetch list of an engine without CDP, and the other resources that answered 4xx/5xx
- safe_preview, URL_PREVIEW_CHARS, POST_PREVIEW_CHARS, RAW_PREVIEW_WINDOW: credential-masked text cut to a limit

[POS]
Recorders behind the `network_log` / `network_detail` / `network_replay` actions; the session-level APIs that
compose their answers live in `browser_session_network_mixin.py`.
"""

from .intelligence import EMPTY_RESPONSE, NetworkIntelligence
from .logger import (
    POST_PREVIEW_CHARS,
    RAW_PREVIEW_WINDOW,
    URL_PREVIEW_CHARS,
    NetworkLogger,
    RequestInfo,
    safe_preview,
)
from .records import CdpRequestRecord

__all__ = [
    "EMPTY_RESPONSE",
    "POST_PREVIEW_CHARS",
    "RAW_PREVIEW_WINDOW",
    "URL_PREVIEW_CHARS",
    "CdpRequestRecord",
    "NetworkIntelligence",
    "NetworkLogger",
    "RequestInfo",
    "safe_preview",
]
