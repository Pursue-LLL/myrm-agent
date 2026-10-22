"""The import report's count keys are exactly the keys the frontend renders, in every locale.

[POS]
tests/architecture/test_instance_archive_report_contract.py

[INPUT]
- app.services.instance_archive.stage_db::_SUMMARY_TABLES and the file-derived counts of import_service
- myrm-agent-frontend/src/lib/instance-archive/counts.ts: COUNT_KEYS
- myrm-agent-frontend/locales/*.json: instanceArchive.report.counts

[OUTPUT]
- Fails when the server emits a count the UI cannot show, or the UI waits for one the server never sends.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.services.instance_archive import import_service, stage_db

_FRONTEND = Path(__file__).resolve().parents[3] / "myrm-agent-frontend"
_COUNTS_TS = _FRONTEND / "src" / "lib" / "instance-archive" / "counts.ts"
_LOCALES = _FRONTEND / "locales"
_SKIP_WITHOUT_FRONTEND = pytest.mark.skipif(not _COUNTS_TS.is_file(), reason="frontend sources are not part of this checkout")

_COUNT_KEYS_RE = re.compile(r"COUNT_KEYS\s*=\s*\[(?P<body>[^\]]*)\]")
_FILE_COUNT_RE = re.compile(r'counts\["(?P<key>\w+)"\]\s*=')


def _server_count_keys() -> set[str]:
    source = Path(import_service.__file__).read_text(encoding="utf-8")
    return set(stage_db._SUMMARY_TABLES) | {m.group("key") for m in _FILE_COUNT_RE.finditer(source)}


def _frontend_count_keys() -> set[str]:
    match = _COUNT_KEYS_RE.search(_COUNTS_TS.read_text(encoding="utf-8"))
    assert match is not None, "COUNT_KEYS not found in counts.ts"
    return set(re.findall(r"'(\w+)'", match.group("body")))


@_SKIP_WITHOUT_FRONTEND
def test_server_count_keys_are_the_keys_the_frontend_renders() -> None:
    assert _server_count_keys() == _frontend_count_keys()


@_SKIP_WITHOUT_FRONTEND
@pytest.mark.parametrize("locale_file", sorted(_LOCALES.glob("*.json")), ids=lambda p: p.stem)
def test_every_rendered_count_has_a_label_in_every_locale(locale_file: Path) -> None:
    labels = json.loads(locale_file.read_text(encoding="utf-8"))["instanceArchive"]["report"]["counts"]
    assert _frontend_count_keys() <= set(labels)
