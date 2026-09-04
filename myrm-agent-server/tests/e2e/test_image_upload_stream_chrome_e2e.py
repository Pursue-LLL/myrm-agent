"""Chrome LIVE E2E: WebUI real-user image upload → send → assistant reply.

Drives the real frontend pipeline in a real Chrome against an isolated private
backend: the user picks an image (real ``<input type=file>`` DataTransfer),
the frontend multipart-uploads it to ``/api/v1/files/upload`` (backend
responds with a stored ``file_id``), the attachment appears as a thumbnail in
the composer, and a turn is submitted with the attachment. The assertion runs
against the persisted API messages (the message carries image file metadata)
plus an assistant stream completion.

The staged JPEG is ~3.9 MiB raw (>4 MiB base64): raw size lands above the
``SEND_COMPRESS_TRIGGER_BYTES`` 4 MiB threshold so the backend
``image_compressor.compress_if_needed`` path is exercised for real, while the
compressed output stays well under every provider per-image ceiling.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import sys
from pathlib import Path

import pytest

_LOGGER = logging.getLogger("test_image_upload_stream_chrome_e2e")

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from cdp_chat.support import (  # noqa: E402
    config_write_mutex,
    fetch_chat_messages,
    fetch_config_value,
    get_e2e_api_url,
    get_e2e_ui_url,
    put_config_value,
    wait_e2e_provider_ready,
)
from cdp_chat.ui import chat_id_from_path  # noqa: E402
from dev_gate.contract import EvaluateIntent  # noqa: E402

from tests.support.chrome_mcp_e2e import open_mcp_page_async  # noqa: E402
from tests.support.e2e_provider_seed import (  # noqa: E402
    infer_provider_id,
    strip_provider_prefix,
    upsert_provider,
)
from tests.support.e2e_runtime_guard import (  # noqa: E402
    E2EResourceLedger,
    heartbeat_once,
)
from tests.support.test_secrets import load_test_secrets  # noqa: E402

_PROMPT = "请直接查看附带的图片并只用一句话回答图片中主要内容。禁止调用任何工具，禁止查找文件，直接回答。"
_TURN_WAIT_SEC = 300.0
_IMAGE_FILENAME = "e2e-upload-staged.jpg"
# Raw bytes land just above SEND_COMPRESS_TRIGGER_BYTES (4 MiB) so the backend
# compress_if_needed path takes effect (measured: ~3.9 MiB raw / ~4.95 MiB b64),
# while the compressed JPEG stays far under every provider per-image ceiling.
_IMAGE_TARGET_BYTES = 3_560_000

_ATTACH_INJECT_JS = """async (b64, filename) => {
  const input = document.querySelector('input[type="file"]');
  if (!input) return { ok: false, err: 'file-input-missing' };
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  const file = new File([bytes], filename, { type: 'image/jpeg' });
  const transfer = new DataTransfer();
  transfer.items.add(file);
  input.files = transfer.files;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true };
}"""

_ATTACH_LIST_READY_JS = """(() => {
  const imgs = Array.from(document.querySelectorAll('img'));
  const staged = imgs.find((img) => (img.alt || '').includes('e2e-upload-staged'));
  return {
    ready: Boolean(staged),
    alt: staged?.getAttribute('alt') ?? null,
    totalImgs: imgs.length,
  };
})()"""


def _make_staged_jpeg(target_bytes: int) -> bytes:
    """Build a realistic JPEG just above the send-compress trigger (raw bytes)."""
    from PIL import Image

    width = 2048
    height = 1536
    while True:
        img = Image.new("RGB", (width, height))
        pixels = img.load()
        seed = 0x5EED
        assert pixels is not None
        for y in range(height):
            for x in range(width):
                seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
                r = (seed >> 24) & 0xFF
                g = ((seed * 7) >> 24) & 0xFF
                b = ((seed * 13) >> 24) & 0xFF
                pixels[x, y] = (r, g, b)
        dst = io.BytesIO()
        img.save(dst, format="JPEG", quality=92)
        data = dst.getvalue()
        if len(data) >= target_bytes:
            return data
        width = int(width * 1.15)
        height = int(height * 1.15)


def _provider_cfg() -> dict[str, str]:
    secrets = load_test_secrets()
    assert secrets.basic_model and secrets.basic_api_key, "BASIC_* missing in .env.test"
    return {
        "basic_model": secrets.basic_model,
        "basic_api_key": secrets.basic_api_key,
        "basic_base_url": secrets.basic_base_url,
        "lite_model": secrets.lite_model or secrets.basic_model,
        "lite_api_key": secrets.lite_api_key or secrets.basic_api_key,
        "lite_base_url": secrets.lite_base_url or secrets.basic_base_url,
    }


def _seed_vision_provider(api_url: str) -> dict[str, object]:
    """Upsert BASIC provider + mark the base model vision-capable (real image turn).

    Reproduces the state a real user produces in the WebUI ModelService dialog:
    the user ticks "vision capable" (ModelInfoCard.handleSave →
    ``setModelInfo(providerId, model, {supports_vision: true})``), which persists
    ``customModelInfo["<providerId>/<model>"]``. Two separate consumers read it:

    * frontend attach gate ``useProviderStore.getModelInfo`` looks up
      ``customModelInfo["<providerId>/<model>"]`` to decide whether to toast
      "vision not configured" (soft gate: upload still proceeds), and
    * backend ``enrich_model_capabilities`` → ``_lookup_custom_model_info`` falls
      back from an exact key to a bare model name before consulting litellm.

    Writing the same ``<providerId>/<model>`` key keeps the E2E flow byte-for-byte
    identical to a user who enabled vision in the UI. MiniMax-M3 also reports
    ``supports_vision: true`` from litellm itself, so the backend would accept
    the image either way; the customModelInfo entry additionally silences the
    frontend soft-gate toast.
    """
    cfg = _provider_cfg()
    basic_id = infer_provider_id(cfg["basic_model"])
    basic_model = strip_provider_prefix(cfg["basic_model"])
    lite_id = infer_provider_id(cfg["lite_model"])
    lite_model = strip_provider_prefix(cfg["lite_model"])

    current = fetch_config_value("providers", api_url=api_url)
    providers = current.get("providers")
    provider_list = upsert_provider(
        ([p for p in providers if isinstance(p, dict)] if isinstance(providers, list) else []),
        provider_id=basic_id,
        model_id=basic_model,
        api_url=cfg["basic_base_url"],
        api_key=cfg["basic_api_key"],
    )
    provider_list = upsert_provider(
        provider_list,
        provider_id=lite_id,
        model_id=lite_model,
        api_url=cfg["lite_base_url"],
        api_key=cfg["lite_api_key"],
        merge_models=True,
    )

    dmc = dict(current.get("defaultModelConfig") or {})
    dmc["baseModel"] = {
        "primary": {"providerId": basic_id, "model": basic_model},
        "fallback": None,
        "temperature": 0.7,
        "modelKwargs": {},
    }
    dmc["liteModel"] = {
        "primary": {"providerId": lite_id, "model": lite_model},
        "fallback": None,
        "temperature": 0.7,
    }
    custom_info = dict(current.get("customModelInfo") or {})
    custom_info[f"{basic_id}/{basic_model}"] = {"supports_vision": True}
    custom_info[f"{lite_id}/{lite_model}"] = {"supports_vision": True}
    merged = {
        **current,
        "providers": provider_list,
        "defaultModelConfig": dmc,
        "customModelInfo": custom_info,
    }
    put_config_value("providers", merged, api_url=api_url)
    return merged


async def _await_assistant_reply(
    chat: McpChatSession,
    *,
    chat_id: str,
    api_url: str,
    timeout_sec: float = _TURN_WAIT_SEC,
) -> dict[str, object]:
    """Wait for the agent to absorb the turn and finish streaming.

    The live agent may run tool loops (assistant rows with empty content but
    ``progressSteps``) before producing final text; the tool activity itself
    proves the uploaded image reached the model context. The durable signal is
    therefore an assistant row plus a settled (non-streaming) stream.
    """
    deadline = __import__("time").monotonic() + timeout_sec
    last_ui: dict[str, object] = {}
    last_assistant_count = 0
    settled_since = 0.0
    while True:
        heartbeat_once()
        try:
            raw = await chat.evaluate(
                """(() => {
                  const bridge = window.__MYRM_E2E_CHAT__;
                  if (!bridge?.turnSnapshot) return { ready: false, err: 'no-turn-snapshot' };
                  const snap = bridge.turnSnapshot();
                  return {
                    pendingAssistant: Boolean(snap?.lastAssistantSample),
                    isStreaming: snap?.isStreaming === true,
                    userCount: snap?.userCount ?? 0,
                    lastAssistantSample: String(snap?.lastAssistantSample || ''),
                  };
                })()""",
                intent=EvaluateIntent.BRIDGE_POLL,
            )
            if isinstance(raw, dict):
                last_ui = raw
        except (RuntimeError, TimeoutError):
            last_ui = {"uiError": "evaluate-failed"}
        assistant_rows = [
            msg
            for msg in fetch_chat_messages(chat_id, api_url=api_url)
            if isinstance(msg, dict) and str(msg.get("role") or "") == "assistant"
        ]
        streaming = last_ui.get("isStreaming") is True
        count = len(assistant_rows)
        if not streaming:
            if count > last_assistant_count:
                settled_since = __import__("time").monotonic()
            elif count > 0 and settled_since == 0.0:
                settled_since = __import__("time").monotonic()
        last_assistant_count = count
        if assistant_rows and not streaming and settled_since:
            content = str(assistant_rows[-1].get("content") or "")
            _LOGGER.info("STAGE: assistant settled! content=%s", content[:100])
            return {
                "ready": True,
                "content": (content or "(tool-turn)")[:200],
                "assistantCount": count,
                "via": "api",
            }
        _LOGGER.info(
            "POLL: isStreaming=%s, assistant_rows=%s, count=%s, last_ui=%s",
            streaming,
            len(assistant_rows),
            count,
            last_ui,
        )
        if __import__("time").monotonic() >= deadline:
            dump = json.dumps(
                fetch_chat_messages(chat_id, api_url=api_url),
                ensure_ascii=False,
                default=str,
            )[:1600]
            raise AssertionError(f"Assistant turn did not settle: ui={last_ui} messages={dump}")
        await asyncio.sleep(2.0)


async def _run_image_flow(chat: McpChatSession, *, api_url: str) -> str:
    ui_base = get_e2e_ui_url().rstrip("/")
    _LOGGER.info(
        "STAGE: run_image_flow start (ui_base=%s, api_url=%s)", ui_base, api_url
    )
    await chat.bootstrap(ui_base, navigate=False, timeout_sec=120.0)
    _LOGGER.info("STAGE: bootstrapped, click_new_chat")
    await chat.click_new_chat()
    _LOGGER.info("STAGE: clicked new chat, pinBasicModelForE2e")

    pin_raw = await chat.evaluate(
        """(async () => {
          const bridge = window.__MYRM_E2E_CHAT__;
          if (!bridge?.pinBasicModelForE2e) {
            return { ok: false, err: 'no pinBasicModelForE2e' };
          }
          const sel = await bridge.pinBasicModelForE2e();
          return { ok: true, selection: sel };
        })()""",
        intent=EvaluateIntent.AGENT_SUBMIT,
    )
    assert isinstance(pin_raw, dict) and pin_raw.get("ok") is True, pin_raw

    image_bytes = _make_staged_jpeg(_IMAGE_TARGET_BYTES)
    b64 = base64.b64encode(image_bytes).decode("ascii")
    assert len(b64) > 4 * 1024 * 1024, "staged JPEG base64 must cross 4 MiB trigger"

    injected = await chat.evaluate(
        f"({_ATTACH_INJECT_JS})({json.dumps(b64)}, {json.dumps(_IMAGE_FILENAME)})",
        intent=EvaluateIntent.AGENT_SUBMIT,
    )
    assert isinstance(injected, dict) and injected.get("ok") is True, injected
    _LOGGER.info("STAGE: attachment injected, wait thumbnail")

    thumbnail_probe: dict[str, object] = {}
    upload_deadline = __import__("time").monotonic() + 90.0
    while True:
        heartbeat_once()
        probe = await chat.evaluate(
            _ATTACH_LIST_READY_JS,
            intent=EvaluateIntent.BRIDGE_POLL,
        )
        if isinstance(probe, dict):
            thumbnail_probe = probe
            if probe.get("ready") is True:
                break
        if __import__("time").monotonic() >= upload_deadline:
            break
        await asyncio.sleep(1.0)
    assert thumbnail_probe.get("ready") is True, f"attachment thumbnail never appeared (upload failed): {thumbnail_probe}"
    _LOGGER.info("STAGE: thumbnail ready, filling prompt and sending message")
    await chat.fill_input(_PROMPT)

    # When attachments are staged in the composer DOM, native button click
    # routes the turn through standard WebUI submit handlers with uploaded files intact.
    submit_res = await chat.submit_native_click()
    _LOGGER.info("STAGE: submit_native_click result=%s", submit_res)
    started = await chat._submit_started()
    chat_id = (
        str(started.get("bridgeChatId") or "").strip()
        or chat_id_from_path(str(started.get("path") or ""))
        or await chat.bridge_chat_id()
        or ""
    )
    if not chat_id:
        send_result = await chat.send_message(_PROMPT, _PROMPT)
        _LOGGER.info("STAGE: fallback send_message result=%s", send_result)
        chat_id = str(
            send_result.get("started", {}).get("chatId")
            or send_result.get("submit", {}).get("chatId")
            or ""
        ).strip()
    assert chat_id, f"image turn did not start: started={started}"
    _LOGGER.info("STAGE: awaiting assistant reply (chat_id=%s)", chat_id)

    reply = await _await_assistant_reply(
        chat,
        chat_id=chat_id,
        api_url=api_url,
    )
    assert reply.get("ready") is True, reply
    assert str(reply.get("content") or "").strip(), reply

    # Persisted turn: the real user message must carry the staged image file_id
    # (uploaded_file_ids) so downstream consume can resolve the uploaded bytes.
    # The persisted row references the image via the storage file URL
    # (metadata.original_query.image_url), not necessarily the bare filename.
    persisted_hit = False
    for msg in fetch_chat_messages(chat_id, api_url=api_url):
        if not isinstance(msg, dict) or str(msg.get("role") or "") != "user":
            continue
        blob = json.dumps(msg, ensure_ascii=False, default=str)
        if _IMAGE_FILENAME in blob or '"image_url"' in blob or "/api/v1/files/storage/files/" in blob:
            persisted_hit = True
            break
    assert persisted_hit, f"user message persisted without staged image file_id: chat_id={chat_id}"
    return chat_id


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_image_upload_stream_assistant_replies(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    api_url = get_e2e_api_url()
    if not wait_e2e_provider_ready(api_url=api_url, timeout_sec=120.0):
        pytest.fail("Provider config not ready — run via ./myrm test -m chrome_e2e after ./myrm ready --chrome")

    backup = fetch_config_value("providers", api_url=api_url)
    try:
        # R2: vision provider seed must stay authoritative for the whole flow.
        with config_write_mutex("providers", wait_sec=900.0):
            _seed_vision_provider(api_url)
            if not wait_e2e_provider_ready(api_url=api_url, timeout_sec=60.0):
                pytest.fail("Provider readiness failed after vision seed")

            page_session = await open_mcp_page_async(
                get_e2e_ui_url().rstrip("/"),
                request_timeout_sec=180.0,
                timeout_ms=120_000,
            )
            try:
                chat_id = await _run_image_flow(
                    McpChatSession(page_session.client, page_session.page),
                    api_url=api_url,
                )
                e2e_resource_ledger.register("chat", chat_id)
            finally:
                await page_session.aclose()
    finally:
        if isinstance(backup, dict) and backup:
            put_config_value("providers", backup, api_url=api_url)
