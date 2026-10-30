"""Blueprint fill response: the server model and the frontend interface declare the same fields.

The frontend turns the fill response into a create request field by field, so a field the server returns that the
interface does not declare is never read and the blueprint's value is dropped; a field the interface declares that the
server no longer returns reads as undefined and the job silently falls back to its default.
"""

from __future__ import annotations

import re

import pytest

from app.api.cron.routes.blueprints import BlueprintFillResponse
from tests.support.frontend_api_paths import FRONTEND_SRC

pytestmark = pytest.mark.architecture

_CRON_TYPES = FRONTEND_SRC / "services" / "cron.types.ts"
_INTERFACE_RE = re.compile(r"export interface BlueprintFillResponse \{(?P<body>.*?)\n\}", re.DOTALL)
_PROPERTY_RE = re.compile(r"(?P<name>\w+)\??:")


def _frontend_fields() -> set[str]:
    match = _INTERFACE_RE.search(_CRON_TYPES.read_text(encoding="utf-8"))
    assert match, f"BlueprintFillResponse interface not found in {_CRON_TYPES}"
    fields: set[str] = set()
    depth = 0
    for line in match.group("body").splitlines():
        # Only the interface's own properties count; the lines of an inline object type belong to its property.
        if depth == 0 and (property_match := _PROPERTY_RE.match(line.strip())):
            fields.add(property_match.group("name"))
        depth += line.count("{") - line.count("}")
    return fields


@pytest.mark.skipif(not _CRON_TYPES.is_file(), reason="frontend sources are not part of this checkout")
def test_fill_response_fields_match_between_server_and_frontend() -> None:
    server = set(BlueprintFillResponse.model_fields)
    frontend = _frontend_fields()

    assert len(frontend) > 10, "frontend interface scan found almost no fields; the scan is broken"
    assert not server - frontend, (
        f"The server returns fill-response fields cron.types.ts BlueprintFillResponse does not declare: "
        f"{sorted(server - frontend)}"
    )
    assert not frontend - server, (
        f"cron.types.ts BlueprintFillResponse declares fields the server does not return: {sorted(frontend - server)}"
    )
