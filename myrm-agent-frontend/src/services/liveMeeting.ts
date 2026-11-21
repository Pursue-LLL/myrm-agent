/**
 * [INPUT]
 * - @/lib/api::apiRequest, fetchOnPageExit (POS: frontend API request helper that owns the base URL, so callers pass endpoint paths)
 * - @/services/wikiService::buildWikiApiPath (POS: Wiki API path constructor carrying the agent scope of the vault)
 *
 * [OUTPUT]
 * - LiveMeetingSnapshot: live meeting rolling-notes DTO
 * - ingestLiveTranscript / finalizeLiveMeeting / finalizeLiveMeetingOnPageExit
 *
 * [POS]
 * Frontend live meeting notes API client. `/wiki/meeting-notes/live/*` REST contract
 * for in-meeting rolling structured notes (summary / decisions / action items).
 * Ingest and finalize never raise a toast of their own (the caller reports the outcome of the
 * finalize it waits for); finalize publishes into the vault of the given agent scope.
 */

import { apiRequest, fetchOnPageExit } from '@/lib/api';
import { buildWikiApiPath } from '@/services/wikiService';

export interface LiveMeetingActionItem {
  description: string;
  owner: string | null;
  due_hint: string | null;
}

/** One finalized transcript utterance, with the id that makes its ingest idempotent. */
export interface LiveTranscriptLine {
  id: string;
  text: string;
  timestamp?: number;
}

export interface LiveMeetingSnapshot {
  success: boolean;
  session_id: string;
  line_count: number;
  transcript_chars: number;
  refreshed: boolean;
  title: string;
  summary: string;
  decisions: string[];
  debate_points: string[];
  risks: string[];
  action_items: LiveMeetingActionItem[];
  published_wiki_paths: string[];
  error: string;
}

const LIVE_NOTES_PATH = '/wiki/meeting-notes/live';

// Distilling the whole transcript and writing the minutes takes far longer than the 30 s of an ordinary request.
const FINALIZE_TIMEOUT_MS = 120_000;

// Each action is written out as a literal segment: the route-consumer gate recognises a caller by its literal path.
function ingestPath(sessionId: string, agentId?: string | null): string {
  return buildWikiApiPath(`${LIVE_NOTES_PATH}/${encodeURIComponent(sessionId)}/ingest`, agentId);
}

function finalizePath(sessionId: string, agentId?: string | null): string {
  return buildWikiApiPath(`${LIVE_NOTES_PATH}/${encodeURIComponent(sessionId)}/finalize`, agentId);
}

/**
 * Send one finalized transcript line. `line.id` must be stable for the lifetime of that
 * utterance: a retried request with the same id is ignored by the server instead of
 * duplicating the line in the transcript and the distilled minutes. `agentId` keeps the
 * session on the same agent vault archiver as its finalize.
 */
export async function ingestLiveTranscript(
  sessionId: string,
  line: LiveTranscriptLine,
  agentId?: string | null,
): Promise<LiveMeetingSnapshot> {
  return apiRequest<LiveMeetingSnapshot>(ingestPath(sessionId, agentId), {
    method: 'POST',
    silent: true,
    body: JSON.stringify({
      text: line.text,
      line_id: line.id,
      ...(line.timestamp !== undefined ? { timestamp: line.timestamp } : {}),
    }),
  });
}

/** Publish the minutes into the vault of `agentId` (the default vault when omitted) and drop the live session. */
export async function finalizeLiveMeeting(sessionId: string, agentId?: string | null): Promise<LiveMeetingSnapshot> {
  return apiRequest<LiveMeetingSnapshot>(finalizePath(sessionId, agentId), {
    method: 'POST',
    silent: true,
    timeout: FINALIZE_TIMEOUT_MS,
  });
}

/** Finalize for a page that is going away: sent without waiting for the answer, so the outcome is never seen. */
export function finalizeLiveMeetingOnPageExit(sessionId: string, agentId?: string | null): void {
  fetchOnPageExit(finalizePath(sessionId, agentId), { method: 'POST' });
}
