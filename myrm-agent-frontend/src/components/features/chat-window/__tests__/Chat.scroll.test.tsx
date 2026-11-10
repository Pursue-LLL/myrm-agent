import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  makeMessages,
  openChat,
  probes,
  scrollWindowTo,
  setUpChatTest,
  tearDownChatTest,
  type BrowserStubs,
} from './chatMocks';
import Chat from '../Chat';
import type { ScrollFollowMirrorEntry } from '@/hooks/ui/useScrollPositionRestore';
import { expectNonNull } from '@/test-utils/expectDefined';
import useChatStore from '@/store/useChatStore';

interface ChatProps {
  loading?: boolean;
  messageAppeared?: boolean;
}

function renderChat(initial: ChatProps = {}) {
  const ui = ({ loading = false, messageAppeared = false }: ChatProps) => (
    <Chat loading={loading} messageAppeared={messageAppeared} />
  );
  const view = render(ui(initial));
  return { ...view, update: (props: ChatProps) => view.rerender(ui(props)) };
}

const dock = (container: HTMLElement) => container.querySelector('[data-composer-dock]');
const scrollUp = () => {
  act(() => scrollWindowTo(500));
  act(() => scrollWindowTo(400));
};
const advance = (ms: number) => act(() => void vi.advanceTimersByTime(ms));
const click = (label: string) => fireEvent.click(screen.getByText(label));
const readerAwayFromBottom: ScrollFollowMirrorEntry = {
  position: 300,
  isFollowingBottom: false,
  isUserScrolledUp: true,
  timestamp: 1,
};
const readerAtBottom: ScrollFollowMirrorEntry = {
  ...readerAwayFromBottom,
  isFollowingBottom: true,
  isUserScrolledUp: false,
};

describe('Chat scrolling', () => {
  let browser: BrowserStubs;

  beforeEach(() => {
    browser = setUpChatTest();
  });

  afterEach(() => {
    tearDownChatTest();
  });

  describe('window scroll', () => {
    it('offers the jump to bottom and hides the composer when the user scrolls up, then brings the composer back after a pause', () => {
      openChat('chat-1', makeMessages(4));
      const { container } = renderChat();
      expect(screen.queryByTestId('scroll-bottom')).toBeNull();

      scrollUp();
      expect(screen.getByTestId('scroll-bottom')).toBeInTheDocument();
      expect(probes.scroll.userScrolled?.current).toBe(true);
      expect(dock(container)?.className).toContain('opacity-0');

      advance(1499);
      expect(dock(container)?.className).toContain('opacity-0');
      advance(1);
      expect(dock(container)?.className).toContain('opacity-100');
      expect(screen.getByTestId('scroll-bottom')).toBeInTheDocument();
    });

    it('ignores an upward scroll of 5px or less and reacts from 6px', () => {
      openChat('chat-1', makeMessages(4));
      const { container } = renderChat();
      act(() => scrollWindowTo(500));

      act(() => scrollWindowTo(495));
      expect(screen.queryByTestId('scroll-bottom')).toBeNull();
      expect(dock(container)?.className).toContain('opacity-100');

      act(() => scrollWindowTo(489));
      expect(screen.getByTestId('scroll-bottom')).toBeInTheDocument();
    });

    it('returns to following the bottom when scrolling down by more than 5px near the bottom', () => {
      openChat('chat-1', makeMessages(4));
      const { container } = renderChat();
      scrollUp();

      probes.nearBottom.value = true;
      act(() => scrollWindowTo(406));

      expect(screen.queryByTestId('scroll-bottom')).toBeNull();
      expect(probes.scroll.userScrolled?.current).toBe(false);
      expect(dock(container)?.className).toContain('opacity-100');
    });

    it('stays scrolled up when scrolling down away from the bottom or by 5px or less', () => {
      openChat('chat-1', makeMessages(4));
      renderChat();
      scrollUp();

      probes.nearBottom.value = false;
      act(() => scrollWindowTo(450));
      expect(screen.getByTestId('scroll-bottom')).toBeInTheDocument();

      probes.nearBottom.value = true;
      act(() => scrollWindowTo(455));
      expect(screen.getByTestId('scroll-bottom')).toBeInTheDocument();
      expect(probes.scroll.userScrolled?.current).toBe(true);
    });

    it('clears the new-message mark once the user is back at the bottom', () => {
      probes.scroll.snapshot.mockReturnValue(readerAwayFromBottom);
      openChat('chat-1', makeMessages(2));
      const { update } = renderChat();
      update({ loading: true });
      expect(screen.getByTestId('scroll-bottom')).toHaveAttribute('data-new', 'true');

      act(() => scrollWindowTo(100));
      probes.nearBottom.value = true;
      act(() => scrollWindowTo(200));
      expect(screen.queryByTestId('scroll-bottom')).toBeNull();

      probes.nearBottom.value = false;
      scrollUp();
      expect(screen.getByTestId('scroll-bottom')).toHaveAttribute('data-new', 'false');
    });

    it('saves the position 200ms after the last scroll, once per burst', () => {
      openChat('chat-1', makeMessages(4));
      renderChat();

      act(() => scrollWindowTo(500));
      advance(150);
      act(() => scrollWindowTo(520));
      advance(199);
      expect(probes.scroll.save).not.toHaveBeenCalled();
      advance(1);
      expect(probes.scroll.save).toHaveBeenCalledTimes(1);
      expect(probes.scroll.save).toHaveBeenCalledWith();
    });

    it('stops listening and drops pending saves once unmounted', () => {
      openChat('chat-1', makeMessages(4));
      const { unmount } = renderChat();
      act(() => scrollWindowTo(500));

      unmount();
      advance(2000);
      act(() => scrollWindowTo(100));
      advance(2000);

      expect(probes.scroll.save).not.toHaveBeenCalled();
    });
  });

  describe('jump to bottom', () => {
    it('scrolls the plain list to its end, resumes following and puts the composer back', () => {
      openChat('chat-1', makeMessages(4));
      const { container } = renderChat();
      scrollUp();
      expect(dock(container)?.className).toContain('opacity-0');
      const following = probes.scroll.followingBottom;
      expectNonNull(following, 'following-bottom ref');
      following.current = false;
      browser.scrolled.length = 0;

      click('scroll to bottom');

      expect(browser.scrolled).toEqual([{ id: 'end', options: { behavior: 'smooth', block: 'end' } }]);
      expect(probes.scroll.save).toHaveBeenCalledWith({ isFollowingBottom: true, isUserScrolledUp: false });
      expect(probes.scroll.userScrolled?.current).toBe(false);
      expect(probes.scroll.followingBottom?.current).toBe(true);
      expect(screen.queryByTestId('scroll-bottom')).toBeNull();
      expect(dock(container)?.className).toContain('opacity-100');
    });

    it('asks the virtual list to scroll to its end instead', () => {
      openChat('chat-1', makeMessages(25));
      renderChat();
      click('virtual scrolled up');
      expect(screen.getByTestId('scroll-bottom')).toBeInTheDocument();

      click('scroll to bottom');

      expect(probes.virtual.scrollToBottom).toHaveBeenCalledTimes(1);
      expect(screen.queryByTestId('scroll-bottom')).toBeNull();
      expect(browser.scrolled).toEqual([]);
      expect(probes.scroll.save).not.toHaveBeenCalled();
    });

    it('clears the new-content mark when the button takes the reader to the end of the virtual list', () => {
      probes.scroll.snapshot.mockReturnValue(readerAwayFromBottom);
      openChat('chat-1', makeMessages(26));
      const { update } = renderChat();
      update({ loading: true });
      expect(screen.getByTestId('scroll-bottom')).toHaveAttribute('data-new', 'true');

      click('scroll to bottom');
      click('virtual scrolled up');

      expect(screen.getByTestId('scroll-bottom')).toHaveAttribute('data-new', 'false');
    });

    it('follows the virtual list when it reports the user left or returned to the bottom', () => {
      openChat('chat-1', makeMessages(25));
      renderChat();

      click('virtual scrolled up');
      expect(screen.getByTestId('scroll-bottom')).toBeInTheDocument();
      click('virtual at bottom');
      expect(screen.queryByTestId('scroll-bottom')).toBeNull();
    });
  });

  describe('following a streaming answer', () => {
    it('keeps the end of the plain list in view while the assistant is writing', () => {
      openChat('chat-1', makeMessages(2));
      renderChat({ loading: true });

      expect(browser.scrolled).toEqual([{ id: 'end', options: { behavior: 'smooth', block: 'end' } }]);
    });

    it('does not scroll for a finished assistant message', () => {
      openChat('chat-1', makeMessages(2));
      renderChat({ loading: false });

      expect(browser.scrolled).toEqual([]);
    });

    it('does not scroll the virtual list from here', () => {
      openChat('chat-1', makeMessages(26));
      renderChat({ loading: true });

      expect(browser.scrolled).toEqual([]);
    });

    it('marks new content instead of scrolling when the user has scrolled up', () => {
      probes.scroll.snapshot.mockReturnValue(readerAwayFromBottom);
      openChat('chat-1', makeMessages(2));
      renderChat({ loading: true });

      expect(browser.scrolled).toEqual([]);
      expect(screen.getByTestId('scroll-bottom')).toHaveAttribute('data-new', 'true');
    });

    it('pulls the view down when the user sends a message, even after scrolling up', () => {
      probes.scroll.snapshot.mockReturnValue(readerAwayFromBottom);
      openChat('chat-1', makeMessages(3));
      renderChat();

      expect(screen.queryByTestId('scroll-bottom')).toBeNull();
      expect(probes.scroll.userScrolled?.current).toBe(false);
      expect(browser.scrolled).toEqual([{ id: 'end', options: { behavior: 'smooth', block: 'end' } }]);
    });

    it('scrolls again each time the streamed content grows', () => {
      openChat('chat-1', makeMessages(2));
      renderChat({ loading: true });
      browser.scrolled.length = 0;

      act(() => {
        useChatStore.setState({
          messages: makeMessages(2).map((message) => ({ ...message, content: `${message.content}!` })),
        });
      });

      expect(browser.scrolled).toEqual([{ id: 'end', options: { behavior: 'smooth', block: 'end' } }]);
    });

    it('follows a growing page only while an answer is streaming and the user has not scrolled away', () => {
      openChat('chat-1', makeMessages(2));
      const { update } = renderChat({ loading: false });
      browser.scrolled.length = 0;

      browser.notifyResize(120);
      act(() => browser.flushFrames());
      expect(browser.scrolled).toEqual([]);

      update({ loading: true });
      browser.scrolled.length = 0;
      browser.notifyResize(0);
      act(() => browser.flushFrames());
      expect(browser.scrolled).toEqual([]);

      browser.notifyResize(120);
      expect(browser.scrolled).toEqual([]);
      act(() => browser.flushFrames());
      expect(browser.scrolled).toEqual([{ id: 'end', options: { behavior: 'smooth', block: 'end' } }]);

      browser.scrolled.length = 0;
      const reader = probes.scroll.userScrolled;
      expectNonNull(reader, 'user-scrolled ref');
      reader.current = true;
      browser.notifyResize(240);
      expect(browser.pendingFrames()).toBe(0);
      act(() => browser.flushFrames());
      expect(browser.scrolled).toEqual([]);
    });
  });

  describe('restoring the reading position', () => {
    it('opens scrolled up when the chat was left that way', () => {
      probes.scroll.snapshot.mockReturnValue(readerAwayFromBottom);
      openChat('chat-1', makeMessages(2));
      renderChat();

      expect(screen.getByTestId('scroll-bottom')).toBeInTheDocument();
      expect(probes.scroll.userScrolled?.current).toBe(true);
      expect(probes.scroll.followingBottom?.current).toBe(false);
    });

    it('opens following the bottom when nothing was saved', () => {
      openChat('chat-1', makeMessages(2));
      renderChat();

      expect(screen.queryByTestId('scroll-bottom')).toBeNull();
      expect(probes.scroll.userScrolled?.current).toBe(false);
      expect(probes.scroll.followingBottom?.current).toBe(true);
    });

    it('reads the saved position of the new chat when the conversation changes', () => {
      openChat('chat-1', makeMessages(2));
      renderChat();
      expect(screen.queryByTestId('scroll-bottom')).toBeNull();

      probes.scroll.snapshot.mockReturnValue(readerAwayFromBottom);
      act(() => openChat('chat-2', makeMessages(2, 'chat-2')));

      expect(screen.getByTestId('scroll-bottom')).toBeInTheDocument();
    });

    it('restores the saved position 100ms after there are messages', () => {
      openChat('chat-1', makeMessages(2));
      renderChat();

      advance(99);
      expect(probes.scroll.restore).not.toHaveBeenCalled();
      advance(1);
      expect(probes.scroll.restore).toHaveBeenCalledTimes(1);
    });

    it('has nothing to restore in an empty conversation or after unmounting', () => {
      openChat('chat-1', []);
      const empty = renderChat();
      advance(500);
      expect(probes.scroll.restore).not.toHaveBeenCalled();
      empty.unmount();

      openChat('chat-1', makeMessages(2));
      renderChat().unmount();
      advance(500);
      expect(probes.scroll.restore).not.toHaveBeenCalled();
    });

    it('forgets the new-content mark when the restored position is at the bottom', () => {
      probes.scroll.snapshot.mockReturnValue(readerAwayFromBottom);
      openChat('chat-1', makeMessages(2));
      renderChat({ loading: true });
      expect(screen.getByTestId('scroll-bottom')).toHaveAttribute('data-new', 'true');

      act(() => probes.scroll.onRestore?.(readerAtBottom));
      act(() => probes.scroll.onRestore?.(readerAwayFromBottom));

      expect(screen.getByTestId('scroll-bottom')).toHaveAttribute('data-new', 'false');
    });

    it('shows or hides the jump to bottom as the restored position says', () => {
      openChat('chat-1', makeMessages(2));
      renderChat();

      act(() => probes.scroll.onRestore?.(readerAwayFromBottom));
      expect(screen.getByTestId('scroll-bottom')).toBeInTheDocument();

      act(() => probes.scroll.onRestore?.(readerAtBottom));
      expect(screen.queryByTestId('scroll-bottom')).toBeNull();
    });
  });
});
