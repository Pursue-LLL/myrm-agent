import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { makeMessages, openChat, probes, setUpChatTest, tearDownChatTest, type BrowserStubs } from './chatMocks';
import Chat from '../Chat';
import { useUserQuestionNavStore } from '../question-nav';
import type { ScrollFollowMirrorEntry } from '@/hooks/ui/useScrollPositionRestore';
import type { TurnOutlineItem } from '@/services/chat';
import { useRewindStore } from '@/store/chat/useRewindStore';
import useChatStore from '@/store/useChatStore';
import { useFeatureGateStore } from '@/store/useFeatureGateStore';

type ListMode = 'plain' | 'virtual';

/** Both sides of the 20-message threshold; each count ends with an assistant message, so a streamed answer is visible. */
const MODES: [ListMode, number][] = [
  ['plain', 4],
  ['virtual', 26],
];

interface ChatProps {
  loading?: boolean;
}

function renderChat(initial: ChatProps = {}) {
  const ui = ({ loading = false }: ChatProps) => <Chat loading={loading} messageAppeared={false} />;
  const view = render(ui(initial));
  return { ...view, update: (props: ChatProps) => view.rerender(ui(props)) };
}

const outline = (turnIndex: number, userMessageId: string): TurnOutlineItem => ({
  turn_index: turnIndex,
  user_message_id: userMessageId,
  assistant_message_id: null,
  prompt_preview: `prompt ${turnIndex}`,
  reply_preview: null,
  created_at: null,
  message_count: 2,
});
const click = (label: string) => fireEvent.click(screen.getByText(label));
const readerAwayFromBottom: ScrollFollowMirrorEntry = {
  position: 300,
  isFollowingBottom: false,
  isUserScrolledUp: true,
  timestamp: 1,
};

describe.each(MODES)('Chat shell around the %s list', (mode, count) => {
  let browser: BrowserStubs;

  beforeEach(() => {
    browser = setUpChatTest();
  });

  afterEach(() => {
    tearDownChatTest();
  });

  /** The message at `index` was brought into view: by the virtual list, or by scrolling its element to the top. */
  function expectScrolledTo(index: number) {
    if (mode === 'virtual') {
      expect(probes.virtual.scrollToIndex).toHaveBeenLastCalledWith(index);
    } else {
      expect(browser.scrolled).toContainEqual({
        id: `m${index + 1}`,
        options: { behavior: 'smooth', block: 'start' },
      });
    }
  }

  describe('overlays', () => {
    it('shows a provider configuration error and clears it on close', () => {
      probes.configError.value = { error_type: 'invalid_api_key' };
      openChat('chat-1', makeMessages(count));
      renderChat();

      expect(screen.getByTestId('config-error')).toHaveAttribute('data-error', 'invalid_api_key');
      click('close config error');
      expect(probes.clearConfigError).toHaveBeenCalledTimes(1);
    });

    it('opens the session analytics dialog only for an active id and resets both ids on close', () => {
      openChat('chat-1', makeMessages(count));
      renderChat();
      expect(screen.queryByTestId('analytics')).toBeNull();

      act(() => useChatStore.setState({ activeSessionAnalyticsId: 'chat-1', activeSessionAnalyticsMessageId: 'm2' }));
      expect(screen.getByTestId('analytics')).toHaveAttribute('data-session', 'chat-1');

      click('close analytics');
      expect(useChatStore.getState().activeSessionAnalyticsId).toBeNull();
      expect(useChatStore.getState().activeSessionAnalyticsMessageId).toBeNull();
      expect(screen.queryByTestId('analytics')).toBeNull();
    });

    it('opens the rewind dialog for the active target and closes it when asked to close', () => {
      openChat('chat-1', makeMessages(count));
      renderChat();
      expect(screen.queryByTestId('rewind')).toBeNull();

      act(() => useRewindStore.getState().openRewind({ chatId: 'chat-1', messageId: 'm2', messageIndex: 1 }));
      expect(screen.getByTestId('rewind')).toHaveAttribute('data-message', 'm2');
      expect(screen.getByTestId('rewind')).toHaveAttribute('data-index', '1');

      click('keep rewind');
      expect(useRewindStore.getState().target).not.toBeNull();

      click('close rewind');
      expect(useRewindStore.getState().target).toBeNull();
      expect(screen.queryByTestId('rewind')).toBeNull();
    });

    it('shows the goal panel only when goals are enabled', () => {
      openChat('chat-1', makeMessages(count));
      const first = renderChat();
      expect(screen.queryByTestId('goal-control-plane')).toBeNull();
      expect(screen.getByTestId('turn-rail')).toHaveAttribute('data-goal', 'false');
      first.unmount();

      act(() => useFeatureGateStore.setState({ enabledFeatures: new Set(['goals_system']) }));
      renderChat();
      expect(screen.getByTestId('goal-control-plane')).toBeInTheDocument();
      expect(screen.getByTestId('turn-rail')).toHaveAttribute('data-goal', 'true');
    });
  });

  describe('outline navigation', () => {
    it('gives the outline rail and the mobile outline the full list including the summary row', () => {
      openChat('chat-1', makeMessages(count), {
        compactedSummary: 'earlier turns, condensed',
        turnOutlines: [outline(0, 'm1'), outline(1, 'm3')],
      });
      renderChat({ loading: true });

      const rail = screen.getByTestId('turn-rail');
      expect(rail).toHaveAttribute('data-count', String(count + 1));
      expect(rail).toHaveAttribute('data-outlines', '2');
      expect(rail).toHaveAttribute('data-loading', 'true');
      expect(screen.getByTestId('mobile-outline')).toHaveAttribute('data-count', String(count + 1));
    });

    it('labels the mobile outline trigger', () => {
      openChat('chat-1', makeMessages(count));
      renderChat();

      expect(screen.getByRole('button', { name: 'ariaLabel' })).toBeInTheDocument();
    });

    it.each([
      ['outline rail', 'rail'],
      ['mobile outline', 'mobile'],
    ])('lets the %s jump by index, jump by id and load turns that are not in memory yet', (_name, prefix) => {
      const loadThroughTurn = vi.fn().mockResolvedValue(true);
      useChatStore.setState({ loadThroughTurn });
      openChat('chat-1', makeMessages(count));
      renderChat();

      click(`${prefix} jump index`);
      expectScrolledTo(1);

      probes.virtual.scrollToIndex.mockClear();
      browser.scrolled.length = 0;
      click(`${prefix} jump id`);
      expectScrolledTo(1);

      click(`${prefix} load turn`);
      expect(loadThroughTurn).toHaveBeenCalledExactlyOnceWith('m3');
    });

    it('lets the attention bar above the composer jump to a message by index', () => {
      openChat('chat-1', makeMessages(count));
      renderChat();

      click('attention jump');

      expectScrolledTo(1);
    });

    it('takes the message id, not the index, from the question navigator and its drawer', () => {
      openChat('chat-1', makeMessages(count));
      renderChat();

      click('question nav jump');
      expectScrolledTo(0);
      click('question drawer jump');
      expectScrolledTo(1);
    });
  });

  describe('scroll-to-bottom button', () => {
    it('shows for a reader who left the bottom with the unread count and the new-content mark', () => {
      useUserQuestionNavStore.setState({
        syncMessages: vi.fn(),
        pendingCount: 3,
        pendingItems: [{ messageId: 'm9', role: 'user', snippet: 'unread' }],
      });
      probes.scroll.snapshot.mockReturnValue(readerAwayFromBottom);
      openChat('chat-1', makeMessages(count));
      const { update } = renderChat();

      const button = screen.getByTestId('scroll-bottom');
      expect(button).toHaveAttribute('data-new', 'false');
      expect(button).toHaveAttribute('data-pending', '3');
      expect(button).toHaveAttribute('data-items', '1');

      update({ loading: true });
      expect(screen.getByTestId('scroll-bottom')).toHaveAttribute('data-new', 'true');
    });

    it('is absent for a reader at the bottom', () => {
      openChat('chat-1', makeMessages(count));
      renderChat();

      expect(screen.queryByTestId('scroll-bottom')).toBeNull();
    });

    it('takes the reader to the end of the list and goes away', () => {
      probes.scroll.snapshot.mockReturnValue(readerAwayFromBottom);
      openChat('chat-1', makeMessages(count));
      renderChat();
      browser.scrolled.length = 0;

      click('scroll to bottom');

      if (mode === 'virtual') {
        expect(probes.virtual.scrollToBottom).toHaveBeenCalledTimes(1);
      } else {
        expect(browser.scrolled).toEqual([{ id: 'end', options: { behavior: 'smooth', block: 'end' } }]);
      }
      expect(screen.queryByTestId('scroll-bottom')).toBeNull();
    });
  });
});
