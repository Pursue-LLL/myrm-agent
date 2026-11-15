"""Reference matrix of the single media input resolver."""

from __future__ import annotations

import base64
import threading
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx
import pytest

from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError
from myrm_agent_harness.core.security.http.secure_fetch import ContentTooLargeError
from myrm_agent_harness.toolkits.llms import media_inputs
from myrm_agent_harness.toolkits.llms.media_inputs import MediaInputError, MediaInputPolicy, resolve_media_inputs

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32


def _loader(store: dict[str, bytes]) -> Callable[[str], Awaitable[bytes]]:
    async def load(ref: str) -> bytes:
        return store[ref]

    return load


@pytest.fixture
def root(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / "_uploaded").mkdir(parents=True)
    (workspace / "_uploaded" / "photo.png").write_bytes(PNG)
    (workspace / "clip.mp4").write_bytes(MP4)
    (workspace / ".env").write_text("OPENAI_API_KEY=sk-secret\n")
    return workspace


@pytest.fixture
def policy(root: Path) -> MediaInputPolicy:
    return MediaInputPolicy(allowed_roots=(root,), loaders={"media": _loader({"abc": PNG, "vid": MP4})})


async def _images(policy: MediaInputPolicy, *refs: str) -> list[bytes]:
    return await resolve_media_inputs(list(refs), "image", policy, field_name="image_url")


class TestAccepted:
    async def test_media_reference_uses_the_injected_loader(self, policy: MediaInputPolicy) -> None:
        assert await _images(policy, "media://abc") == [PNG]

    async def test_relative_path_resolves_under_the_allowed_root(self, policy: MediaInputPolicy) -> None:
        assert await _images(policy, "_uploaded/photo.png") == [PNG]

    async def test_absolute_path_inside_the_root(self, policy: MediaInputPolicy, root: Path) -> None:
        assert await _images(policy, str(root / "_uploaded" / "photo.png")) == [PNG]

    async def test_data_url_for_images(self, policy: MediaInputPolicy) -> None:
        url = "data:image/png;base64," + base64.b64encode(PNG).decode()
        assert await _images(policy, url) == [PNG]

    async def test_video_from_path_and_loader(self, policy: MediaInputPolicy) -> None:
        videos = await resolve_media_inputs(["clip.mp4", "media://vid"], "video", policy, field_name="reference_videos")
        assert videos == [MP4, MP4]

    async def test_public_http_goes_through_secure_get(
        self, policy: MediaInputPolicy, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_secure_get(url: str, **_: object) -> httpx.Response:
            return httpx.Response(200, content=PNG, request=httpx.Request("GET", url))

        monkeypatch.setattr(media_inputs, "secure_get", fake_secure_get)
        assert await _images(policy, "https://example.com/a.png") == [PNG]

    @pytest.mark.parametrize("allow_private", [True, False])
    async def test_ssrf_shield_follows_the_policy(
        self, root: Path, monkeypatch: pytest.MonkeyPatch, allow_private: bool
    ) -> None:
        seen: list[object] = []

        async def fake_secure_get(url: str, **kwargs: object) -> httpx.Response:
            seen.append(kwargs["enable_ssrf_shield"])
            return httpx.Response(200, content=PNG, request=httpx.Request("GET", url))

        monkeypatch.setattr(media_inputs, "secure_get", fake_secure_get)
        local = MediaInputPolicy(allowed_roots=(root,), allow_private_networks=allow_private)
        assert await _images(local, "http://127.0.0.1:8000/a.png") == [PNG]
        assert seen == [not allow_private]

    async def test_image_hook_runs_once_per_image(self, root: Path) -> None:
        calls: list[bytes] = []

        def hook(data: bytes) -> bytes:
            calls.append(data)
            return b"\x89PNG\r\n\x1a\nclamped"

        hooked = MediaInputPolicy(allowed_roots=(root,), image_hook=hook)
        assert await _images(hooked, "_uploaded/photo.png") == [b"\x89PNG\r\n\x1a\nclamped"]
        assert calls == [PNG]

    async def test_image_hook_runs_off_the_event_loop_thread(self, root: Path) -> None:
        threads: list[int] = []

        def hook(data: bytes) -> bytes:
            threads.append(threading.get_ident())
            return data

        hooked = MediaInputPolicy(allowed_roots=(root,), image_hook=hook)
        await _images(hooked, "_uploaded/photo.png")

        assert threads
        assert threads[0] != threading.get_ident()


class TestRejected:
    async def test_path_outside_the_roots(self, policy: MediaInputPolicy, tmp_path: Path) -> None:
        outside = tmp_path / "outside.png"
        outside.write_bytes(PNG)
        with pytest.raises(MediaInputError, match="image_url: path is outside"):
            await _images(policy, str(outside))

    async def test_traversal_out_of_the_root(self, policy: MediaInputPolicy, tmp_path: Path) -> None:
        (tmp_path / "secret.png").write_bytes(PNG)
        with pytest.raises(MediaInputError, match="outside"):
            await _images(policy, "../secret.png")

    async def test_symlink_pointing_out_of_the_root(self, policy: MediaInputPolicy, root: Path, tmp_path: Path) -> None:
        target = tmp_path / "private.png"
        target.write_bytes(PNG)
        (root / "link.png").symlink_to(target)
        with pytest.raises(MediaInputError, match="outside"):
            await _images(policy, "link.png")

    async def test_env_file_inside_the_root_is_not_an_image(self, policy: MediaInputPolicy) -> None:
        with pytest.raises(MediaInputError, match="not a supported image"):
            await _images(policy, ".env")

    async def test_missing_file(self, policy: MediaInputPolicy) -> None:
        with pytest.raises(MediaInputError, match="file not found"):
            await _images(policy, "_uploaded/none.png")

    async def test_unknown_media_id(self, root: Path) -> None:
        strict = MediaInputPolicy(allowed_roots=(root,), loaders={"media": _loader({})})
        with pytest.raises(MediaInputError, match="not found"):
            await _images(strict, "media://missing")

    @pytest.mark.parametrize("ref", ["file:///etc/passwd", "ftp://host/a.png", "vault://x"])
    async def test_unsupported_schemes(self, policy: MediaInputPolicy, ref: str) -> None:
        with pytest.raises(MediaInputError, match="unsupported reference"):
            await _images(policy, ref)

    async def test_data_url_is_images_only(self, policy: MediaInputPolicy) -> None:
        url = "data:video/mp4;base64," + base64.b64encode(MP4).decode()
        with pytest.raises(MediaInputError, match="images only"):
            await resolve_media_inputs([url], "video", policy, field_name="reference_videos")

    async def test_non_base64_data_url(self, policy: MediaInputPolicy) -> None:
        with pytest.raises(MediaInputError, match="base64"):
            await _images(policy, "data:image/png,rawbytes")

    async def test_corrupt_base64(self, policy: MediaInputPolicy) -> None:
        with pytest.raises(MediaInputError, match="invalid base64"):
            await _images(policy, "data:image/png;base64,@@@@")

    async def test_image_is_not_a_video_and_vice_versa(self, policy: MediaInputPolicy) -> None:
        with pytest.raises(MediaInputError, match="not a supported video"):
            await resolve_media_inputs(["_uploaded/photo.png"], "video", policy, field_name="reference_videos")
        with pytest.raises(MediaInputError, match="not a supported image"):
            await _images(policy, "clip.mp4")

    async def test_oversized_path_is_refused_before_it_is_read(self, root: Path) -> None:
        tiny = MediaInputPolicy(allowed_roots=(root,), max_image_bytes=8)
        with pytest.raises(MediaInputError, match="larger than"):
            await _images(tiny, "_uploaded/photo.png")

    async def test_oversized_loader_result(self, root: Path) -> None:
        tiny = MediaInputPolicy(allowed_roots=(root,), loaders={"media": _loader({"abc": PNG})}, max_image_bytes=8)
        with pytest.raises(MediaInputError, match="larger than"):
            await _images(tiny, "media://abc")

    async def test_empty_reference(self, policy: MediaInputPolicy) -> None:
        with pytest.raises(MediaInputError, match="reference is empty"):
            await _images(policy, "  ")

    async def test_blocked_address(self, policy: MediaInputPolicy, monkeypatch: pytest.MonkeyPatch) -> None:
        async def blocked(url: str, **_: object) -> httpx.Response:
            raise SSRFSecurityError("private address")

        monkeypatch.setattr(media_inputs, "secure_get", blocked)
        with pytest.raises(MediaInputError, match="blocked by the network policy"):
            await _images(policy, "http://169.254.169.254/latest")

    async def test_oversized_download(self, policy: MediaInputPolicy, monkeypatch: pytest.MonkeyPatch) -> None:
        async def too_big(url: str, **_: object) -> httpx.Response:
            raise ContentTooLargeError

        monkeypatch.setattr(media_inputs, "secure_get", too_big)
        with pytest.raises(MediaInputError, match="larger than"):
            await _images(policy, "https://example.com/huge.png")

    async def test_http_error_status(self, policy: MediaInputPolicy, monkeypatch: pytest.MonkeyPatch) -> None:
        async def not_found(url: str, **_: object) -> httpx.Response:
            return httpx.Response(404, request=httpx.Request("GET", url))

        monkeypatch.setattr(media_inputs, "secure_get", not_found)
        with pytest.raises(MediaInputError, match="download failed"):
            await _images(policy, "https://example.com/gone.png")


class TestErrorNamesTheOffendingReference:
    async def test_one_bad_reference_among_several_is_indexed(self, policy: MediaInputPolicy) -> None:
        with pytest.raises(MediaInputError, match=r"reference_image_urls\[1\]: file not found"):
            await resolve_media_inputs(
                ["_uploaded/photo.png", "_uploaded/none.png"], "image", policy, field_name="reference_image_urls"
            )

    async def test_nothing_is_dropped_silently(self, policy: MediaInputPolicy) -> None:
        with pytest.raises(MediaInputError):
            await resolve_media_inputs(["media://abc", "media://zzz-missing"], "image", policy, field_name="refs")
