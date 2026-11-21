/**
 * [INPUT]
 * - @/services/liveMeeting (POS: live meeting API client; the boundary replaced by doubles here)
 * - @/lib/utils/toast::toast (POS: unified toast wrapper; replaced by doubles here)
 * - @/hooks/voice/useLiveMeetingNotes (POS: In-meeting live notes session: transcript upload, rolling structured notes, minutes published when the session ends)
 *
 * [OUTPUT]
 * - ingestLiveTranscript / finalizeLiveMeeting / finalizeLiveMeetingOnPageExit / toastSuccess / toastError: the doubles
 * - EMPTY_SNAPSHOT / ROLLING_SNAPSHOT / PUBLISHED_SNAPSHOT: what the server answers before, during and after publishing
 * - deferred: a promise a test settles by hand
 * - renderLive: mounts the hook the way the voice session does
 * - sentTexts: the transcript lines sent so far, in order
 * - settle: lets pending effects and promises run
 * - resetLiveNotesKit: clears storage and doubles, and points the server at a healthy answer
 *
 * [POS]
 * Shared base of the useLiveMeetingNotes behaviour tests. It must be imported before anything that loads the hook:
 * vi.mock registers when this module is evaluated. The service client and the toast are the boundary; the queue, the
 * meeting boundaries and the publish rules are real.
 */
import { act, renderHook } from '@testing-library/react';
import { vi } from 'vitest';
import type { LiveTranscriptLine } from '@/services/liveMeeting';
import { useLiveMeetingNotes } from '@/hooks/voice/useLiveMeetingNotes';

export const ingestLiveTranscript = vi.fn();
export const finalizeLiveMeeting = vi.fn();
export const finalizeLiveMeetingOnPageExit = vi.fn();
export const toastSuccess = vi.fn();
export const toastError = vi.fn();

vi.mock('@/services/liveMeeting', () => ({
  ingestLiveTranscript: (...args: unknown[]) => ingestLiveTranscript(...args),
  finalizeLiveMeeting: (...args: unknown[]) => finalizeLiveMeeting(...args),
  finalizeLiveMeetingOnPageExit: (...args: unknown[]) => finalizeLiveMeetingOnPageExit(...args),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));

export const EMPTY_SNAPSHOT = {
  success: true,
  session_id: 'x',
  line_count: 1,
  transcript_chars: 5,
  refreshed: false,
  title: '',
  summary: '',
  decisions: [],
  debate_points: [],
  risks: [],
  action_items: [],
  published_wiki_paths: [],
  error: '',
};
export const ROLLING_SNAPSHOT = { ...EMPTY_SNAPSHOT, summary: 'Agreed to ship on Friday', line_count: 3 };
export const PUBLISHED_SNAPSHOT = {
  ...ROLLING_SNAPSHOT,
  title: 'Standup',
  published_wiki_paths: ['meeting-notes/meeting-Standup.md'],
};

export function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

interface LiveProps {
  sessionKey?: string;
  agentId?: string;
  active?: boolean;
}

/** Mounts the hook the way the voice session does: `active` follows the running state of the session. */
export function renderLive(initialProps: LiveProps = {}) {
  return renderHook(({ sessionKey, agentId, active }: LiveProps) => useLiveMeetingNotes(sessionKey, agentId, active), {
    initialProps,
  });
}

export const sentTexts = () => ingestLiveTranscript.mock.calls.map(([, line]) => (line as LiveTranscriptLine).text);
export const settle = () => act(async () => {});

export function resetLiveNotesKit(): void {
  window.sessionStorage.clear();
  ingestLiveTranscript.mockReset();
  ingestLiveTranscript.mockResolvedValue(EMPTY_SNAPSHOT);
  finalizeLiveMeeting.mockReset();
  finalizeLiveMeeting.mockResolvedValue(PUBLISHED_SNAPSHOT);
  finalizeLiveMeetingOnPageExit.mockReset();
  toastSuccess.mockReset();
  toastError.mockReset();
}
