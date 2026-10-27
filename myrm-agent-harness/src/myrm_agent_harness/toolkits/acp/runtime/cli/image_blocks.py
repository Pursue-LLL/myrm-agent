"""Image files of a turn as the base64 blocks a CLI reads from its stdin.

A CLI that is only told a path decides for itself what to do with it: Claude's ``@`` file mention silently drops
every image above 256 KiB, which is below most screenshots. A block carries the bytes in the request itself, so
the image reaches the model whatever its size, whatever directory it lives in and whatever the permission mode.

[INPUT]
- utils.mime_types::VISION_IMAGE_MIME_TYPES, detect_image_mime (POS: Centralized image MIME type utilities.)

[OUTPUT]
- ImageBlock: one image as a media type plus base64 data
- load_image_blocks: the readable image files of a turn, in order

[POS]
Image input of CliRuntime for a CLI that takes base64 blocks. The host bounds the size of what it hands over (the
server stages at most 5 MiB per image); this module only decides whether a file is an image the CLIs accept.
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from myrm_agent_harness.utils.mime_types import VISION_IMAGE_MIME_TYPES, detect_image_mime

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ImageBlock:
    """One image of a turn: its media type and its bytes in base64."""

    media_type: str
    data: str


def load_image_blocks(paths: Sequence[str]) -> list[ImageBlock]:
    """The blocks of the image files in ``paths``, keeping their order.

    Blocking file I/O: callers on an event loop run it in a thread. A file that cannot be read or is not an image is
    left out and logged without its path (a path can carry a user name).
    """
    blocks: list[ImageBlock] = []
    for path in paths:
        try:
            raw = Path(path).read_bytes()
        except OSError as exc:
            logger.warning("cli_image_skipped reason=unreadable error=%s", type(exc).__name__)
            continue
        # The first bytes say what a file is, its name does not.
        media_type = detect_image_mime(raw, fallback="")
        if media_type not in VISION_IMAGE_MIME_TYPES:
            logger.warning("cli_image_skipped reason=unknown_format")
            continue
        blocks.append(ImageBlock(media_type, base64.b64encode(raw).decode("ascii")))
    return blocks
