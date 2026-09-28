import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

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

  it('drains finalized transcript lines through the service', async () => {
    const { result } = renderHook(() => useLiveMeetingNotes('chat-2'));
    act(() => {
      result.current.ingest('  hello world  ');
    });
    await waitFor(() =>
      expect(ingestLiveTranscript).toHaveBeenCalledWith(result.current.sessionId, 'hello world'),
    );
  });

  it('ignores blank transcript lines', () => {
    const { result } = renderHook(() => useLiveMeetingNotes('chat-3'));
    act(() => {
      result.current.ingest('   ');
    });
    expect(ingestLiveTranscript).not.toHaveBeenCalled();
  });
});
