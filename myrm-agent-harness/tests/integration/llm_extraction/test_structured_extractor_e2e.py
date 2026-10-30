"""Real-LLM e2e test for the browser session structured extractor.

The extractor routes LLM output through ``extract_answer_text``. This test exercises the real path without
mocking the LLM.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.toolkits.browser.session.structured_extractor import StructuredExtractor

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_browser_structured_extractor_real_llm(basic_llm) -> None:
    """StructuredExtractor returns schema-compliant JSON from real LLM output."""
    extractor = StructuredExtractor(llm=basic_llm)
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "price": {"type": "string"},
            "stock_status": {"type": "string"},
        },
        "required": ["title"],
    }
    page_text = "iPhone 15 Pro\nPrice: $999\nCurrently in stock, ships within 24 hours."
    result = await extractor.extract(text=page_text, schema=schema)
    assert not result.startswith("[Error]"), f"extraction failed: {result}"
    parsed = json.loads(result)
    assert isinstance(parsed, dict)
    assert parsed.get("title"), "title should be extracted from the page text"
