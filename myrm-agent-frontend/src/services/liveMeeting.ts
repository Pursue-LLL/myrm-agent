/**
 * [INPUT]
 * - @/lib/api::apiRequest,getApiUrl (POS: frontend API request helper)
 * - @/services/wikiService::buildWikiApiPath (POS: Wiki API path constructor)
 *
 * [OUTPUT]
 * - LiveMeetingSnapshot: live meeting rolling-notes DTO
 * - ingestLiveTranscript / getLiveMeetingSnapshot / finalizeLiveMeeting
 *
 * [POS]
 * Frontend live meeting notes API client. `/wiki/meeting-notes/live/*` REST contract
 * for in-meeting rolling structured notes (summary / decisions / action items).
 */

import { apiRequest, getApiUrl } from '@/lib/api';
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

function sessionPath(sessionId: string): string {
  return buildWikiApiPath(`/wiki/meeting-notes/live/${encodeURIComponent(sessionId)}`);
}

/**
 * Send one finalized transcript line. `lineId` must be stable for the lifetime of that
 * utterance: a retried request with the same id is ignored by the server instead of
 * duplicating the line in the transcript and the distilled minutes.
 */
export async function ingestLiveTranscript(sessionId: string, line: LiveTranscriptLine): Promise<LiveMeetingSnapshot> {
  return apiRequest<LiveMeetingSnapshot>(getApiUrl(`${sessionPath(sessionId)}/ingest`), {
    method: 'POST',
    body: JSON.stringify({
      text: line.text,
      line_id: line.id,
      ...(line.timestamp !== undefined ? { timestamp: line.timestamp } : {}),
    }),
  });
}

export async function getLiveMeetingSnapshot(sessionId: string): Promise<LiveMeetingSnapshot> {
  return apiRequest<LiveMeetingSnapshot>(getApiUrl(sessionPath(sessionId)), { method: 'GET' });
}

export async function finalizeLiveMeeting(sessionId: string): Promise<LiveMeetingSnapshot> {
  return apiRequest<LiveMeetingSnapshot>(getApiUrl(`${sessionPath(sessionId)}/finalize`), {
    method: 'POST',
    body: JSON.stringify({}),
  });
}
