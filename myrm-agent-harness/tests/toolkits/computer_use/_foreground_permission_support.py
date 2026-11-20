"""Builders shared by the foreground-permission integration tests."""

from __future__ import annotations

import io
import random
from unittest.mock import AsyncMock, MagicMock

from PIL import Image, ImageDraw

from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef
from myrm_agent_harness.toolkits.computer_use.types import ActionResult, ScreenInfo


def _realistic_png_bytes() -> bytes:
    """Generate a 1920x1080 noisy PNG that passes the min-size check after JPEG encoding."""
    random.seed(42)
    img = Image.new("RGB", (1920, 1080))
    draw = ImageDraw.Draw(img)
    for y in range(0, 1080, 10):
        for x in range(0, 1920, 10):
            colour = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
            draw.rectangle((x, y, x + 9, y + 9), fill=colour)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


FAKE_SCREENSHOT = _realistic_png_bytes()

NON_SENSITIVE_FG_INFO: dict[str, str | int | bool] = {
    "app_name": "Safari",
    "window_title": "Example Page",
    "interactive_estimate": 5,
    "needs_permission": False,
}


def assert_control_blocked(result: str | list[object]) -> str:
    """Mutating vision/interact paths block via per-app or foreground gate; returns the lowered refusal."""
    assert isinstance(result, str), "a refused action answers with text, never with a frame"
    lowered = result.lower()
    assert "control denied" in lowered or "permission denied" in lowered
    return lowered


def make_backend() -> MagicMock:
    """Create a fake backend with minimal screen info and async methods."""
    b = MagicMock()
    b.screen_info.return_value = ScreenInfo(width=1920, height=1080, dpi_scale=1.0)
    b.screenshot = AsyncMock(return_value=FAKE_SCREENSHOT)
    b.click = AsyncMock(return_value=ActionResult(success=True, output="clicked"))
    b.type_text = AsyncMock(return_value=ActionResult(success=True, output="typed"))
    return b


def make_element(x: int = 100, y: int = 200) -> ElementRef:
    return ElementRef(
        ref_id="e0",
        role="button",
        name="Submit",
        bbox=BBox(x=x, y=y, width=40, height=20),
        backend_key="ax_key_0",
    )
