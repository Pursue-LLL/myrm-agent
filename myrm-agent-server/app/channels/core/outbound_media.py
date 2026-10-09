"""Lifecycle of temporary files attached to outbound messages.

[INPUT]
- channels.types.messages::MediaAttachment (POS: outbound attachment with the ``ephemeral`` flag)

[OUTPUT]
- discard_ephemeral_media(): delete ephemeral attachment files that no delivery record needs any more

[POS]
Producers (screenshots, compressed images, synthesized speech) hand their temp files to the message
bus by flagging the attachment ``ephemeral``. The bus calls this once the delivery outcome is final,
so a file is never deleted while a queued, retried or dead-lettered message may still upload it.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Collection, Iterable
from pathlib import Path

from app.channels.types import MediaAttachment

logger = logging.getLogger(__name__)


def discard_ephemeral_media(media: Iterable[MediaAttachment], *, keep_paths: Collection[str | None] = ()) -> None:
    """Delete the temp files of ephemeral attachments, except those a delivery record still references.

    Only files inside the system temp directory are ever removed, so a mis-flagged attachment
    can never delete user or workspace files.
    """
    temp_root = Path(tempfile.gettempdir()).resolve()
    for attachment in media:
        if not attachment.ephemeral or not attachment.path or attachment.path in keep_paths:
            continue
        try:
            path = Path(attachment.path).resolve()
            if path.is_relative_to(temp_root):
                path.unlink(missing_ok=True)
            else:
                logger.warning("Refusing to delete ephemeral attachment outside the temp directory: %s", attachment.path)
        except OSError as exc:
            logger.debug("Could not delete ephemeral attachment %s: %s", attachment.path, exc)
