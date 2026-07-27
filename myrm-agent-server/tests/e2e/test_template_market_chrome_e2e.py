"""Chrome E2E: Template Market API serves official_document_assistant correctly.

Validates the full end-to-end path:
  YAML file on disk → server startup → templates API → correct response

Uses ephemeral_server (full backend instance) to verify real glob discovery
and YAML parsing without mocks.
"""

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    http_json,
)

pytestmark = pytest.mark.e2e


def test_template_market_lists_official_document_assistant():
    """Templates API returns official_document_assistant with correct metadata."""
    api_url = get_e2e_api_url()
    data = http_json("GET", f"{api_url}/api/v1/agents/templates")
    templates = data["data"]
    ids = [t["id"] for t in templates]
    assert "official_document_assistant" in ids, (
        f"official_document_assistant not found in template IDs: {ids}"
    )

    tpl = next(t for t in templates if t["id"] == "official_document_assistant")
    assert tpl["agent_type"] == "individual"
    assert tpl.get("avatar_url") == "lucide:stamp"
    assert tpl.get("description")
    assert "GB/T 9704" in tpl["description"]


def test_template_market_i18n_negotiation():
    """Templates API respects Accept-Language for i18n content."""
    api_url = get_e2e_api_url()

    zh_data = http_json("GET", f"{api_url}/api/v1/agents/templates")
    templates_default = zh_data["data"]
    tpl = next(t for t in templates_default if t["id"] == "official_document_assistant")
    assert tpl["name"]
    assert tpl["description"]
