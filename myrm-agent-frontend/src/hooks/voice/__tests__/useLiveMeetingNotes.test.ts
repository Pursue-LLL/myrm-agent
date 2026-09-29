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

  it('still works when sessionStorage is unavailable', async () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });
    try {
      const { result } = renderHook(() => useLiveMeetingNotes('chat-locked'));
      expect(result.current.sessionId).toMatch(/^live-/);
      act(() => {
        result.current.ingest('line while storage is blocked');
      });
      await waitFor(() => expect(ingestLiveTranscript).toHaveBeenCalledTimes(1));
    } finally {
      getItem.mockRestore();
      setItem.mockRestore();
    }
  });

  it('keeps a distinct session per key and per anonymous use', () => {
    const a = renderHook(() => useLiveMeetingNotes('chat-a'));
    const b = renderHook(() => useLiveMeetingNotes('chat-b'));
    const anonymous = renderHook(() => useLiveMeetingNotes());
    expect(a.result.current.sessionId).not.toBe(b.result.current.sessionId);
    expect(anonymous.result.current.sessionId).toMatch(/^live-/);
  });

  it('finalize publishes the snapshot and clears the stored key', async () => {
    const { result } = renderHook(() => useLiveMeetingNotes('chat-final'));
    const sessionId = result.current.sessionId;
    let resolved: unknown = null;
    await act(async () => {
      resolved = await result.current.finalize();
    });
    expect(finalizeLiveMeeting).toHaveBeenCalledWith(sessionId);
    expect(resolved).toEqual(EMPTY_SNAPSHOT);
    expect(window.sessionStorage.getItem('myrm-live-notes:chat-final')).toBeNull();
  });

  it('returns null and keeps working when finalize fails', async () => {
    finalizeLiveMeeting.mockRejectedValueOnce(new Error('network down'));
    const { result } = renderHook(() => useLiveMeetingNotes('chat-final-fail'));
    let resolved: unknown = 'unset';
    await act(async () => {
      resolved = await result.current.finalize();
    });
    expect(resolved).toBeNull();
    // The session is not torn down by a failed finalize.
    act(() => {
      result.current.ingest('after a failed finalize');
    });
    await waitFor(() => expect(ingestLiveTranscript).toHaveBeenCalledTimes(1));
  });

  it('never lets a failed ingest break the voice session', async () => {
    ingestLiveTranscript.mockRejectedValueOnce(new Error('500'));
    const { result } = renderHook(() => useLiveMeetingNotes('chat-ingest-fail'));
    act(() => {
      result.current.ingest('first');
      result.current.ingest('second');
    });
    // The queue keeps draining after the failure instead of stalling on it.
    await waitFor(() => expect(ingestLiveTranscript).toHaveBeenCalledTimes(2));
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
