"""Chrome E2E: live meeting notes end-to-end from inside the real WebUI session (Lane-B + Lane-C).

The whole business flow runs **in the page**, against the backend the WebUI itself talks
to, so there is exactly one backend and one wiki vault in the loop:

  1. open Settings -> Wiki like a user (real page, real session cookies);
  2. post a real meeting transcript to the same REST contract the voice Live board uses
     (`POST /wiki/meeting-notes/live/{sid}/ingest`, one `line_id` per utterance);
  3. replay one line to prove at-least-once delivery cannot duplicate it;
  4. `finalize` -> the real LLM distills and the real raw gate publishes to the wiki;
  5. reload the page and assert the meeting note is visible in the real UI tree.

Driving it from the page (rather than from pytest) is what makes the assertion honest:
a pinned private-epoch API can run against an isolated vault while the page is served by
another backend, and a test that mixes the two silently asserts nothing.

Residue control: the published raw source is deleted through the same in-page API in the
finally path, and finalize always releases the live session.
"""

from __future__ import annotations

import json
import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    navigate_mcp_page,
    open_wiki_settings_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

# Real meeting transcripts, one per run. The wiki slug is derived from the LLM-authored
# title, so each run gets its own project codename: runs stay independent (no title
# collision with a leftover note) and the published path is assertable.
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


def _transcript_lines(codename: str) -> list[dict[str, object]]:
    """A real meeting transcript; long enough to cross the rolling-refresh gate."""
    return [
        {
            "text": (
                f"Alice: Let us confirm the release plan for {codename}. We want the beta live on "
                "Friday so the marketing team has the weekend to prepare the announcement."
            ),
            "timestamp": 0.0,
        },
        {
            "text": (
                f"Bob: The transcription vendor contract for {codename} expired last month and legal "
                "review is still pending, so nobody has signed it off and we have no guarantee of "
                "service continuity."
            ),
            "timestamp": 14.0,
        },
        {
            "text": (
                f"Carol: I will draft the {codename} migration checklist and circulate it before "
                "Thursday. Alice will make the final go or no go decision on Friday morning once the "
                "vendor is settled."
            ),
            "timestamp": 29.0,
        },
    ]


# Runs the whole meeting flow with same-origin requests, i.e. exactly the backend the
# page is served by. Returns the finalize payload plus the replay guard result.
_RUN_MEETING_JS = """(async () => {
  const lines = __LINES__;
  const sessionId = __SESSION__;
  const slugSeed = __CODENAME__;
  const base = '/api/v1/wiki/meeting-notes/live/' + encodeURIComponent(sessionId);

  const post = async (path, body) => {
    const response = await fetch(path, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
    const text = await response.text();
    let payload = null;
    try { payload = text ? JSON.parse(text) : null; } catch (error) { payload = { raw: text }; }
    return { status: response.status, payload };
  };

  try {
    let last = null;
    for (let index = 0; index < lines.length; index += 1) {
      last = await post(base + '/ingest', {
        text: lines[index].text,
        timestamp: lines[index].timestamp,
        line_id: sessionId + '-line-' + index,
      });
      if (last.status !== 200) {
        return { ready: false, stage: 'ingest-' + index, status: last.status, payload: last.payload };
      }
    }
    const ingested = last.payload;

    // At-least-once delivery: replaying a line must not inflate the transcript.
    const replay = await post(base + '/ingest', {
      text: lines[0].text,
      timestamp: lines[0].timestamp,
      line_id: sessionId + '-line-0',
    });
    if (replay.status !== 200) {
      return { ready: false, stage: 'replay', status: replay.status, payload: replay.payload };
    }

    const final = await post(base + '/finalize?auto_compile=false', {});
    if (final.status !== 200) {
      return { ready: false, stage: 'finalize', status: final.status, payload: final.payload };
    }
    const body = final.payload || {};
    const published = body.published_wiki_paths || [];
    const slug = (published[0] || '').split('/').pop().replace(/\\.md$/, '');

    const contract = {
      lineCountExact: ingested.line_count === lines.length,
      replayKeptCount: replay.payload.line_count === lines.length,
      replayKeptChars: replay.payload.transcript_chars === ingested.transcript_chars,
      hasTitle: Boolean(body.title),
      hasSummary: (body.summary || '').length > 20,
      hasRisks: (body.risks || []).length > 0,
      publishedClean: published.length > 0 && published.every(
        (entry) => typeof entry === 'string'
          && entry.startsWith('meeting-notes/')
          && !entry.includes('/Users/'),
      ),
      isThisRun: slug.toLowerCase().includes(slugSeed.toLowerCase()),
    };
    const allOk = Object.values(contract).every(Boolean);
    return {
      ready: allOk,
      stage: 'contract',
      sessionId,
      slug,
      publishedPath: published[0] || '',
      contract,
      title: body.title || '',
      risks: body.risks || [],
      actionItems: body.action_items || [],
      sessionReleased: null,
    };
  } catch (error) {
    return { ready: false, stage: 'exception', error: String(error) };
  }
})()"""

# Verifies the session was released after finalize and the published note is gone.
_VERIFY_CLEANUP_JS = """(async () => {
  try {
    const response = await fetch(
      '/api/v1/wiki/meeting-notes/live/' + encodeURIComponent(__SESSION__),
      { headers: { accept: 'application/json' } },
    );
    return { ready: response.status === 404, status: response.status };
  } catch (error) {
    return { ready: false, error: String(error) };
  }
})()"""

_DELETE_NOTE_JS = """(async () => {
  try {
    const response = await fetch(
      '/api/v1/wiki/raw/' + encodeURIComponent(__PATH__),
      {
        method: 'DELETE',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ forget_reason: 'e2e live meeting notes cleanup' }),
      },
    );
    return { ready: response.ok, status: response.status };
  } catch (error) {
    return { ready: false, error: String(error) };
  }
})()"""

_NOTE_VISIBLE_JS = """(() => {
  const text = document.body ? document.body.innerText : '';
  const hasShell = Boolean(document.querySelector('[data-testid="wiki-settings-shell"]'));
  const hasNoteNode = text.includes(__SLUG__);
  return {
    ready: hasShell && hasNoteNode,
    hasShell,
    hasNoteNode,
    apiStatus: __API_STATUS__,
    sample: text.slice(0, 300),
  };
})()"""

# Confirms the published note is really in the tree the page reads.
_TREE_HAS_NOTE_JS = """(async () => {
  try {
    const response = await fetch('/api/v1/wiki/raw/tree', { headers: { accept: 'application/json' } });
    const payload = await response.json();
    const hit = JSON.stringify(payload || []).includes(__SLUG__);
    return { ready: hit, status: response.status };
  } catch (error) {
    return { ready: false, error: String(error) };
  }
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_live_meeting_notes_publish_real_wiki_note_visible_in_ui() -> None:
    """Real transcript -> real LLM -> real wiki publish -> real UI render, in-page."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    session_id = f"e2e-live-{uuid.uuid4().hex[:12]}"
    codename = _PROJECT_CODENAMES[uuid.uuid4().int % len(_PROJECT_CODENAMES)]
    lines = _transcript_lines(codename)
    published_path: str | None = None

    wiki_url = f"{ui_url.rstrip('/')}/settings/wiki"
    try:
        warm_ui_route("/settings/wiki")
        with open_wiki_settings_mcp_page(wiki_url, request_timeout_sec=300.0) as (client, page):
            # 1-4) The whole meeting runs in the page against the page's own backend.
            result = wait_for_state(
                client,
                page,
                _RUN_MEETING_JS.replace("__LINES__", json.dumps(lines))
                .replace("__SESSION__", json.dumps(session_id))
                .replace("__CODENAME__", json.dumps(codename)),
                timeout_sec=300.0,
            )
            assert result["stage"] != "exception", result
            assert result["stage"] == "contract", f"meeting flow failed at {result['stage']}: {result}"
            contract = result["contract"]
            for name, ok in contract.items():
                assert ok is True, f"{name} failed: {result}"
            assert result["title"], result
            assert result["risks"], result
            published_path = str(result["publishedPath"])
            assert published_path.startswith("meeting-notes/"), published_path
            assert "/Users/" not in published_path, published_path

            # 5) Reload so the page re-reads the tree it renders from, then assert the
            #    meeting deliverable is visible in the real UI.
            navigate_mcp_page(client, page, wiki_url, timeout_ms=90_000)
            in_tree = wait_for_state(
                client,
                page,
                _TREE_HAS_NOTE_JS.replace("__SLUG__", json.dumps(str(result["slug"]))),
                timeout_sec=120.0,
            )
            assert in_tree["ready"] is True, f"published note missing from the UI's tree: {in_tree}"

            visible = wait_for_state(
                client,
                page,
                _NOTE_VISIBLE_JS.replace("__SLUG__", json.dumps(str(result["slug"])))
                .replace("__API_STATUS__", json.dumps(in_tree["status"])),
                timeout_sec=120.0,
            )
            assert visible["hasShell"] is True, f"wiki shell missing: {visible}"
            assert visible["hasNoteNode"] is True, f"published note not visible in UI: {visible}"

            # The live session must be released by finalize, not leak in the registry.
            released = wait_for_state(
                client,
                page,
                _VERIFY_CLEANUP_JS.replace("__SESSION__", json.dumps(session_id)),
                timeout_sec=60.0,
            )
            assert released["ready"] is True, f"live session was not released: {released}"
    finally:
        # Sandbox isolation: never leave residue in the real wiki vault.
        if published_path is not None:
            with open_wiki_settings_mcp_page(wiki_url, warm=False) as (client, page):
                client.evaluate(
                    page,
                    _DELETE_NOTE_JS.replace("__PATH__", json.dumps(published_path)),
                    timeout_sec=60.0,
                )
