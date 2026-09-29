"""Chrome E2E: live meeting notes publish a real wiki note visible in the real UI (Lane-B + Lane-C).

Real business task flow, zero mocks on the key path:
  1. a real meeting transcript is ingested through the same REST contract the
     voice Live board uses (`POST /wiki/meeting-notes/live/{sid}/ingest`);
  2. the real LLM distills it into structured notes (summary/decisions/risks/actions);
  3. `finalize` publishes the minutes into the real wiki vault;
  4. a real Chrome session opens Settings -> Wiki for that published note and the
     rendered raw-source tree must show it, i.e. the meeting deliverable is visible
     to the user in the real knowledge UI.

Note on scope: the raw-source tree lists file names only (there is no raw markdown
preview in this UI), so the LLM-authored content is asserted from the real finalize
response above; the browser assertion covers real UI visibility of the deliverable.

Residue control: the published raw source is deleted through the real wiki API
in the finally block, and the live session is always finalized (which releases it).
"""

from __future__ import annotations

import json
import random
import urllib.parse
import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_wiki_settings_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

# Real meeting transcripts, one per run. The wiki slug is derived from the
# LLM-authored title, so each run gets its own project codename: that keeps runs
# independent (no title collision with a leftover note) and lets the test assert
# the published path deterministically.
_PROJECT_CODENAMES: tuple[str, ...] = (
    "Nimbus",
    "Halcyon",
    "Cobalt",
    "Zephyr",
    "Lantern",
    "Quartz",
    "Basalt",
    "Meridian",
)


def _transcript_lines(codename: str) -> tuple[tuple[str, float], ...]:
    """A real meeting transcript; long enough to cross the rolling-refresh gate."""
    return (
        (
            f"Alice: Let us confirm the release plan for {codename}. We want the beta live on Friday "
            "so the marketing team has the weekend to prepare the announcement.",
            0.0,
        ),
        (
            f"Bob: The transcription vendor contract for {codename} expired last month and legal "
            "review is still pending, so nobody has signed it off and we have no guarantee of "
            "service continuity.",
            14.0,
        ),
        (
            f"Carol: I will draft the {codename} migration checklist and circulate it before "
            "Thursday. Alice will make the final go or no go decision on Friday morning once the "
            "vendor is settled.",
            29.0,
        ),
    )

_NOTE_RENDERED_JS = """(async () => {
  const text = document.body ? document.body.innerText : '';
  const hasShell = Boolean(document.querySelector('[data-testid="wiki-settings-shell"]'));
  const slug = __SLUG__;
  const hasNoteNode = text.includes(slug);

  // Probe the same endpoint the page uses, so a failure tells us whether the backend
  // omitted the note or the tree simply had not rendered yet.
  let apiStatus = -1;
  let apiHasNode = false;
  let apiError = '';
  try {
    const response = await fetch('/api/v1/wiki/raw/tree', { headers: { accept: 'application/json' } });
    apiStatus = response.status;
    const payload = await response.json();
    apiHasNode = JSON.stringify(payload ?? []).includes(slug);
  } catch (error) {
    apiError = String(error);
  }

  return {
    ready: hasShell && hasNoteNode,
    hasShell,
    hasNoteNode,
    apiStatus,
    apiHasNode,
    apiError,
    sample: text.slice(0, 600),
  };
})()"""


def _ingest_live_transcript(
    base_url: str, session_id: str, lines: tuple[tuple[str, float], ...]
) -> dict[str, object]:
    """Drive the real ingest contract the Live board uses; return the last snapshot."""
    snapshot: dict[str, object] = {}
    for index, (text, timestamp) in enumerate(lines):
        payload = http_json(
            "POST",
            f"{base_url.rstrip('/')}/api/v1/wiki/meeting-notes/live/{session_id}/ingest",
            {"text": text, "timestamp": timestamp, "line_id": f"{session_id}-line-{index}"},
            timeout_sec=90.0,
        )
        assert isinstance(payload, dict)
        snapshot = payload
    return snapshot


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_live_meeting_notes_publish_real_wiki_note_visible_in_ui() -> None:
    """Real transcript -> real LLM -> real wiki publish -> real UI render."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    # The browser page talks to the backend behind the WebUI origin, while a pinned
    # private-epoch API can run against an isolated wiki vault. Drive the meeting flow
    # through the WebUI origin so the test and the page observe one backend and one vault.
    base_url = ui_url

    session_id = f"e2e-live-{uuid.uuid4().hex[:12]}"
    codename = random.choice(_PROJECT_CODENAMES)
    lines = _transcript_lines(codename)
    published_path: str | None = None

    try:
        # 1) Real ingest through the REST contract the Live board calls. Line ids make
        #    ingest idempotent, so the count is exact even when the client retries.
        live = _ingest_live_transcript(base_url, session_id, lines)
        assert live["session_id"] == session_id
        assert int(live["line_count"]) == len(lines), live
        assert int(live["transcript_chars"]) > 200

        # 2) Replay the first line (at-least-once delivery): must not be counted twice.
        replay = http_json(
            "POST",
            f"{base_url.rstrip('/')}/api/v1/wiki/meeting-notes/live/{session_id}/ingest",
            {
                "text": lines[0][0],
                "timestamp": lines[0][1],
                "line_id": f"{session_id}-line-0",
            },
            timeout_sec=90.0,
        )
        assert isinstance(replay, dict)
        assert int(replay["line_count"]) == len(lines), f"replayed line was duplicated: {replay}"
        assert int(replay["transcript_chars"]) == int(live["transcript_chars"]), replay

        # 3) finalize forces the real distillation and publishes to the real wiki.
        final = http_json(
            "POST",
            f"{base_url.rstrip('/')}/api/v1/wiki/meeting-notes/live/{session_id}/finalize?auto_compile=false",
            timeout_sec=90.0,
        )
        assert isinstance(final, dict)
        published = final["published_wiki_paths"]
        assert isinstance(published, list) and published, f"no wiki note published: {final}"
        # Contract: plain vault-relative path strings (never a result repr / absolute path).
        for entry in published:
            assert isinstance(entry, str), f"published path must be a string, got {type(entry)}"
            assert entry.startswith("meeting-notes/"), entry
            assert "/Users/" not in entry, f"absolute local path leaked: {entry}"
        published_path = str(published[0])
        # This run's own deliverable, not a leftover from a previous run.
        assert codename.lower() in published_path.lower(), (
            f"published note is not this run's meeting: {published_path}"
        )

        # 4) The real LLM must have produced structured content.
        title = str(final["title"] or "")
        summary = str(final["summary"] or "")
        risks = final["risks"] or []
        assert title, f"real LLM produced no title: {final}"
        assert len(summary) > 20, f"real LLM produced no summary: {final}"
        assert isinstance(risks, list) and risks, f"real LLM produced no risks: {final}"

        # 5) Real browser: the published meeting note must be visible in the real
        #    knowledge UI raw-source tree (rawPath auto-expands to the node).
        slug = published_path.rsplit("/", 1)[-1].removesuffix(".md")
        warm_ui_route("/settings/wiki")
        note_url = (
            f"{ui_url.rstrip('/')}/settings/wiki?rawPath={urllib.parse.quote(published_path, safe='')}"
        )
        with open_wiki_settings_mcp_page(note_url, request_timeout_sec=300.0) as (client, page):
            rendered = wait_for_state(
                client,
                page,
                _NOTE_RENDERED_JS.replace("__SLUG__", json.dumps(slug)),
                page_url=note_url,
                timeout_sec=120.0,
            )
            assert rendered["hasShell"] is True, f"wiki shell missing: {rendered}"
            assert rendered["hasNoteNode"] is True, f"published note not visible in UI: {rendered}"
    finally:
        # Sandbox isolation: never leave residue in the real wiki vault.
        if published_path is not None:
            http_json(
                "DELETE",
                f"{base_url.rstrip('/')}/api/v1/wiki/raw/{urllib.parse.quote(published_path, safe='/')}",
                {"forget_reason": "e2e live meeting notes cleanup"},
                expected_statuses=frozenset({200, 204, 404}),
                timeout_sec=60.0,
            )
