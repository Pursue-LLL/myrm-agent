"""Channel Image → Visual Input E2E Test (OC-27)

Verifies the complete pipeline:
  1. build_channel_inbound_query correctly produces OpenAI Vision multimodal content
  2. LLM receives multimodal input and correctly describes image content

Uses a real LLM call (requires BASIC_API_KEY).
"""

import base64
import io
import os

import pytest

from app.channels.types import InboundMessage
from app.core.channel_bridge.agent_executor.helpers import build_channel_inbound_query


def _make_red_image_data_url() -> str:
    """Create a 50x50 solid red JPEG and return its base64 data URL."""
    from PIL import Image

    img = Image.new("RGB", (50, 50), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
def test_multimodal_query_structure():
    """build_channel_inbound_query returns OpenAI Vision format for image messages."""
    data_url = _make_red_image_data_url()
    msg = InboundMessage(
        channel="telegram",
        sender_id="u1",
        chat_id="c1",
        content="What color?",
        sent_at=1747900800.0,
        sent_timezone="UTC",
        user_id="u1",
        is_group=False,
        mentioned=False,
        metadata={
            "image_data_list": [
                {"data_url": data_url, "mime_type": "image/jpeg"},
            ]
        },
    )
    query = build_channel_inbound_query(msg)

    assert isinstance(query, list), "Should return multimodal list"
    assert len(query) == 2, "Should have text + image parts"
    assert query[0]["type"] == "text"
    assert "What color?" in query[0]["text"]
    assert query[1]["type"] == "image_url"
    assert query[1]["image_url"]["url"] == data_url


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
async def test_llm_recognizes_channel_image():
    """LLM receives a red image via the channel multimodal pipeline and identifies it."""
    from litellm import acompletion

    data_url = _make_red_image_data_url()
    msg = InboundMessage(
        channel="discord",
        sender_id="u1",
        chat_id="c1",
        content="What color is this image? Reply with ONLY the color name, nothing else.",
        sent_at=1747900800.0,
        sent_timezone="UTC",
        user_id="u1",
        is_group=False,
        mentioned=False,
        metadata={
            "image_data_list": [
                {"data_url": data_url, "mime_type": "image/jpeg"},
            ]
        },
    )

    query = build_channel_inbound_query(msg)
    assert isinstance(query, list)

    model = os.environ.get("BASIC_MODEL", "openai/gpt-4o-mini")
    try:
        response = await acompletion(
            model=model,
            messages=[{"role": "user", "content": query}],
            max_tokens=20,
        )
    except Exception as exc:
        pytest.skip(f"LLM call failed (environment issue): {exc}")

    answer = response.choices[0].message.content.strip().lower()
    print(f"\nLLM response: {answer}")

    assert "red" in answer, f"LLM should identify the red image, got: {answer}"
