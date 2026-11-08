"""Image request edges: a size or a credential the caller leaves out leaves its field out of the request."""

from __future__ import annotations

from myrm_agent_harness.toolkits.llms.transport import images
from myrm_agent_harness.toolkits.llms.transport.service_routes import service_route


def test_a_gemini_image_model_given_an_unreadable_size_sends_no_image_config() -> None:
    route = service_route("gemini/gemini-3-pro-image-preview", api_key="k", api_base=None)

    request = images._gemini_request(route, "a cat", "huge", 1, 30.0)

    assert request.body == {
        "contents": [{"parts": [{"text": "a cat"}]}],
        "generationConfig": {"response_modalities": ["IMAGE", "TEXT"], "candidateCount": 1},
    }


def test_a_stability_request_with_an_unreadable_size_and_no_key_names_neither_ratio_nor_credentials() -> None:
    route = service_route("stability/sd3", api_key=None, api_base=None)

    request = images._stability_request(route, "a cat", "huge", 30.0)

    assert request.form == {"prompt": "a cat", "output_format": "png"}
    assert request.headers == {"Accept": "application/json"}
