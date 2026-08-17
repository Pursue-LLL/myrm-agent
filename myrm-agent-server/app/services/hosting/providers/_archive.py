"""Shared archive utilities for hosting providers.

[INPUT]
- app.services.hosting.packager::PublishFile (POS: 可部署文件的统一数据结构)

[OUTPUT]
- build_provider_zip: build a ZIP archive from deployable publish files

[POS]
Hosting provider 层共享归档工具，供 http_webhook / cloudflare / netlify 复用。
"""

from __future__ import annotations

import base64
import io
import zipfile

from app.services.hosting.packager import PublishFile


def build_provider_zip(files: dict[str, PublishFile]) -> bytes:
    """Build a ZIP archive containing every deployable publish file."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, publish_file in files.items():
            content = (
                base64.b64decode(publish_file.content)
                if publish_file.encoding == "base64"
                else publish_file.content
            )
            archive.writestr(path, content)
    return buffer.getvalue()
