"""A local stand-in for the user's hosting webhook: it records what each publication uploads and answers with a page address.

[INPUT]
- The multipart body the http_webhook provider posts (POS: the form fields and one zip holding the files of the publication)

[OUTPUT]
- Upload: the form fields and the text of every file of one publication
- WebhookReceiver: a loopback HTTP server on a free port; ``url`` is where to point a target, ``uploads`` lists what arrived

[POS]
Server pytest-only. The real-model hosting tests (tests/api/agent/test_artifact_publish_by_path_e2e.py) use it in place of the platform the
user publishes to; the page address it returns is derived from the artifact id, so publishing one artifact again answers with the same address.
"""

from __future__ import annotations

import io
import json
import threading
import zipfile
from dataclasses import dataclass
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import default as default_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from typing import cast

PAGE_HOST = "https://sites.example.test"


@dataclass(frozen=True)
class Upload:
    fields: dict[str, str]
    files: dict[str, str]


class _Server(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.uploads: list[Upload] = []


def _parse_upload(content_type: str, body: bytes) -> Upload:
    message = BytesParser(policy=default_policy).parsebytes(b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + body)
    assert isinstance(message, EmailMessage)
    fields: dict[str, str] = {}
    files: dict[str, str] = {}
    for part in message.iter_parts():
        name = str(part.get_param("name", header="content-disposition"))
        raw = part.get_payload(decode=True)
        payload = raw if isinstance(raw, bytes) else b""
        if name != "artifact":
            fields[name] = payload.decode("utf-8", "replace")
            continue
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            files = {entry: archive.read(entry).decode("utf-8", "replace") for entry in archive.namelist()}
    return Upload(fields, files)


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802  (the name http.server dispatches on)
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        upload = _parse_upload(self.headers["Content-Type"], body)
        server = cast(_Server, self.server)
        server.uploads.append(upload)
        answer = json.dumps(
            {"url": f"{PAGE_HOST}/{upload.fields['artifact_id']}", "publication_id": f"pub-{len(server.uploads)}"}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(answer)))
        self.end_headers()
        self.wfile.write(answer)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002  (signature of the base class)
        return


class WebhookReceiver:
    def __init__(self) -> None:
        self._server = _Server()
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/hook"

    @property
    def uploads(self) -> list[Upload]:
        return self._server.uploads

    def __enter__(self) -> WebhookReceiver:
        self._thread.start()
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
