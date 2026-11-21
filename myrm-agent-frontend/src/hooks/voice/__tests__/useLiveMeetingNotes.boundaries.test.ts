import { act, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { ApiError } from '@/lib/api';
import {
  ingestLiveTranscript,
  finalizeLiveMeeting,
  toastSuccess,
  toastWarning,
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

describe('useLiveMeetingNotes boundaries', () => {
  beforeEach(resetLiveNotesKit);

  describe('when the minutes cannot be published', () => {
    it('keeps the board, says so, and offers a retry that publishes the same meeting', async () => {
      ingestLiveTranscript.mockResolvedValue(ROLLING_SNAPSHOT);
      finalizeLiveMeeting.mockRejectedValueOnce(new Error('network down'));
      const { result, rerender } = renderLive({ active: true });
      act(() => {
        result.current.ingest('line');
      });
      await waitFor(() => expect(result.current.snapshot).toEqual(ROLLING_SNAPSHOT));

      rerender({ active: false });

      await waitFor(() => expect(toastError).toHaveBeenCalledOnce());
      expect(result.current.snapshot).toEqual(ROLLING_SNAPSHOT);
      expect(toastSuccess).not.toHaveBeenCalled();
      const [message, options] = toastError.mock.calls[0] as [
        string,
        { action: { label: string; onClick: () => void } },
      ];
      expect(message).toBe('saveFailed');
      expect(options.action.label).toBe('retry');

      act(() => options.action.onClick());

      await waitFor(() => expect(toastSuccess).toHaveBeenCalledOnce());
      expect(finalizeLiveMeeting).toHaveBeenCalledTimes(2);
      expect(finalizeLiveMeeting.mock.calls[1]).toEqual(finalizeLiveMeeting.mock.calls[0]);
    });

    it('tries again at the next stop when the user starts talking instead of retrying', async () => {
      finalizeLiveMeeting.mockRejectedValueOnce(new Error('network down'));
      const { result, rerender } = renderLive({ active: true });
      act(() => {
        result.current.ingest('first meeting');
      });
      rerender({ active: false });
      await waitFor(() => expect(toastError).toHaveBeenCalledOnce());

      rerender({ active: true });
      act(() => {
        result.current.ingest('second meeting');
      });
      await waitFor(() => expect(ingestLiveTranscript).toHaveBeenCalledTimes(2));
      rerender({ active: false });

      await waitFor(() => expect(toastSuccess).toHaveBeenCalledOnce());
      expect(finalizeLiveMeeting).toHaveBeenCalledTimes(2);
    });

    it('cannot confirm the save, and offers no retry, for a meeting the server no longer holds', async () => {
      finalizeLiveMeeting.mockRejectedValueOnce(new ApiError('Live meeting session not found', 404));
      const { result, rerender } = renderLive({ active: true });
      act(() => {
        result.current.ingest('line');
      });

      rerender({ active: false });
      await waitFor(() => expect(toastWarning).toHaveBeenCalledOnce());
      rerender({ active: true });
      rerender({ active: false });
      await settle();

      expect(toastWarning).toHaveBeenCalledExactlyOnceWith('sessionGone');
      expect(toastError).not.toHaveBeenCalled();
      expect(toastSuccess).not.toHaveBeenCalled();
      expect(finalizeLiveMeeting).toHaveBeenCalledOnce();
    });

    it('does not claim success for minutes that were not written to the knowledge base', async () => {
      finalizeLiveMeeting.mockResolvedValueOnce(EMPTY_SNAPSHOT);
      const { result, rerender } = renderLive({ active: true });
      act(() => {
        result.current.ingest('line');
      });

      rerender({ active: false });

      await waitFor(() => expect(toastError).toHaveBeenCalledExactlyOnceWith('saveFailed'));
      expect(toastSuccess).not.toHaveBeenCalled();
    });
  });

  describe('lines around the end of a meeting', () => {
    it('drops a late line of a meeting that was already published, so it cannot resurface in the next one', async () => {
      const { result, rerender } = renderLive({ active: true });
      act(() => {
        result.current.ingest('line');
      });
      rerender({ active: false });
      await waitFor(() => expect(toastSuccess).toHaveBeenCalledOnce());

      act(() => {
        result.current.ingest('straggler');
      });
      await settle();
      expect(sentTexts()).toEqual(['line']);

      rerender({ active: true });
      act(() => {
        result.current.ingest('next meeting');
      });
      await waitFor(() => expect(sentTexts()).toEqual(['line', 'next meeting']));
    });

    it('drops a late line of a meeting that had none, so it cannot open a session no minutes will cover', async () => {
      const { result, rerender } = renderLive({ active: true });
      rerender({ active: false });
      await settle();

      act(() => {
        result.current.ingest('straggler');
      });
      await settle();
      expect(sentTexts()).toEqual([]);

      rerender({ active: true });
      act(() => {
        result.current.ingest('next meeting');
      });
      await waitFor(() => expect(sentTexts()).toEqual(['next meeting']));
    });

    it('takes lines again, and publishes them, when the next voice session starts', async () => {
      const { result, rerender } = renderLive({ active: true });
      act(() => {
        result.current.ingest('first meeting');
      });
      rerender({ active: false });
      await waitFor(() => expect(toastSuccess).toHaveBeenCalledOnce());

      rerender({ active: true });
      act(() => {
        result.current.ingest('second meeting');
      });
      await waitFor(() => expect(sentTexts()).toEqual(['first meeting', 'second meeting']));
      rerender({ active: false });

      await waitFor(() => expect(finalizeLiveMeeting).toHaveBeenCalledTimes(2));
    });

    it('holds back the lines of a meeting that starts while the previous minutes are being published', async () => {
      const publishing = deferred<typeof PUBLISHED_SNAPSHOT>();
      finalizeLiveMeeting.mockReturnValueOnce(publishing.promise);
      const { result, rerender } = renderLive({ active: true });
      act(() => {
        result.current.ingest('old meeting');
      });
      await waitFor(() => expect(sentTexts()).toEqual(['old meeting']));
      rerender({ active: false });
      await waitFor(() => expect(finalizeLiveMeeting).toHaveBeenCalledOnce());

      rerender({ active: true });
      act(() => {
        result.current.ingest('new meeting');
      });
      await settle();
      // The server is still closing the old meeting: a line sent now would be lost with it.
      expect(sentTexts()).toEqual(['old meeting']);

      await act(async () => {
        publishing.resolve(PUBLISHED_SNAPSHOT);
      });
      await waitFor(() => expect(sentTexts()).toEqual(['old meeting', 'new meeting']));
      rerender({ active: false });

      await waitFor(() => expect(finalizeLiveMeeting).toHaveBeenCalledTimes(2));
    });

    it('publishes the newer meeting too when it ended while the previous minutes were being published', async () => {
      const publishing = deferred<typeof PUBLISHED_SNAPSHOT>();
      finalizeLiveMeeting.mockReturnValueOnce(publishing.promise);
      const { result, rerender } = renderLive({ active: true });
      act(() => {
        result.current.ingest('old meeting');
      });
      await waitFor(() => expect(sentTexts()).toEqual(['old meeting']));
      rerender({ active: false });
      await waitFor(() => expect(finalizeLiveMeeting).toHaveBeenCalledOnce());
      rerender({ active: true });
      act(() => {
        result.current.ingest('short meeting');
      });
      rerender({ active: false });
      await settle();
      expect(finalizeLiveMeeting).toHaveBeenCalledOnce();

      await act(async () => {
        publishing.resolve(PUBLISHED_SNAPSHOT);
      });

      await waitFor(() => expect(finalizeLiveMeeting).toHaveBeenCalledTimes(2));
      expect(sentTexts()).toEqual(['old meeting', 'short meeting']);
      expect(toastSuccess).toHaveBeenCalledTimes(2);
    });
  });
});
