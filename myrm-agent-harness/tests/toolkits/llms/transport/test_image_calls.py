"""Image calls: request shapes per provider family, answer parsing, refusals inside a 200, multipart encoding."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import httpx
import pytest

from myrm_agent_harness.toolkits.llms.transport import images
from myrm_agent_harness.toolkits.llms.transport.http import PreparedRequest, _build, _with_json_headers
from myrm_agent_harness.toolkits.llms.transport.images import (
    GeneratedImage,
    ImageProviderError,
    aedit_images,
    agenerate_images,
)
from myrm_agent_harness.toolkits.llms.transport.profile import UnsupportedProviderError

Answer = dict[str, object]
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[Answer], list[PreparedRequest]]]:
    requests: list[PreparedRequest] = []
    answer_box: list[Answer] = [{}]

    async def fake_send(request: PreparedRequest) -> Answer:
        requests.append(request)
        return answer_box[0]

    monkeypatch.setattr(images, "asend_json", fake_send)

    def arm(answer: Answer) -> list[PreparedRequest]:
        answer_box[0] = answer
        return requests

    yield arm


async def _generate(model: str, *, size: str = "1024x1024", n: int = 1, **overrides: object) -> list[GeneratedImage]:
    params: dict[str, object] = {
        "quality": "standard",
        "style": None,
        "api_key": "k",
        "api_base": None,
        "timeout": 30.0,
    }
    params.update(overrides)
    return await agenerate_images(model, "a cat", size=size, n=n, **params)  # type: ignore[arg-type]


_OPENAI_ANSWER: Answer = {
    "data": [{"url": "https://img/1.png", "revised_prompt": "a fluffy cat"}, {"b64_json": "QUJD"}]
}


class TestOpenAIFamily:
    async def test_request_and_parse(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent(_OPENAI_ANSWER)
        result = await _generate("dall-e-3", style="vivid")

        (request,) = requests
        assert request.url == "https://api.openai.com/v1/images/generations"
        assert request.headers["Authorization"] == "Bearer k"
        assert request.body == {
            "prompt": "a cat",
            "n": 1,
            "size": "1024x1024",
            "model": "dall-e-3",
            "quality": "standard",
            "style": "vivid",
        }
        assert request.timeout == 30.0
        assert result == [
            GeneratedImage(url="https://img/1.png", revised_prompt="a fluffy cat"),
            GeneratedImage(b64_json="QUJD"),
        ]

    async def test_quality_and_style_are_omitted_when_unset(
        self, sent: Callable[[Answer], list[PreparedRequest]]
    ) -> None:
        requests = sent(_OPENAI_ANSWER)
        await _generate("gpt-image-1", quality=None)
        assert set(requests[0].body or {}) == {"prompt", "n", "size", "model"}

    @pytest.mark.parametrize("model", ["gpt-image-1", "dall-e-2", "xai/grok-imagine-image"])
    async def test_style_is_sent_to_dall_e_3_only(
        self, sent: Callable[[Answer], list[PreparedRequest]], model: str
    ) -> None:
        requests = sent(_OPENAI_ANSWER)
        await _generate(model, style="vivid")
        assert "style" not in (requests[0].body or {})

    @pytest.mark.parametrize(
        ("model", "url"),
        [
            ("xai/grok-imagine-image", "https://api.x.ai/v1/images/generations"),
            ("together_ai/black-forest-labs/FLUX.1-schnell", "https://api.together.xyz/v1/images/generations"),
            ("flux/schnell", "https://api.together.xyz/v1/images/generations"),
        ],
    )
    async def test_provider_endpoints(
        self, sent: Callable[[Answer], list[PreparedRequest]], model: str, url: str
    ) -> None:
        requests = sent(_OPENAI_ANSWER)
        await _generate(model)
        assert requests[0].url == url

    async def test_flux_alias_resolves_to_the_together_model(
        self, sent: Callable[[Answer], list[PreparedRequest]]
    ) -> None:
        requests = sent(_OPENAI_ANSWER)
        await _generate("flux/pro")
        assert requests[0].body["model"] == "black-forest-labs/FLUX.1.1-pro"  # type: ignore[index]

    async def test_gateway_base_keeps_the_model_id(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent(_OPENAI_ANSWER)
        await _generate("gpt-image-1", api_base="https://gw.example/image_gen")
        assert requests[0].url == "https://gw.example/image_gen/images/generations"
        assert requests[0].body["model"] == "gpt-image-1"  # type: ignore[index]

    async def test_full_endpoint_url_is_not_doubled(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent(_OPENAI_ANSWER)
        await _generate("dall-e-3", api_base="https://gw.example/v1/images/generations")
        assert requests[0].url == "https://gw.example/v1/images/generations"

    async def test_azure_addresses_the_deployment_in_the_url(
        self, sent: Callable[[Answer], list[PreparedRequest]]
    ) -> None:
        requests = sent(_OPENAI_ANSWER)
        await _generate("azure/dalle3", api_base="https://r.openai.azure.com")
        (request,) = requests
        assert request.url == "https://r.openai.azure.com/openai/deployments/dalle3/images/generations"
        assert request.query == {"api-version": "2025-02-01-preview"}
        assert request.headers["api-key"] == "k"
        assert "model" not in (request.body or {})

    async def test_empty_answer_is_an_error(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        sent({"data": []})
        with pytest.raises(ValueError, match="returned no image"):
            await _generate("dall-e-3")

    async def test_unknown_model_without_base_is_rejected(self) -> None:
        with pytest.raises(UnsupportedProviderError):
            await _generate("mystery-image-model")

    async def test_no_environment_credential_is_read(
        self, sent: Callable[[Answer], list[PreparedRequest]], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "from-env")
        requests = sent(_OPENAI_ANSWER)
        await _generate("dall-e-3", api_key=None)
        assert "Authorization" not in requests[0].headers


class TestEdit:
    async def test_dall_e_2_uploads_a_single_image(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent(_OPENAI_ANSWER)
        result = await aedit_images(
            "dall-e-2",
            _PNG,
            "make it blue",
            mask=b"\x89PNG\r\n\x1a\nmask",
            size="1024x1024",
            n=1,
            api_key="k",
            api_base=None,
            timeout=30.0,
        )

        (request,) = requests
        assert request.url == "https://api.openai.com/v1/images/edits"
        assert request.body is None
        assert request.form == {"prompt": "make it blue", "n": "1", "size": "1024x1024", "model": "dall-e-2"}
        assert request.files is not None
        assert set(request.files) == {"image", "mask"}
        assert request.files["image"] == ("image.png", _PNG, "image/png")
        assert len(result) == 2

    async def test_gpt_image_uploads_a_list_field(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent(_OPENAI_ANSWER)
        await aedit_images(
            "gpt-image-1", _PNG, "edit", mask=None, size="1024x1024", n=1, api_key="k", api_base=None, timeout=30.0
        )
        assert requests[0].files is not None
        assert set(requests[0].files) == {"image[]"}

    async def test_jpeg_upload_is_labelled_by_its_content(
        self, sent: Callable[[Answer], list[PreparedRequest]]
    ) -> None:
        requests = sent(_OPENAI_ANSWER)
        jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 16
        await aedit_images(
            "gpt-image-1", jpeg, "edit", mask=None, size="1024x1024", n=1, api_key="k", api_base=None, timeout=30.0
        )
        assert requests[0].files is not None
        assert requests[0].files["image[]"][2] == "image/jpeg"  # type: ignore[index]

    async def test_provider_without_an_edit_endpoint_is_rejected(self) -> None:
        with pytest.raises(UnsupportedProviderError, match="no image editing endpoint"):
            await aedit_images(
                "gemini/imagen-3.0-generate-002",
                _PNG,
                "edit",
                mask=None,
                size="1024x1024",
                n=1,
                api_key="k",
                api_base=None,
                timeout=30.0,
            )


class TestGemini:
    async def test_imagen_predict(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent({"predictions": [{"bytesBase64Encoded": "QUJD"}]})
        result = await _generate("gemini/imagen-3.0-generate-002", size="1792x1024", n=2)

        (request,) = requests
        assert request.url == "https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:predict"
        assert request.headers == {"x-goog-api-key": "k"}
        assert request.body == {
            "instances": [{"prompt": "a cat"}],
            "parameters": {"sampleCount": 2, "aspectRatio": "16:9"},
        }
        assert result == [GeneratedImage(b64_json="QUJD")]

    async def test_aspect_ratio_size_is_accepted_directly(
        self, sent: Callable[[Answer], list[PreparedRequest]]
    ) -> None:
        requests = sent({"predictions": [{"bytesBase64Encoded": "QUJD"}]})
        await _generate("gemini/imagen-3.0-generate-002", size="9:16")
        assert requests[0].body["parameters"] == {"sampleCount": 1, "aspectRatio": "9:16"}  # type: ignore[index]

    async def test_larger_output_requests_its_image_size(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent({"predictions": [{"bytesBase64Encoded": "QUJD"}]})
        await _generate("gemini/imagen-4.0-generate-001", size="2048x2048")
        assert requests[0].body["parameters"] == {  # type: ignore[index]
            "sampleCount": 1,
            "aspectRatio": "1:1",
            "imageSize": "2K",
        }

    async def test_gemini_image_model_uses_generate_content(
        self, sent: Callable[[Answer], list[PreparedRequest]]
    ) -> None:
        requests = sent(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": "here"}, {"inlineData": {"mimeType": "image/png", "data": "QUJD"}}]
                        }
                    }
                ]
            }
        )
        result = await _generate("gemini/gemini-3-pro-image-preview", size="2048x2048")

        (request,) = requests
        assert request.url.endswith("/models/gemini-3-pro-image-preview:generateContent")
        assert request.body == {
            "contents": [{"parts": [{"text": "a cat"}]}],
            "generationConfig": {
                "response_modalities": ["IMAGE", "TEXT"],
                "candidateCount": 1,
                "imageConfig": {"aspectRatio": "1:1", "imageSize": "2K"},
            },
        }
        assert result == [GeneratedImage(b64_json="QUJD")]

    async def test_flash_image_has_a_fixed_output_size(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent({"candidates": []})
        with pytest.raises(ValueError, match="returned no image"):
            await _generate("gemini/gemini-2.5-flash-image", size="2048x2048")
        config = requests[0].body["generationConfig"]  # type: ignore[index]
        assert config["imageConfig"] == {"aspectRatio": "1:1"}  # type: ignore[index]


class TestStability:
    async def test_form_request_and_parse(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent({"image": "QUJD", "finish_reason": "SUCCESS"})
        result = await _generate("stability/stable-diffusion-xl", size="1792x1024")

        (request,) = requests
        assert request.url == "https://api.stability.ai/v2beta/stable-image/generate/sd3"
        assert request.headers == {"Accept": "application/json", "Authorization": "Bearer k"}
        assert request.form == {"prompt": "a cat", "output_format": "png", "aspect_ratio": "16:9"}
        assert request.files == {"none": ""}
        assert request.body is None
        assert result == [GeneratedImage(b64_json="QUJD")]

    @pytest.mark.parametrize(
        ("model", "endpoint"),
        [
            ("stability/sd3.5-large-turbo", "/v2beta/stable-image/generate/sd3"),
            ("stability/stable-image-ultra", "/v2beta/stable-image/generate/ultra"),
            ("stability/stable-image-core", "/v2beta/stable-image/generate/core"),
        ],
    )
    async def test_model_selects_the_endpoint(
        self, sent: Callable[[Answer], list[PreparedRequest]], model: str, endpoint: str
    ) -> None:
        requests = sent({"image": "QUJD"})
        await _generate(model)
        assert requests[0].url == f"https://api.stability.ai{endpoint}"

    async def test_filtered_content_is_a_refusal(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        sent({"image": "QUJD", "finish_reason": "CONTENT_FILTERED"})
        with pytest.raises(ImageProviderError) as excinfo:
            await _generate("stability/sd3")
        assert excinfo.value.status_code == 400


class TestMiniMax:
    async def test_request_and_parse(self, sent: Callable[[Answer], list[PreparedRequest]]) -> None:
        requests = sent(
            {"base_resp": {"status_code": 0}, "data": {"image_urls": ["https://img/1.png"], "image_base64": ["QUJD"]}}
        )
        result = await _generate("minimax_image/image-01", size="1280x720", n=2)

        (request,) = requests
        assert request.url == "https://api.minimax.io/v1/image_generation"
        assert request.headers == {"Authorization": "Bearer k"}
        assert request.body == {
            "model": "image-01",
            "prompt": "a cat",
            "aspect_ratio": "16:9",
            "response_format": "url",
            "n": 2,
        }
        assert result == [GeneratedImage(url="https://img/1.png"), GeneratedImage(b64_json="QUJD")]

    @pytest.mark.parametrize(("code", "status"), [(1004, 401), (1026, 400), (1002, 429), (9999, 500)])
    async def test_provider_status_maps_to_http_status(
        self, sent: Callable[[Answer], list[PreparedRequest]], code: int, status: int
    ) -> None:
        sent({"base_resp": {"status_code": code, "status_msg": "refused"}})
        with pytest.raises(ImageProviderError) as excinfo:
            await _generate("minimax_image/image-01")
        assert excinfo.value.status_code == status


class TestUnsupportedWires:
    @pytest.mark.parametrize("model", ["anthropic/claude-sonnet-4-5", "ollama/llava"])
    async def test_chat_only_providers_have_no_image_endpoint(self, model: str) -> None:
        with pytest.raises(UnsupportedProviderError, match="no image generation endpoint"):
            await _generate(model)


class TestMultipartEncoding:
    def test_form_and_files_become_a_multipart_body(self) -> None:
        request = PreparedRequest(
            provider="openai",
            url="https://api.openai.com/v1/images/edits",
            headers={"Authorization": "Bearer k"},
            body=None,
            timeout=10.0,
            form={"prompt": "edit"},
            files={"image[]": ("image.png", _PNG, "image/png")},
        )
        built = _build(httpx.Client(), _with_json_headers(request))

        assert built.headers["content-type"].startswith("multipart/form-data; boundary=")
        body = built.read()
        assert b'name="prompt"' in body
        assert b'name="image[]"; filename="image.png"' in body
        assert _PNG in body

    def test_json_content_type_is_not_forced_on_a_multipart_request(self) -> None:
        request = PreparedRequest(
            provider="stability", url="https://x", headers={}, body=None, timeout=1.0, form={}, files={"none": ""}
        )
        assert "Content-Type" not in _with_json_headers(request).headers
