"""Architecture test: no application code takes a client address from a header the visitor can write."""

from __future__ import annotations

import ast
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent.parent.parent / "app"

# Headers that carry an address written by the visitor or by any hop on the way. The address a limit keys on comes from
# app.core.security.client_address::client_ip; uvicorn applies X-Forwarded-For itself, and only for the peers named in
# FORWARDED_ALLOW_IPS.
_ADDRESS_HEADERS = frozenset({"x-forwarded-for", "x-real-ip", "forwarded", "cf-connecting-ip", "true-client-ip", "x-client-ip"})

# trust_zone.py reads them to tell tunnel ingress from local dev proxying; it never picks an address a limit keys on.
_ALLOWED_FILES = frozenset({"remote_access/trust_zone.py"})


def _files_naming_address_headers(root: Path) -> set[str]:
    """Return the files under ``root`` holding a string constant that is exactly one of the address header names."""
    found: set[str] = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.strip().lower() in _ADDRESS_HEADERS
            for node in ast.walk(tree)
        ):
            found.add(path.relative_to(root).as_posix())
    return found


def test_only_the_listed_files_name_an_address_header() -> None:
    assert sorted(_files_naming_address_headers(_APP_ROOT) - _ALLOWED_FILES) == [], (
        "Read the client address with app.core.security.client_address.client_ip, never from a forwarded header."
    )


def test_every_listed_file_still_names_an_address_header() -> None:
    assert sorted(_ALLOWED_FILES - _files_naming_address_headers(_APP_ROOT)) == [], (
        "a listed file that no longer reads one must leave the list"
    )


def test_detector_flags_a_header_read_and_not_prose(tmp_path: Path) -> None:
    (tmp_path / "reads.py").write_text('def key(request):\n    return request.headers.get("X-Forwarded-For")\n', encoding="utf-8")
    (tmp_path / "prose.py").write_text('"""Never trusts X-Forwarded-For or X-Real-IP."""\n', encoding="utf-8")
    assert _files_naming_address_headers(tmp_path) == {"reads.py"}
