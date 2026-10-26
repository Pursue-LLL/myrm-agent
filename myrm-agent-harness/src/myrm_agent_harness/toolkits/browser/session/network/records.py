"""The shapes the CDP network recorder works with: event payloads and the tracked request record.

[INPUT]
- (none)

[OUTPUT]
- CdpRequest / CdpResponse / CdpRequestWillBeSent / CdpResponseReceived / CdpLoadingFailed / CdpFrameNavigated: the
  parts of the CDP `Network` and `Page` event payloads the recorder reads
- CdpRequestRecord: one tracked request, `seq` being the number network_log shows for it

[POS]
Data shapes of `intelligence.py`, kept apart so the recorder module holds behaviour only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


class CdpRequest(TypedDict, total=False):
    url: str
    method: str
    postData: str


class CdpResponse(TypedDict, total=False):
    status: int
    mimeType: str


class CdpRequestWillBeSent(TypedDict, total=False):
    requestId: str
    type: str
    request: CdpRequest
    redirectResponse: CdpResponse


class CdpResponseReceived(TypedDict, total=False):
    requestId: str
    response: CdpResponse


class CdpCorsErrorStatus(TypedDict, total=False):
    corsError: str


class CdpLoadingFailed(TypedDict, total=False):
    requestId: str
    errorText: str
    canceled: bool
    corsErrorStatus: CdpCorsErrorStatus


class CdpFrame(TypedDict, total=False):
    parentId: str


class CdpFrameNavigated(TypedDict, total=False):
    frame: CdpFrame


@dataclass(frozen=True, slots=True)
class CdpRequestRecord:
    """Tracked CDP request with requestId for lazy body retrieval.

    Attributes:
        request_id: CDP-assigned request identifier for getResponseBody
        url: Request URL
        method: HTTP method
        resource_type: Network resource type (XHR or Fetch)
        seq: The number network_log shows for the request, unique for the session
        status: HTTP response status code; for a redirect hop, the status of the redirect it answered with
        mime_type: Response MIME type
        failure: The browser's error when the request ended without a usable response (e.g. net::ERR_BLOCKED_BY_CLIENT)
        post_data: Raw POST body window; get_summary redacts it before cutting it to the preview
        timestamp: Request time (monotonic)
        epoch: The page the request was made on; only the current page's records are listed and can be opened
    """

    request_id: str
    url: str
    method: str
    resource_type: str
    seq: int
    status: int | None = None
    mime_type: str | None = None
    failure: str | None = None
    post_data: str | None = None
    timestamp: float = 0.0
    epoch: int = 0
