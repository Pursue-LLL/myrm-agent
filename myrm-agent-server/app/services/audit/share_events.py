"""Share events in the server log: which links get created, and whether opening one worked.

[INPUT]
- app.core.security.share.share_hmac::decode_unverified_payload, token_log_id (POS: share token decoding + short non-reversible token id)
- app.core.security.share.share_links::ShareKind (POS: where each share token kind is served)
- app.core.security.share.share_status_page::ShareLinkState (POS: why a share link cannot be opened)

[OUTPUT]
- ShareSource: where a link was created (the share dialog, or an IM button)
- ShareDenial: why opening a link was refused (a lifecycle state, or a wrong password)
- report_share_created: one ``share_created`` line per link created
- report_share_access: one ``share_access`` line per entry served or refused

[POS]
Nothing counted shared links, so whether anyone shares and opens them, and why opening fails, could not be answered.
These two INFO lines are the whole record: no table, no counter service. A link is named by its short token id, never
the token. Opening a bundle's entry page counts once (its assets do not), a wrong password counts each time (the lockout
caps those), and a refusal of text that does not decode as one of our tokens is not logged, so a scanner cannot
flood the log.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Literal

from app.core.security.share.share_hmac import decode_unverified_payload, token_log_id
from app.core.security.share.share_links import ShareKind
from app.core.security.share.share_status_page import ShareLinkState

logger = logging.getLogger(__name__)

ShareDenial = ShareLinkState | Literal["wrong_password"]


class ShareSource(StrEnum):
    DIALOG = "dialog"
    IM = "im"


def report_share_created(kind: ShareKind, source: ShareSource, token: str) -> None:
    """Record that a share link of *kind* was just created by *source*."""
    logger.info("share_created kind=%s source=%s token=%s", kind, source, token_log_id(token))


def report_share_access(kind: ShareKind, token: str, *, denied: ShareDenial | None = None) -> None:
    """Record that opening a share link was granted, or refused for the reason in *denied*."""
    if denied is None:
        logger.info("share_access kind=%s result=granted token=%s", kind, token_log_id(token))
    elif decode_unverified_payload(token) is not None:
        reason = denied.value if isinstance(denied, ShareLinkState) else denied
        logger.info("share_access kind=%s result=denied reason=%s token=%s", kind, reason, token_log_id(token))
