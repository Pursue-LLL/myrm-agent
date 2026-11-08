"""Architecture gate: SSRF validation must live in core/security/guards only."""

from __future__ import annotations

import ast
from pathlib import Path

_HARNESS_SRC = Path(__file__).resolve().parents[2] / "src" / "myrm_agent_harness"

_FORBIDDEN_SSRF_PATTERNS = (
    "validate_url_for_ssrf",
    "async_validate_url_for_ssrf",
    "_validate_url_security",
)

_ALLOWED_SSRF_ROOTS = (
    _HARNESS_SRC / "core" / "security" / "guards",
    _HARNESS_SRC / "utils" / "url_utils",
)

_SCAN_ROOTS = (
    _HARNESS_SRC / "toolkits",
    _HARNESS_SRC / "agent",
)

# Diagnostics / ops probes — not agent outbound fetch paths.
_FOLLOW_REDIRECTS_ALLOWLIST = frozenset(
    {
        "observability/diagnostics/probes.py",
        "runtime/doctor.py",
        "toolkits/web_search/probe/local_probe.py",
        "toolkits/mcp/client.py",
    }
)

# Modules that open a connection by themselves.
_HTTP_CLIENT_ROOTS = frozenset({"httpx", "requests", "aiohttp", "urllib3", "curl_cffi"})
_HTTP_CLIENT_MODULES = frozenset({"urllib.request", "http.client"})

_SSRF_IMPORT_MARKERS = (
    "secure_fetch",
    "async_pin_url",
    "validate_url_for_ssrf",
    "async_validate_url_for_ssrf",
    "resolve_secure_http_target",
    "secure_get",
    "secure_request",
)


def _defines_ssrf_helper(path: Path, tree: ast.Module) -> list[str]:
    violations: list[str] = []
    rel = path.relative_to(_HARNESS_SRC)
    if any(str(rel).startswith(allowed.relative_to(_HARNESS_SRC).as_posix()) for allowed in _ALLOWED_SSRF_ROOTS):
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and any(
            pattern in node.name for pattern in _FORBIDDEN_SSRF_PATTERNS
        ):
            violations.append(f"{rel}:{node.lineno} defines {node.name}")
    return violations


def _uses_unprotected_follow_redirects(path: Path, source: str) -> bool:
    rel = path.relative_to(_HARNESS_SRC).as_posix()
    if rel in _FOLLOW_REDIRECTS_ALLOWLIST:
        return False
    if "follow_redirects=True" not in source:
        return False
    return not any(marker in source for marker in _SSRF_IMPORT_MARKERS)


def test_no_inline_ssrf_helpers_outside_core_guards() -> None:
    violations: list[str] = []
    for root in _SCAN_ROOTS:
        for path in root.rglob("*.py"):
            if "tests" in path.parts:
                continue
            if path.name == "ssrf.py":
                continue
            source = path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            violations.extend(_defines_ssrf_helper(path, tree))

    assert not violations, "Inline SSRF helpers outside core/security/guards:\n" + "\n".join(violations)


def test_no_unprotected_follow_redirects_in_agent_toolkits() -> None:
    violations: list[str] = []
    for root in _SCAN_ROOTS:
        for path in root.rglob("*.py"):
            if "tests" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            if _uses_unprotected_follow_redirects(path, source):
                rel = path.relative_to(_HARNESS_SRC)
                violations.append(f"{rel} uses follow_redirects=True without SSRF guard imports")

    assert not violations, "Unprotected follow_redirects in agent/toolkits:\n" + "\n".join(violations)


def test_toolkits_network_package_removed() -> None:
    network_dir = _HARNESS_SRC / "toolkits" / "network"
    assert not network_dir.exists(), "toolkits/network/ must not exist — use core/security/guards/ssrf.py"


def _imported_modules(path: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def test_wiki_url_ingestion_reaches_the_network_only_through_the_fetch_engine() -> None:
    """The engine's SSRF guard covers every hop; a client of its own in the wiki toolkit would bypass it."""
    wiki = _HARNESS_SRC / "toolkits" / "wiki"
    own_clients = {
        f"{name}: {module}"
        for name in ("source_loader.py", "wiki_agent_tools.py")
        for module in _imported_modules(wiki / name)
        if module.split(".")[0] in _HTTP_CLIENT_ROOTS or module in _HTTP_CLIENT_MODULES or "secure_fetch" in module
    }

    assert not own_clients, f"Wiki URL ingestion must fetch through web_fetch_tools only: {sorted(own_clients)}"
    assert "myrm_agent_harness.toolkits.web_fetch" in _imported_modules(wiki / "source_loader.py")


def test_image_reference_download_uses_secure_get() -> None:
    """Image reference URL download must use secure_get."""
    generator = _HARNESS_SRC / "toolkits" / "llms" / "image" / "generator.py"
    source = generator.read_text(encoding="utf-8")
    start = source.index("async def _download_reference_images")
    next_def = source.find("\nasync def ", start + 1)
    next_sync = source.find("\ndef ", start + 1)
    candidates = [x for x in (next_def, next_sync) if x != -1]
    end = min(candidates) if candidates else len(source)
    body = source[start:end]
    assert "secure_get" in body
    assert "create_httpx_client" not in body


def test_video_media_resolve_uses_secure_get() -> None:
    """Video/image input URL resolution must use secure_get."""
    engine = _HARNESS_SRC / "toolkits" / "llms" / "video" / "video_engine.py"
    source = engine.read_text(encoding="utf-8")
    start = source.index("async def _resolve_media_sources")
    next_def = source.find("\nasync def ", start + 1)
    end = next_def if next_def != -1 else len(source)
    body = source[start:end]
    assert "secure_get" in body
    assert "create_httpx_client" not in body
