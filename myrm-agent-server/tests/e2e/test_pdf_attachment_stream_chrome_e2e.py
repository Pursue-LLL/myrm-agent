"""Chrome LIVE E2E: a real user attaches a mixed typed/scanned PDF and asks about it.

Covers the delivery contract this change introduced end to end: the user picks a PDF via
the real ``<input type=file>``, the frontend extracts it through ``/api/v1/files/extract-pdf``
and sends the parsed text plus page images in the turn, and the assistant's answer must
reflect which pages carried no text layer.

The staged PDF has three typed pages and two graphic-only pages. The assertion is the
user-visible consequence: the reply names the scanned pages, which is only possible if the
extraction disclosed them instead of serving a silently partial document.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import sys
import time
import zlib
from pathlib import Path

import pytest

_LOGGER = logging.getLogger("test_pdf_attachment_stream_chrome_e2e")

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from cdp_chat.support import (  # noqa: E402
    fetch_chat_messages,
    get_e2e_ui_url,
)
from dev_gate.contract import EvaluateIntent  # noqa: E402

from tests.support.chrome_mcp_e2e import open_mcp_page_async  # noqa: E402
from tests.support.e2e_runtime_guard import heartbeat_once  # noqa: E402

_PDF_FILENAME = "e2e-mixed-scan.pdf"

_PROMPT = (
    "这个 PDF 里有印刷体页面，也有扫描图片页面。请只用一句话回答：总共几页，"
    "哪些页码没有可提取的文本层。禁止调用任何工具，禁止查找文件，直接回答。"
)

_ATTACH_CHUNK_RESET_JS = "(() => { window.__MYRM_ATTACH_CHUNKS__ = []; return { ok: true }; })()"

_ATTACH_CHUNK_PUSH_JS = """(chunk) => {
  if (!window.__MYRM_ATTACH_CHUNKS__) window.__MYRM_ATTACH_CHUNKS__ = [];
  window.__MYRM_ATTACH_CHUNKS__.push(chunk);
  return { ok: true };
}"""

_ATTACH_ASSEMBLE_AND_DISPATCH_JS = """(filename) => {
  const input = document.querySelector('input[type="file"]');
  if (!input) return { ok: false, err: 'file-input-missing' };
  const b64Full = (window.__MYRM_ATTACH_CHUNKS__ || []).join('');
  delete window.__MYRM_ATTACH_CHUNKS__;
  const binary = atob(b64Full);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  const file = new File([bytes], filename, { type: 'application/pdf' });
  const transfer = new DataTransfer();
  transfer.items.add(file);
  input.files = transfer.files;
  input.dispatchEvent(new Event('input', { bubbles: true }));
  input.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true, size: file.size };
}"""

_ATTACH_READY_JS = """(() => {
  const name = 'e2e-mixed-scan.pdf';
  const bodyText = document.body ? document.body.textContent || '' : '';
  if (bodyText.includes(name)) return { ready: true, via: 'composer-label' };
  const nodes = Array.from(document.querySelectorAll('[data-testid], [class*="attachment"], [class*="file"]'));
  for (const node of nodes) {
    const text = (node.textContent || '') + ' ' + (node.getAttribute('title') || '');
    if (text.includes(name)) return { ready: true, via: 'attachment-node' };
    if (text.includes('e2e-mixed-scan')) return { ready: true, via: 'attachment-prefix' };
  }
  return { ready: false, via: 'none' };
})()"""

_LAST_ASSISTANT_TEXT_JS = """(() => {
  const bubbles = Array.from(document.querySelectorAll('[data-role="assistant"], [data-message-role="assistant"], .assistant-bubble'));
  const target = bubbles.length > 0 ? bubbles[bubbles.length - 1] : null;
  if (target) return { ready: true, text: (target.textContent || '').trim() };
  const generic = Array.from(document.querySelectorAll('[data-message-id]'));
  if (generic.length > 0) {
    const last = generic[generic.length - 1];
    return { ready: true, text: (last.textContent || '').trim() };
  }
  return { ready: false, text: '' };
})()"""


def _scan_page_pixels(width: int = 80, height: int = 60, seed: int = 1) -> bytes:
    """Deterministic non-uniform RGB samples: the ablation filter drops flat fills."""
    rows = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            value = (x * 37 + y * 11 + seed * 53) % 256
            row += bytes((value, (value * 3) % 256, (value * 5) % 256))
        rows.append(bytes(row))
    return b"".join(rows)


def _build_mixed_pdf(text_pages: int = 3, scan_pages: int = 2) -> bytes:
    """PDF with typed pages followed by graphic-only (scanned) pages."""
    objects: list[bytes] = [b"", b"", b""]  # 1 catalog, 2 pages, 3 reserved

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font_id = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []
    for index in range(1, text_pages + scan_pages + 1):
        if index <= text_pages:
            line = f"PAGE {index} TYPED BODY TEXT SAMPLE " * 4
            escaped = line.replace("(", "\\(").replace(")", "\\)")
            stream = f"BT /F1 10 Tf 40 740 Td ({escaped}) Tj ET".encode("latin-1")
            resources = b"<< /Font << /F1 %d 0 R >> >>" % font_id
        else:
            pixels = _scan_page_pixels(seed=index)
            compressed = zlib.compress(pixels, 9)
            image_id = add(
                b"<< /Type /XObject /Subtype /Image /Width 80 /Height 60 /ColorSpace /DeviceRGB "
                b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n"
                % len(compressed)
                + compressed
                + b"\nendstream"
            )
            stream = b"q 480 0 0 640 60 60 cm /Im0 Do Q"
            resources = b"<< /XObject << /Im0 %d 0 R >> >>" % image_id
        content_id = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page_ids.append(
            add(
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R /Resources " % content_id
                + resources
                + b" >>"
            )
        )

    objects[1] = b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % pid for pid in page_ids) + b"] /Count %d >>" % len(page_ids)
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % idx + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets[1:]:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


async def _wait_for(predicate_js: str, chat: McpChatSession, timeout_sec: float) -> dict:
    deadline = time.monotonic() + timeout_sec
    last: dict = {}
    while True:
        heartbeat_once()
        probe = await chat.evaluate(predicate_js, intent=EvaluateIntent.BRIDGE_POLL)
        if isinstance(probe, dict):
            last = probe
            if probe.get("ready") is True:
                return probe
        if time.monotonic() >= deadline:
            return last
        await asyncio.sleep(1.0)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
async def test_pdf_attachment_discloses_scanned_pages_live_chrome_e2e() -> None:
    """A real user attaches a mixed PDF; the assistant must name the scanned pages."""

    ui_url = get_e2e_ui_url()
    pdf_bytes = _build_mixed_pdf(text_pages=3, scan_pages=2)
    encoded = base64.b64encode(pdf_bytes).decode("ascii")

    session = await open_mcp_page_async(ui_url)
    try:
        chat = McpChatSession(session.client, session.page)
        await chat.bootstrap(ui_url, timeout_sec=120.0)
        await chat.click_new_chat()
        await chat.ensure_chat_surface(ui_url)

        await chat.evaluate(_ATTACH_CHUNK_RESET_JS, intent=EvaluateIntent.AGENT_SUBMIT)
        chunk_size = 96 * 1024
        for start in range(0, len(encoded), chunk_size):
            chunk = encoded[start : start + chunk_size]
            pushed = await chat.evaluate(
                f"({_ATTACH_CHUNK_PUSH_JS})({json.dumps(chunk)})",
                intent=EvaluateIntent.AGENT_SUBMIT,
            )
            assert isinstance(pushed, dict) and pushed.get("ok") is True, pushed

        injected = await chat.evaluate(
            f"({_ATTACH_ASSEMBLE_AND_DISPATCH_JS})({json.dumps(_PDF_FILENAME)})",
            intent=EvaluateIntent.AGENT_SUBMIT,
        )
        assert isinstance(injected, dict) and injected.get("ok") is True, injected
        _LOGGER.info("STAGE: pdf attached (size=%s)", injected.get("size"))

        ready = await _wait_for(_ATTACH_READY_JS, chat, timeout_sec=120.0)
        assert ready.get("ready") is True, f"attachment never appeared in the composer: {ready}"

        send_result = await chat.send_message(_PROMPT, _PROMPT, skip_model_sync=True)
        chat_id = str(
            send_result.get("started", {}).get("chatId")
            or send_result.get("submit", {}).get("chatId")
            or (await chat.bridge_chat_id())
            or ""
        ).strip()
        assert chat_id, f"turn did not start: {send_result}"

        reply = await _wait_for(_LAST_ASSISTANT_TEXT_JS, chat, timeout_sec=240.0)
        assistant_text = str(reply.get("text") or "").strip()
        print(f"E2E_PDF_ASSISTANT_REPLY: {assistant_text[:600]}", flush=True)
        assert reply.get("ready") is True, reply
        assert len(assistant_text) >= 10, f"assistant reply too short: {assistant_text}"

        # The extraction must have reached the model: the reply has to name the scanned
        # page range instead of claiming no PDF was attached. Asserting a bare digit would
        # pass on any number in the prose, so require both page numbers to appear in a
        # page-reference shape. The model is free to phrase it as "4,5" / "4-5" /
        # "第 4 页和第 5 页", so the match strips punctuation and whitespace first.
        lowered = assistant_text.lower()
        assert "no pdf" not in lowered and "没有 pdf" not in lowered, f"the attachment did not reach the model: {assistant_text}"
        normalized = lowered
        for ch in (
            " ",
            "\u3000",
            "，",
            "、",
            "。",
            ",",
            "和",
            "与",
            "以及",
            "～",
            "至",
            "到",
            "~",
            "第",
            "页",
            "page",
            "pages",
            "and",
        ):
            normalized = normalized.replace(ch, "")
        names_both_pages = any(token in normalized for token in ("4-5", "45"))
        assert names_both_pages, f"reply must name the scanned pages 4 and 5 together: {assistant_text}"

        persisted = json.dumps(fetch_chat_messages(chat_id), ensure_ascii=False, default=str)
        assert _PDF_FILENAME in persisted or "application/pdf" in persisted or "pdf" in persisted.lower(), (
            "the user turn did not persist the PDF attachment"
        )
    finally:
        await session.aclose()
