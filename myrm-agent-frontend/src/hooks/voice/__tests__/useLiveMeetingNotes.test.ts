import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LiveTranscriptLine } from '@/services/liveMeeting';

const ingestLiveTranscript = vi.fn();
const finalizeLiveMeeting = vi.fn();

vi.mock('@/services/liveMeeting', () => ({
  ingestLiveTranscript: (...args: unknown[]) => ingestLiveTranscript(...args),
  finalizeLiveMeeting: (...args: unknown[]) => finalizeLiveMeeting(...args),
}));

import { useLiveMeetingNotes } from '@/hooks/voice/useLiveMeetingNotes';

const EMPTY_SNAPSHOT = {
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

describe('useLiveMeetingNotes', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    ingestLiveTranscript.mockReset();
    ingestLiveTranscript.mockResolvedValue(EMPTY_SNAPSHOT);
    finalizeLiveMeeting.mockReset();
    finalizeLiveMeeting.mockResolvedValue(EMPTY_SNAPSHOT);
  });

  it('persists and resumes the session id for a stable key', () => {
    const first = renderHook(() => useLiveMeetingNotes('chat-1'));
    const sessionId = first.result.current.sessionId;
    expect(window.sessionStorage.getItem('myrm-live-notes:chat-1')).toBe(sessionId);
    first.unmount();

    const second = renderHook(() => useLiveMeetingNotes('chat-1'));
    expect(second.result.current.sessionId).toBe(sessionId);
  });

  it('drains finalized transcript lines through the service with a stable line id', async () => {
    const { result } = renderHook(() => useLiveMeetingNotes('chat-2'));
    act(() => {
      result.current.ingest('  hello world  ', 12);
    });
    await waitFor(() => expect(ingestLiveTranscript).toHaveBeenCalledTimes(1));
    const [sessionId, line] = ingestLiveTranscript.mock.calls[0] as [string, LiveTranscriptLine];
    expect(sessionId).toBe(result.current.sessionId);
    expect(line.text).toBe('hello world');
    expect(line.timestamp).toBe(12);
    expect(line.id).toEqual(expect.any(String));
    expect(line.id.length).toBeGreaterThan(0);
  });

  it('gives every queued line its own id so retries cannot collapse lines', async () => {
    const { result } = renderHook(() => useLiveMeetingNotes('chat-2b'));
    act(() => {
      result.current.ingest('first line');
      result.current.ingest('second line');
    });
    await waitFor(() => expect(ingestLiveTranscript).toHaveBeenCalledTimes(2));
    const ids = ingestLiveTranscript.mock.calls.map(
      ([, line]) => (line as LiveTranscriptLine).id,
    );
    expect(new Set(ids).size).toBe(2);
  });

  it('ignores blank transcript lines', () => {
    const { result } = renderHook(() => useLiveMeetingNotes('chat-3'));
    act(() => {
      result.current.ingest('   ');
    });
    expect(ingestLiveTranscript).not.toHaveBeenCalled();
  });
});
