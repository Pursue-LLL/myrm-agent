"""Read-only probe against a real ima account; skipped unless ``IMA_CLIENT_ID`` and ``IMA_API_KEY`` are set.

Run it to confirm the response shapes the fixtures assume (library listing, folder entries, media info, notes)::

    IMA_CLIENT_ID=... IMA_API_KEY=... ./myrm-dev test myrm-agent/myrm-agent-server/tests/services/wiki/source_sync/ima/test_live_probe.py -s

It never writes to ima or to the wiki vault.
"""

from __future__ import annotations

import os

import pytest

from app.services.wiki.source_sync.ima.client import ImaClient
from app.services.wiki.source_sync.ima.models import ImaCredentials
from app.services.wiki.source_sync.ima.transport import ImaTransport

CLIENT_ID = os.environ.get("IMA_CLIENT_ID", "")
API_KEY = os.environ.get("IMA_API_KEY", "")

pytestmark = pytest.mark.skipif(not (CLIENT_ID and API_KEY), reason="needs IMA_CLIENT_ID and IMA_API_KEY")


async def test_live_account_shapes() -> None:
    async with ImaTransport(ImaCredentials(client_id=CLIENT_ID, api_key=API_KEY)) as transport:
        client = ImaClient(transport)
        await client.verify()

        libraries = await client.list_knowledge_bases()
        print(f"\nlibraries: {[(library.id[:8], library.name) for library in libraries]}")
        assert all(library.id and library.name for library in libraries)

        for library in libraries[:2]:
            listing = await client.list_knowledge_page(library.id)
            print(
                f"{library.name}: {len(listing.items)} items, {len(listing.folders)} folders, "
                f"is_end={listing.is_end}, types={sorted({item.media_type for item in listing.items if item.media_type is not None})}"
            )
            for entry in listing.items[:3]:
                info = await client.get_media_info(entry.media_id)
                print(
                    f"  {entry.title!r} type={info.media_type} has_url={bool(info.url)} "
                    f"signed_headers={sorted(info.headers)} note_id={bool(info.note_id)}"
                )

        notes = await client.list_notes_page(start=0)
        print(f"notes page: {len(notes.notes)} notes, is_end={notes.is_end}")
        if notes.notes:
            text = await client.get_note_text(notes.notes[0].note_id)
            print(f"first note body chars: {len(text)}")
