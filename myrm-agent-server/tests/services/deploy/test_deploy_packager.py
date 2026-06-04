import base64
from pathlib import Path

import pytest

from app.services.deploy.deploy_packager import DeployFile, collect_deploy_files, validate_deploy_payload


def test_collect_single_html_file(tmp_path: Path):
    html_path = tmp_path / "page.html"
    html_path.write_text("<h1>Hello</h1>", encoding="utf-8")

    files = collect_deploy_files(html_path)

    assert "index.html" in files
    assert files["index.html"].encoding == "utf-8"
    assert files["index.html"].content == "<h1>Hello</h1>"


def test_collect_directory_with_binary(tmp_path: Path):
    (tmp_path / "index.html").write_text("<img src='logo.png' />", encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n")

    files = collect_deploy_files(tmp_path)

    assert files["index.html"].encoding == "utf-8"
    assert files["logo.png"].encoding == "base64"
    assert base64.b64decode(files["logo.png"].content).startswith(b"\x89PNG")


def test_validate_deploy_payload_requires_html_entry() -> None:
    with pytest.raises(ValueError, match="No files"):
        validate_deploy_payload({})

    validate_deploy_payload(
        {"index.html": DeployFile(path="index.html", content="<h1>Hi</h1>")}
    )

    with pytest.raises(ValueError, match="index.html"):
        validate_deploy_payload(
            {"style.css": DeployFile(path="style.css", content="body{}")}
        )
