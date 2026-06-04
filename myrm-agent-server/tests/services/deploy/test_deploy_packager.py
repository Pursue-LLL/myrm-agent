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


def test_collect_single_html_includes_sibling_css(tmp_path: Path) -> None:
    html_path = tmp_path / "index.html"
    html_path.write_text(
        '<html><head><link rel="stylesheet" href="style.css"></head><body>Hi</body></html>',
        encoding="utf-8",
    )
    (tmp_path / "style.css").write_text("body { color: red; }", encoding="utf-8")

    vault_html = tmp_path / "vault" / "page.html"
    vault_html.parent.mkdir(parents=True)
    vault_html.write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")

    files = collect_deploy_files(vault_html, asset_root=tmp_path, entry_name_hint="index.html")

    assert "index.html" in files
    assert "style.css" in files
    assert "color: red" in files["style.css"].content


def test_collect_directory_with_unresolved_root(tmp_path: Path) -> None:
    """macOS /var vs /private/var: obj_path may differ from rglob resolved paths."""
    resolved = tmp_path.resolve()
    (resolved / "index.html").write_text("<h1>Hi</h1>", encoding="utf-8")
    (resolved / "style.css").write_text("body{}", encoding="utf-8")

    files = collect_deploy_files(tmp_path)

    assert "index.html" in files
    assert "style.css" in files


def test_collect_directory_skips_node_modules(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>Hi</h1>", encoding="utf-8")
    node_modules = tmp_path / "node_modules" / "pkg"
    node_modules.mkdir(parents=True)
    (node_modules / "secret.js").write_text("bad()", encoding="utf-8")

    files = collect_deploy_files(tmp_path)

    assert "index.html" in files
    assert "secret.js" not in files
