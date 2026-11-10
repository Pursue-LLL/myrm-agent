import { describe, expect, it, vi } from 'vitest';
import { act } from '@testing-library/react';
import {
  broadcastFromOtherTab,
  FakeEventSource,
  installGlobalEventsLifecycle,
  LEADER_KEY,
  lastChannel,
  lastSource,
  mocks,
  mountGlobalEvents,
  recordWindowEvents,
} from './globalEventsTestKit';

const STREAM_URL = 'http://test.local/notifications/stream';
const HEARTBEAT_INTERVAL_MS = 3_000;
const HEARTBEAT_TIMEOUT_MS = 6_000;
const CRON_FRAME = { type: 'cron_updated', data: { job: 'j' }, timestamp: 't' };

function ownTabId(): string {
  return localStorage.getItem(LEADER_KEY) ?? '';
}

function posted(kind: string): unknown[] {
  return lastChannel()
    .postMessage.mock.calls.map(([message]) => message as { kind: string })
    .filter((message) => message.kind === kind);
}

/** Fails the open stream and returns how many streams existed right before the reconnect timer is armed. */
function failStream(): number {
  act(() => lastSource().onerror?.());
  return FakeEventSource.instances.length;
}

describe('useGlobalEvents: transport and leader election', () => {
  installGlobalEventsLifecycle();

  describe('claiming leadership', () => {
    it('takes the lead when nobody holds it: opens the stream, announces the claim and sends heartbeats', async () => {
      mountGlobalEvents();

      expect(FakeEventSource.instances.map((source) => source.url)).toEqual([STREAM_URL]);
      expect(lastChannel().name).toBe('myrm-sse-events');
      const tabId = ownTabId();
      expect(tabId).not.toBe('');
      expect(posted('leader-claim')).toEqual([{ kind: 'leader-claim', tabId }]);

      await vi.advanceTimersByTimeAsync(HEARTBEAT_INTERVAL_MS - 1);
      expect(posted('heartbeat')).toHaveLength(0);
      await vi.advanceTimersByTimeAsync(1);
      expect(posted('heartbeat')).toEqual([{ kind: 'heartbeat', tabId }]);
      await vi.advanceTimersByTimeAsync(HEARTBEAT_INTERVAL_MS);
      expect(posted('heartbeat')).toHaveLength(2);
    });

    it('waits out a foreign claim for the heartbeat timeout, then takes over', async () => {
      localStorage.setItem(LEADER_KEY, 'other-tab');
      mountGlobalEvents();

      expect(FakeEventSource.instances).toHaveLength(0);
      expect(posted('leader-claim')).toHaveLength(1);
      await vi.advanceTimersByTimeAsync(HEARTBEAT_TIMEOUT_MS - 1);
      expect(FakeEventSource.instances).toHaveLength(0);

      await vi.advanceTimersByTimeAsync(1);
      expect(FakeEventSource.instances).toHaveLength(1);
      expect(ownTabId()).not.toBe('other-tab');
    });

    it('stays a follower while the leader keeps sending heartbeats', async () => {
      localStorage.setItem(LEADER_KEY, 'other-tab');
      mountGlobalEvents();

      for (let beat = 0; beat < 4; beat += 1) {
        await vi.advanceTimersByTimeAsync(HEARTBEAT_TIMEOUT_MS - 1);
        broadcastFromOtherTab({ kind: 'heartbeat', tabId: 'other-tab' });
      }
      expect(FakeEventSource.instances).toHaveLength(0);

      await vi.advanceTimersByTimeAsync(HEARTBEAT_TIMEOUT_MS);
      expect(FakeEventSource.instances).toHaveLength(1);
    });
  });

  describe('stepping down', () => {
    it.each(['heartbeat', 'leader-claim'])(
      'a leader yields to the %s of another tab, then takes over again after silence',
      async (kind) => {
        const { source } = mountGlobalEvents();

        broadcastFromOtherTab({ kind, tabId: 'other-tab' });

        expect(source.close).toHaveBeenCalledTimes(1);
        await vi.advanceTimersByTimeAsync(HEARTBEAT_TIMEOUT_MS - 1);
        expect(posted('heartbeat')).toHaveLength(0);
        expect(FakeEventSource.instances).toHaveLength(1);

        await vi.advanceTimersByTimeAsync(1);
        expect(FakeEventSource.instances).toHaveLength(2);
      },
    );

    it('ignores the echo of its own heartbeat and claim', () => {
      const { source } = mountGlobalEvents();
      const tabId = ownTabId();

      broadcastFromOtherTab({ kind: 'heartbeat', tabId });
      broadcastFromOtherTab({ kind: 'leader-claim', tabId });

      expect(source.close).not.toHaveBeenCalled();
    });
  });

  describe('stream', () => {
    it('announces a resync on connect and refreshes the open chat transcript', async () => {
      mocks.chat.chatId = 'c1';
      const { source } = mountGlobalEvents();
      const events = recordWindowEvents();

      await act(async () => {
        await source.onopen?.();
      });

      expect(events()).toEqual([{ type: 'app_resync_required', detail: null }]);
      expect(posted('resync-pulse')).toHaveLength(1);
      expect(mocks.refreshOpenChatTranscript).toHaveBeenCalledWith('c1');
    });

    it('leaves the transcript alone when no chat is open', async () => {
      const { source } = mountGlobalEvents();

      await act(async () => {
        await source.onopen?.();
      });

      expect(mocks.refreshOpenChatTranscript).not.toHaveBeenCalled();
    });

    it('runs one transcript refresh at a time', async () => {
      mocks.chat.chatId = 'c1';
      let finishRefresh: () => void = () => {};
      mocks.refreshOpenChatTranscript.mockReturnValueOnce(
        new Promise<void>((resolve) => {
          finishRefresh = resolve;
        }),
      );
      const { source } = mountGlobalEvents();

      await act(async () => {
        void source.onopen?.();
        void source.onopen?.();
        await vi.dynamicImportSettled();
      });
      expect(mocks.refreshOpenChatTranscript).toHaveBeenCalledTimes(1);

      await act(async () => {
        finishRefresh();
        await vi.dynamicImportSettled();
      });
      await act(async () => {
        await source.onopen?.();
      });
      expect(mocks.refreshOpenChatTranscript).toHaveBeenCalledTimes(2);
    });

    it('relays each frame to the other tabs before handling it and drops malformed frames', () => {
      const { source } = mountGlobalEvents();
      const events = recordWindowEvents();

      act(() => source.onmessage?.({ data: JSON.stringify(CRON_FRAME) } as MessageEvent<string>));
      act(() => source.onmessage?.({ data: '{broken' } as MessageEvent<string>));

      expect(posted('sse-event')).toEqual([{ kind: 'sse-event', payload: CRON_FRAME }]);
      expect(events()).toEqual([{ type: 'cron_updated', detail: { job: 'j' } }]);
    });

    it('reconnects with exponential backoff capped at 30 seconds and starts over after an open', async () => {
      const { source } = mountGlobalEvents();

      for (const delayMs of [1_000, 2_000, 4_000, 8_000, 16_000, 30_000, 30_000]) {
        const failing = lastSource();
        const before = failStream();
        expect(failing.close).toHaveBeenCalledTimes(1);
        await vi.advanceTimersByTimeAsync(delayMs - 1);
        expect(FakeEventSource.instances).toHaveLength(before);
        await vi.advanceTimersByTimeAsync(1);
        expect(FakeEventSource.instances).toHaveLength(before + 1);
      }
      expect(source.close).toHaveBeenCalledTimes(1);

      await act(async () => {
        await lastSource().onopen?.();
      });
      const before = failStream();
      await vi.advanceTimersByTimeAsync(999);
      expect(FakeEventSource.instances).toHaveLength(before);
      await vi.advanceTimersByTimeAsync(1);
      expect(FakeEventSource.instances).toHaveLength(before + 1);
    });

    it('does not reconnect a stream that failed after the tab stepped down', async () => {
      const { source } = mountGlobalEvents();

      broadcastFromOtherTab({ kind: 'heartbeat', tabId: 'other-tab' });
      act(() => source.onerror?.());
      await vi.advanceTimersByTimeAsync(HEARTBEAT_TIMEOUT_MS - 1);

      expect(FakeEventSource.instances).toHaveLength(1);
    });
  });

  describe('follower', () => {
    it('handles the events the leader relays and pulses a resync without opening a stream', () => {
      localStorage.setItem(LEADER_KEY, 'other-tab');
      mountGlobalEvents();
      const events = recordWindowEvents();

      broadcastFromOtherTab({ kind: 'sse-event', payload: CRON_FRAME });
      broadcastFromOtherTab({ kind: 'resync-pulse' });

      expect(events()).toEqual([
        { type: 'cron_updated', detail: { job: 'j' } },
        { type: 'app_resync_required', detail: null },
      ]);
      expect(FakeEventSource.instances).toHaveLength(0);
    });

    it('shows toasts but leaves system notifications to the leader', () => {
      localStorage.setItem(LEADER_KEY, 'other-tab');
      mountGlobalEvents();

      broadcastFromOtherTab({
        kind: 'sse-event',
        payload: { type: 'health_alert', data: { component: 'db', status: 'fail', message: 'down' }, timestamp: 't' },
      });

      expect(mocks.toast.error).toHaveBeenCalledTimes(1);
      expect(mocks.notify).not.toHaveBeenCalled();
    });

    it('a leader ignores broadcast events and pulses: it saw them on its own stream', () => {
      mountGlobalEvents();
      const events = recordWindowEvents();

      broadcastFromOtherTab({ kind: 'sse-event', payload: CRON_FRAME });
      broadcastFromOtherTab({ kind: 'resync-pulse' });

      expect(events()).toEqual([]);
    });
  });

  describe('cleanup', () => {
    it('the leader closes the stream and the channel, stops its timers and gives the claim back', async () => {
      const { source, unmount } = mountGlobalEvents();
      const channel = lastChannel();

      unmount();

      expect(source.close).toHaveBeenCalled();
      expect(channel.close).toHaveBeenCalled();
      expect(localStorage.getItem(LEADER_KEY)).toBeNull();
      await vi.advanceTimersByTimeAsync(HEARTBEAT_TIMEOUT_MS * 2);
      expect(posted('heartbeat')).toHaveLength(0);
      expect(FakeEventSource.instances).toHaveLength(1);
    });

    it('a follower leaves the claim of another tab alone and never takes over afterwards', async () => {
      localStorage.setItem(LEADER_KEY, 'other-tab');
      const { unmount } = mountGlobalEvents();

      unmount();
      await vi.advanceTimersByTimeAsync(HEARTBEAT_TIMEOUT_MS * 2);

      expect(localStorage.getItem(LEADER_KEY)).toBe('other-tab');
      expect(FakeEventSource.instances).toHaveLength(0);
    });

    it('never takes the lead after unmount, even when the claim it was waiting on vanished', async () => {
      localStorage.setItem(LEADER_KEY, 'other-tab');
      const { unmount } = mountGlobalEvents();
      localStorage.removeItem(LEADER_KEY);

      unmount();
      await vi.advanceTimersByTimeAsync(HEARTBEAT_TIMEOUT_MS * 2);

      expect(FakeEventSource.instances).toHaveLength(0);
      expect(localStorage.getItem(LEADER_KEY)).toBeNull();
      expect(posted('heartbeat')).toHaveLength(0);
    });

    it('does not erase a claim another tab took over in the meantime', () => {
      const { unmount } = mountGlobalEvents();
      localStorage.setItem(LEADER_KEY, 'usurper');

      unmount();

      expect(localStorage.getItem(LEADER_KEY)).toBe('usurper');
    });

    it('takes the lead again at once when a dependency change restarts the effect', () => {
      const { rerender } = mountGlobalEvents();
      const firstStream = lastSource();
      mocks.config.enableWebNotifications = false;

      rerender();

      expect(firstStream.close).toHaveBeenCalled();
      expect(FakeEventSource.instances).toHaveLength(2);
    });
  });
});
