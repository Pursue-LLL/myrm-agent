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
  action_items: LiveMeetingActionItem[];
  published_wiki_paths: string[];
  error: string;
}

function sessionPath(sessionId: string): string {
  return buildWikiApiPath(`/wiki/meeting-notes/live/${encodeURIComponent(sessionId)}`);
}

export async function ingestLiveTranscript(
  sessionId: string,
  text: string,
  timestamp?: number,
): Promise<LiveMeetingSnapshot> {
  return apiRequest<LiveMeetingSnapshot>(getApiUrl(`${sessionPath(sessionId)}/ingest`), {
    method: 'POST',
    body: JSON.stringify({ text, ...(timestamp !== undefined ? { timestamp } : {}) }),
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
