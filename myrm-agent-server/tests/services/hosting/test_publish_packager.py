import base64
from pathlib import Path

import pytest

from app.services.hosting.packager import PublishFile, collect_publish_files, validate_publish_payload


def _discovery_files(
    tmp_path: Path,
    sandbox_html: str,
    sandbox_files: dict[str, str | bytes] | None = None,
) -> dict[str, PublishFile]:
    """Collect via the vault-object + sandbox path so HTML reference discovery
    (``_merge_disk_assets`` / ``_discover_dependency_files``) actually runs.

    The directory-scan path (``collect_publish_files(dir)``) gathers every
    allowed static file via rglob and never resolves references, so it cannot
    exercise discovery.
    """
    vault_obj = tmp_path / "obj" / "abc"
    vault_obj.parent.mkdir()
    vault_obj.write_text("<h1>vault</h1>", encoding="utf-8")
    asset_root = tmp_path / "sandbox"
    asset_root.mkdir()
    (asset_root / "index.html").write_text(sandbox_html, encoding="utf-8")
    for name, content in (sandbox_files or {}).items():
        target = asset_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    return collect_publish_files(vault_obj, asset_root=asset_root, entry_name_hint="index.html")


def test_collect_single_html_file(tmp_path: Path):
    html_path = tmp_path / "page.html"
    html_path.write_text("<h1>Hello</h1>", encoding="utf-8")

    files = collect_publish_files(html_path)

    assert "index.html" in files
    assert files["index.html"].encoding == "utf-8"
    assert files["index.html"].content == "<h1>Hello</h1>"


def test_collect_directory_with_binary(tmp_path: Path):
    (tmp_path / "index.html").write_text("<img src='logo.png' />", encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n")

    files = collect_publish_files(tmp_path)

    assert files["index.html"].encoding == "utf-8"
    assert files["logo.png"].encoding == "base64"
    assert base64.b64decode(files["logo.png"].content).startswith(b"\x89PNG")


def test_validate_publish_payload_requires_html_entry() -> None:
    with pytest.raises(ValueError, match="No files"):
        validate_publish_payload({})

    validate_publish_payload({"index.html": PublishFile(path="index.html", content="<h1>Hi</h1>")})

    with pytest.raises(ValueError, match="index.html"):
        validate_publish_payload({"style.css": PublishFile(path="style.css", content="body{}")})


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

    files = collect_publish_files(vault_html, asset_root=tmp_path, entry_name_hint="index.html")

    assert "index.html" in files
    assert "style.css" in files
    assert "color: red" in files["style.css"].content


def test_collect_extensionless_vault_html_uses_artifact_name(tmp_path: Path) -> None:
    """Vault objects are extension-less UUID files; the artifact name must win."""
    vault_obj = tmp_path / "obj" / "9f2c"  # extension-less physical object
    vault_obj.parent.mkdir(parents=True)
    vault_obj.write_text("<h1>Hi</h1>", encoding="utf-8")

    files = collect_publish_files(vault_obj, entry_name_hint="index.html")

    assert list(files) == ["index.html"]
    assert files["index.html"].encoding == "utf-8"
    assert files["index.html"].content == "<h1>Hi</h1>"


def test_collect_extensionless_vault_pdf_uses_artifact_name(tmp_path: Path) -> None:
    vault_obj = tmp_path / "obj" / "7b1e"
    vault_obj.parent.mkdir(parents=True)
    vault_obj.write_bytes(b"%PDF-1.4\n%%EOF")

    files = collect_publish_files(vault_obj, entry_name_hint="report.pdf")

    assert list(files) == ["report.pdf"]
    assert files["report.pdf"].encoding == "base64"
    assert base64.b64decode(files["report.pdf"].content).startswith(b"%PDF")


def test_collect_directory_with_unresolved_root(tmp_path: Path) -> None:
    """macOS /var vs /private/var: obj_path may differ from rglob resolved paths."""
    resolved = tmp_path.resolve()
    (resolved / "index.html").write_text("<h1>Hi</h1>", encoding="utf-8")
    (resolved / "style.css").write_text("body{}", encoding="utf-8")

    files = collect_publish_files(tmp_path)

    assert "index.html" in files
    assert "style.css" in files


def test_collect_directory_skips_node_modules(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>Hi</h1>", encoding="utf-8")
    node_modules = tmp_path / "node_modules" / "pkg"
    node_modules.mkdir(parents=True)
    (node_modules / "secret.js").write_text("bad()", encoding="utf-8")

    files = collect_publish_files(tmp_path)

    assert "index.html" in files
    assert "secret.js" not in files


def test_collect_publish_files_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        collect_publish_files(tmp_path / "missing.html")


def test_collect_single_file_too_large(tmp_path: Path) -> None:
    from app.services.hosting.packager import MAX_SINGLE_FILE_BYTES

    big = tmp_path / "big.html"
    big.write_bytes(b"x" * (MAX_SINGLE_FILE_BYTES + 1))
    with pytest.raises(ValueError, match="too large for deploy"):
        collect_publish_files(big)


def test_collect_total_payload_too_large(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.hosting.packager.MAX_TOTAL_BYTES", 100)
    dir_path = tmp_path / "bundle"
    dir_path.mkdir()
    (dir_path / "a.html").write_text("a" * 60, encoding="utf-8")
    (dir_path / "b.html").write_text("b" * 60, encoding="utf-8")
    with pytest.raises(ValueError, match="exceeds limit"):
        collect_publish_files(dir_path)


def test_collect_publish_files_empty_directory(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(ValueError, match="no deployable files"):
        collect_publish_files(empty_dir)


def test_collect_html_with_js_import(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        '<html><script src="app.js"></script></html>',
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text("console.log('ok')", encoding="utf-8")
    files = collect_publish_files(tmp_path)
    assert "index.html" in files
    assert "app.js" in files


def test_collect_skips_remote_and_data_references(tmp_path: Path) -> None:
    files = _discovery_files(
        tmp_path,
        '<img src="https://cdn.example.com/x.png" />'
        '<img src="data:image/png;base64,AAA" />'
        '<script src="//cdn.example.com/y.js"></script>'
        '<a href="#anchor"></a>',
    )
    assert list(files) == ["index.html"]


def test_collect_blocks_path_traversal_reference(tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    files = _discovery_files(tmp_path, '<img src="../secret.txt">')
    assert "secret.txt" not in files
    assert list(files) == ["index.html"]


def test_collect_discovers_css_imports_and_inline_urls(tmp_path: Path) -> None:
    html = (
        '<html><head><style>@import url("theme.css");'
        'body{background:url("bg.png")}</style></head>'
        "<body><div style=\"background-image:url('inline.png')\"></div></body></html>"
    )
    files = _discovery_files(
        tmp_path,
        html,
        {
            "theme.css": "body{}",
            "bg.png": b"\x89PNG\r\n",
            "inline.png": b"\x89PNG\r\n",
            "decoy.txt": "not referenced",
        },
    )
    assert "theme.css" in files
    assert "bg.png" in files
    assert "inline.png" in files
    # Discovery collects only the reference chain, never unreferenced files.
    assert "decoy.txt" not in files


def test_collect_discovers_js_esm_and_dynamic_imports(tmp_path: Path) -> None:
    files = _discovery_files(
        tmp_path,
        '<script type="module" src="main.js"></script><script src="main.js"></script>',
        {
            "main.js": ('import helper from "./helper.js";\nimport("./chunk.js");\nexport {x} from "./reexport.js";'),
            "helper.js": "export{}",
            "chunk.js": "console.log(1)",
            "reexport.js": "export{}",
            "decoy.js": "console.log('nope')",
        },
    )
    # Duplicate main.js reference exercises the BFS visited-set skip.
    assert {"main.js", "helper.js", "chunk.js", "reexport.js"} <= set(files)
    assert "decoy.js" not in files


def test_collect_non_utf8_html_falls_back_to_base64(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_bytes(b"\xff\xfe\x00\x80 bad")
    files = collect_publish_files(tmp_path)
    assert files["index.html"].encoding == "base64"
    assert base64.b64decode(files["index.html"].content).startswith(b"\xff\xfe")


def test_collect_blocks_excluded_file_and_node_modules_ref(tmp_path: Path) -> None:
    files = _discovery_files(
        tmp_path,
        '<script src="node_modules/pkg/x.js"></script><link rel="stylesheet" href="package-lock.json">',
        {
            "node_modules/pkg/x.js": "bad()",
            "package-lock.json": "{}",
        },
    )
    assert "node_modules/pkg/x.js" not in files
    assert "package-lock.json" not in files


def test_collect_skips_directory_referenced_like_html(tmp_path: Path) -> None:
    """A reference resolving to a directory (not a file) is skipped by discovery."""
    files = _discovery_files(
        tmp_path,
        '<img src="assets.html">',
        {"assets.html/hidden.png": b"\x89PNG\r\n"},
    )
    assert "assets.html/hidden.png" not in files
    assert list(files) == ["index.html"]


def test_collect_tolerates_unreadable_scannable_file(tmp_path: Path) -> None:
    files = _discovery_files(tmp_path, '<script src="bad.js"></script>', {"bad.js": b"\xff\xfe\x00"})
    assert "bad.js" in files


def test_resolve_reference_query_only_skipped(tmp_path: Path) -> None:
    files = _discovery_files(tmp_path, '<img src="?v=1"><img src="?cb=2">')
    assert list(files) == ["index.html"]


def test_discover_dependency_files_non_file_entry(tmp_path: Path) -> None:
    from app.services.hosting.packager import _discover_dependency_files

    root = tmp_path.resolve()
    discovered = _discover_dependency_files(root, root)
    assert discovered == set()


def test_scan_file_references_unknown_suffix() -> None:
    from app.services.hosting.packager import _scan_file_references

    assert _scan_file_references(Path("data.txt"), "anything") == []


def test_collect_single_non_html_file_without_hint(tmp_path: Path) -> None:
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    files = collect_publish_files(pdf)
    assert list(files) == ["report.pdf"]
    assert files["report.pdf"].encoding == "base64"


def test_merge_assets_falls_back_to_index_candidate(tmp_path: Path) -> None:
    """When the hinted entry is absent, the sandbox index.html is the merge root."""
    vault_obj = tmp_path / "obj" / "abc"
    vault_obj.parent.mkdir()
    vault_obj.write_text("<h1>vault</h1>", encoding="utf-8")
    asset_root = tmp_path / "sandbox"
    asset_root.mkdir()
    (asset_root / "index.html").write_text('<link rel="stylesheet" href="style.css">', encoding="utf-8")
    (asset_root / "style.css").write_text("body{}", encoding="utf-8")

    files = collect_publish_files(vault_obj, asset_root=asset_root, entry_name_hint="missing.html")

    assert "index.html" in files
    assert "style.css" in files


def test_merge_assets_no_entry_keeps_vault_file(tmp_path: Path) -> None:
    vault_obj = tmp_path / "obj" / "abc"
    vault_obj.parent.mkdir()
    vault_obj.write_text("<h1>vault</h1>", encoding="utf-8")
    asset_root = tmp_path / "empty_sandbox"
    asset_root.mkdir()

    files = collect_publish_files(vault_obj, asset_root=asset_root, entry_name_hint="page.html")

    assert list(files) == ["index.html"]


def test_collect_directory_skips_non_allowed_files(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>Hi</h1>", encoding="utf-8")
    (tmp_path / "secret.db").write_bytes(b"db")
    (tmp_path / ".DS_Store").write_bytes(b"")
    # package-lock.json has an allowed extension but is an excluded filename.
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    files = collect_publish_files(tmp_path)
    assert "index.html" in files
    assert "secret.db" not in files
    assert ".DS_Store" not in files
    assert "package-lock.json" not in files


def test_collect_directory_skips_sensitive_dirs(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>Hi</h1>", encoding="utf-8")
    mem = tmp_path / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    (mem / "notes.txt").write_text("secret", encoding="utf-8")
    files = collect_publish_files(tmp_path)
    assert "memory/notes.txt" not in files


def test_collect_rejects_non_regular_file(tmp_path: Path) -> None:
    import os

    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="Invalid artifact physical format"):
        collect_publish_files(fifo)


def test_validate_payload_single_html_with_asset() -> None:
    validate_publish_payload(
        {
            "page.html": PublishFile(path="page.html", content="<h1>Hi</h1>"),
            "style.css": PublishFile(path="style.css", content="body{}"),
        }
    )
    with pytest.raises(ValueError, match="index.html"):
        validate_publish_payload(
            {
                "a.html": PublishFile(path="a.html", content="<h1>A</h1>"),
                "b.html": PublishFile(path="b.html", content="<h1>B</h1>"),
            }
        )


def test_is_blocked_path_outside_root(tmp_path: Path) -> None:
    from app.services.hosting.packager import _is_blocked_path

    root = tmp_path.resolve()
    outside = root.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    assert _is_blocked_path(root, outside) is True
    assert _is_blocked_path(root, root / "memory" / "notes.txt") is True
    assert _is_blocked_path(root, root / ".env") is True
    assert _is_blocked_path(root, root) is False


def test_merge_disk_assets_none_hint(tmp_path: Path) -> None:
    from app.services.hosting.packager import _merge_disk_assets

    files = {}
    merged, _ = _merge_disk_assets(files, 0, allowed_root=tmp_path.resolve(), entry_hint=None)
    assert merged == files
