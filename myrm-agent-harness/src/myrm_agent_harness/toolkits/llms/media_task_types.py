"""Async media job type ids shared by the harness enqueue side and the server executors.

[INPUT]
- (none)

[OUTPUT]
- TASK_TYPE_IMAGE_GENERATE / TASK_TYPE_VIDEO_GENERATE: canonical async job type ids

[POS]
Single source of the two media job type strings (``Task.task_type``). Payload and result shapes are plain dicts at
the ``toolkits/tasks`` queue layer; the enqueue side is ``llms/image/async_image_engine.py`` and
``llms/video/async_video_engine.py``, the executors live in the server.
"""

from __future__ import annotations

TASK_TYPE_IMAGE_GENERATE = "image_generate"
TASK_TYPE_VIDEO_GENERATE = "video_generate"

__all__ = [
    "TASK_TYPE_IMAGE_GENERATE",
    "TASK_TYPE_VIDEO_GENERATE",
]
