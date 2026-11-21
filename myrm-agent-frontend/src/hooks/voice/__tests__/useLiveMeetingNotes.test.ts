import { act, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { LiveTranscriptLine } from '@/services/liveMeeting';
import {
  ingestLiveTranscript,
  finalizeLiveMeeting,
  finalizeLiveMeetingOnPageExit,
  toastSuccess,
  toastError,
  EMPTY_SNAPSHOT,
  ROLLING_SNAPSHOT,
  PUBLISHED_SNAPSHOT,
  deferred,
  renderLive,
  sentTexts,
  settle,
  resetLiveNotesKit,
} from './liveNotesKit';

describe('useLiveMeetingNotes', () => {
  beforeEach(resetLiveNotesKit);

  describe('session id', () => {
    it('persists and resumes the session id for a stable key', () => {
      const first = renderLive({ sessionKey: 'chat-1' });
      const sessionId = first.result.current.sessionId;
      expect(window.sessionStorage.getItem('myrm-live-notes:chat-1')).toBe(sessionId);
      first.unmount();

      const second = renderLive({ sessionKey: 'chat-1' });
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
        const { result } = renderLive({ sessionKey: 'chat-locked' });
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
      const a = renderLive({ sessionKey: 'chat-a' });
      const b = renderLive({ sessionKey: 'chat-b' });
      const anonymous = renderLive();
      expect(a.result.current.sessionId).not.toBe(b.result.current.sessionId);
      expect(anonymous.result.current.sessionId).toMatch(/^live-/);
    });
  });

  describe('uploading lines', () => {
    it('never lets a failed ingest break the voice session', async () => {
      ingestLiveTranscript.mockRejectedValueOnce(new Error('500'));
      const { result } = renderLive({ sessionKey: 'chat-ingest-fail' });
      act(() => {
        result.current.ingest('first');
        result.current.ingest('second');
      });
      // The queue keeps draining after the failure instead of stalling on it.
      await waitFor(() => expect(ingestLiveTranscript).toHaveBeenCalledTimes(2));
    });

    it('sends a line queued during an in-flight request right after it, in order, and then accepts new lines', async () => {
      const first = deferred<typeof EMPTY_SNAPSHOT>();
      ingestLiveTranscript.mockReturnValueOnce(first.promise);
      const { result } = renderLive({ sessionKey: 'chat-queue' });

      act(() => {
        result.current.ingest('first');
      });
      act(() => {
        result.current.ingest('second');
      });
      // Single flight: the second line waits for the first request instead of racing it.
      expect(ingestLiveTranscript).toHaveBeenCalledTimes(1);

      await act(async () => {
        first.resolve(EMPTY_SNAPSHOT);
      });
      await waitFor(() => expect(ingestLiveTranscript).toHaveBeenCalledTimes(2));
      expect(sentTexts()).toEqual(['first', 'second']);

      // The drain released its guard once the queue was empty, so a later line is not stranded.
      act(() => {
        result.current.ingest('third');
      });
      await waitFor(() => expect(ingestLiveTranscript).toHaveBeenCalledTimes(3));
      expect(sentTexts()).toEqual(['first', 'second', 'third']);
    });

    it('drains finalized transcript lines through the service with a stable line id', async () => {
      const { result } = renderLive({ sessionKey: 'chat-2' });
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
      const { result } = renderLive({ sessionKey: 'chat-2b' });
      act(() => {
        result.current.ingest('first line');
        result.current.ingest('second line');
      });
      await waitFor(() => expect(ingestLiveTranscript).toHaveBeenCalledTimes(2));
      const ids = ingestLiveTranscript.mock.calls.map(([, line]) => (line as LiveTranscriptLine).id);
      expect(new Set(ids).size).toBe(2);
    });

    it('ignores blank transcript lines', () => {
      const { result } = renderLive({ sessionKey: 'chat-3' });
      act(() => {
        result.current.ingest('   ');
      });
      expect(ingestLiveTranscript).not.toHaveBeenCalled();
    });

    it('sends every line against the vault of the agent', async () => {
      const { result } = renderLive({ sessionKey: 'chat-scoped', agentId: 'agent-1' });
      act(() => {
        result.current.ingest('scoped line');
      });
      await waitFor(() => expect(ingestLiveTranscript).toHaveBeenCalledTimes(1));
      expect(ingestLiveTranscript).toHaveBeenCalledWith(
        result.current.sessionId,
        expect.objectContaining({ text: 'scoped line' }),
        'agent-1',
      );
    });
  });

  describe('publishing when the voice session ends', () => {
    it('publishes the minutes into the vault of the agent once the session stops, and clears the key and the board', async () => {
      ingestLiveTranscript.mockResolvedValue(ROLLING_SNAPSHOT);
      const { result, rerender } = renderLive({ sessionKey: 'chat-final', agentId: 'agent-1', active: true });
      act(() => {
        result.current.ingest('line');
      });
      await waitFor(() => expect(result.current.snapshot).toEqual(ROLLING_SNAPSHOT));
      expect(finalizeLiveMeeting).not.toHaveBeenCalled();

      rerender({ sessionKey: 'chat-final', agentId: 'agent-1', active: false });

      await waitFor(() => expect(result.current.snapshot).toBeNull());
      expect(finalizeLiveMeeting).toHaveBeenCalledExactlyOnceWith(result.current.sessionId, 'agent-1');
      expect(window.sessionStorage.getItem('myrm-live-notes:chat-final')).toBeNull();
    });

    it('tells the user where the minutes went, under the title of the meeting', async () => {
      const { result, rerender } = renderLive({ active: true });
      act(() => {
        result.current.ingest('line');
      });

      rerender({ active: false });

      await waitFor(() => expect(toastSuccess).toHaveBeenCalledOnce());
      expect(toastSuccess).toHaveBeenCalledWith('saved', { description: 'Standup' });
      expect(toastError).not.toHaveBeenCalled();
    });

    it('publishes nothing when no line was said while the voice session ran', async () => {
      const { rerender } = renderLive({ sessionKey: 'chat-silent', active: true });

      rerender({ sessionKey: 'chat-silent', active: false });
      await settle();

      expect(finalizeLiveMeeting).not.toHaveBeenCalled();
      expect(toastSuccess).not.toHaveBeenCalled();
      expect(toastError).not.toHaveBeenCalled();
    });

    it('sends the lines still in flight before it asks for the minutes', async () => {
      const lastLine = deferred<typeof EMPTY_SNAPSHOT>();
      ingestLiveTranscript.mockReturnValueOnce(lastLine.promise);
      const { result, rerender } = renderLive({ active: true });
      act(() => {
        result.current.ingest('the last words');
      });
      act(() => {
        result.current.ingest('queued behind them');
      });

      rerender({ active: false });
      await settle();
      expect(finalizeLiveMeeting).not.toHaveBeenCalled();

      await act(async () => {
        lastLine.resolve(EMPTY_SNAPSHOT);
      });
      await waitFor(() => expect(finalizeLiveMeeting).toHaveBeenCalledOnce());
      expect(sentTexts()).toEqual(['the last words', 'queued behind them']);
      expect(ingestLiveTranscript.mock.invocationCallOrder[1]).toBeLessThan(
        finalizeLiveMeeting.mock.invocationCallOrder[0],
      );
    });

    it('publishes once however many signals say the session is over', async () => {
      const { result, rerender, unmount } = renderLive({ active: true });
      act(() => {
        result.current.ingest('line');
      });

      rerender({ active: false });
      unmount();
      await waitFor(() => expect(toastSuccess).toHaveBeenCalledOnce());

      expect(finalizeLiveMeeting).toHaveBeenCalledOnce();
    });

    it('publishes a meeting whose page goes away while the session is still running', async () => {
      const { result, unmount } = renderLive({ active: true });
      act(() => {
        result.current.ingest('line');
      });

      unmount();

      await waitFor(() => expect(finalizeLiveMeeting).toHaveBeenCalledOnce());
    });

    it('sends the request on page exit, once, and leaves the answer unread', () => {
      const { result, unmount } = renderLive({ sessionKey: 'chat-exit', agentId: 'agent-1', active: true });
      act(() => {
        result.current.ingest('line');
      });

      window.dispatchEvent(new Event('pagehide'));
      window.dispatchEvent(new Event('pagehide'));
      unmount();

      expect(finalizeLiveMeetingOnPageExit).toHaveBeenCalledExactlyOnceWith(result.current.sessionId, 'agent-1');
      expect(finalizeLiveMeeting).not.toHaveBeenCalled();
    });

    it('sends nothing on page exit when nothing was said or a publish is already under way', async () => {
      const silent = renderLive({ active: true });
      window.dispatchEvent(new Event('pagehide'));
      expect(finalizeLiveMeetingOnPageExit).not.toHaveBeenCalled();
      silent.unmount();

      const publishing = deferred<typeof PUBLISHED_SNAPSHOT>();
      finalizeLiveMeeting.mockReturnValueOnce(publishing.promise);
      const talked = renderLive({ active: true });
      act(() => {
        talked.result.current.ingest('line');
      });
      talked.rerender({ active: false });
      await waitFor(() => expect(finalizeLiveMeeting).toHaveBeenCalledOnce());

      window.dispatchEvent(new Event('pagehide'));

      expect(finalizeLiveMeetingOnPageExit).not.toHaveBeenCalled();
      await act(async () => {
        publishing.resolve(PUBLISHED_SNAPSHOT);
      });
    });

    it('does not publish the same meeting again once it has been published', async () => {
      const { result, rerender, unmount } = renderLive({ active: true });
      act(() => {
        result.current.ingest('line');
      });
      rerender({ active: false });
      await waitFor(() => expect(toastSuccess).toHaveBeenCalledOnce());

      unmount();
      window.dispatchEvent(new Event('pagehide'));
      await settle();

      expect(finalizeLiveMeeting).toHaveBeenCalledOnce();
      expect(finalizeLiveMeetingOnPageExit).not.toHaveBeenCalled();
    });

    it('survives a blocked sessionStorage: a published meeting is not reported as failed', async () => {
      const { result, rerender } = renderLive({ sessionKey: 'chat-blocked', active: true });
      act(() => {
        result.current.ingest('line');
      });
      const removeItem = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
        throw new Error('denied');
      });
      try {
        rerender({ sessionKey: 'chat-blocked', active: false });
        await waitFor(() => expect(toastSuccess).toHaveBeenCalledOnce());
      } finally {
        removeItem.mockRestore();
      }
      expect(toastError).not.toHaveBeenCalled();
    });
  });
});
