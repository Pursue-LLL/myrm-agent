import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { makeMessages, openChat, probes, setUpChatTest, tearDownChatTest, type BrowserStubs } from './chatMocks';
import Chat from '../Chat';
import { useUserQuestionNavStore } from '../question-nav';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

interface ChatProps {
  loading?: boolean;
  messageAppeared?: boolean;
  messagesOverride?: Message[];
}

function renderChat(initial: ChatProps = {}) {
  const ui = ({ loading = false, messageAppeared = false, messagesOverride }: ChatProps) => (
    <Chat loading={loading} messageAppeared={messageAppeared} messagesOverride={messagesOverride} />
  );
  const view = render(ui(initial));
  return { ...view, update: (props: ChatProps) => view.rerender(ui(props)) };
}

const boxes = () => screen.getAllByTestId('message-box');
const dock = (container: HTMLElement) => container.querySelector('[data-composer-dock]');

describe('Chat rendering', () => {
  let browser: BrowserStubs;

  beforeEach(() => {
    browser = setUpChatTest();
  });

  afterEach(() => {
    tearDownChatTest();
  });

  describe('list mode', () => {
    it('lists a short conversation as message boxes and flags only the last one', () => {
      openChat('chat-1', makeMessages(3));
      renderChat({ loading: true });

      expect(
        boxes().map((box) => [box.dataset.message, box.dataset.index, box.dataset.last, box.dataset.loading]),
      ).toEqual([
        ['m1', '0', 'false', 'true'],
        ['m2', '1', 'false', 'true'],
        ['m3', '2', 'true', 'true'],
      ]);
      expect(screen.queryByTestId('virtual-list')).toBeNull();
      expect(screen.getByTestId('clearance-spacer')).toBeInTheDocument();
    });

    it('shows messages appended to the store in the same mounted list and composer', () => {
      openChat('chat-1', makeMessages(2));
      renderChat();
      expect(probes.messageInputMounts).toEqual(['chat-1']);

      act(() => useChatStore.setState({ messages: makeMessages(3) }));
      act(() => useChatStore.setState({ messages: makeMessages(4) }));

      expect(boxes().map((box) => box.dataset.message)).toEqual(['m1', 'm2', 'm3', 'm4']);
      expect(probes.messageInputMounts).toEqual(['chat-1']);
    });

    it('draws a rule under an assistant message unless it is the last one', () => {
      openChat('chat-1', makeMessages(4));
      const { container } = renderChat();

      // m2 is an assistant message followed by more; m4 is the last assistant message.
      expect(container.querySelectorAll('.h-px.w-full')).toHaveLength(1);
      expect(container.querySelector('[data-message-id="m2"]')?.nextElementSibling?.className).toContain('h-px');
      expect(container.querySelector('[data-message-id="m4"]')?.nextElementSibling?.className ?? '').not.toContain(
        'h-px',
      );
    });

    it('keeps the plain list at 20 messages and switches to the virtual list at 21', () => {
      openChat('chat-1', makeMessages(20));
      const view = renderChat();
      expect(screen.queryByTestId('virtual-list')).toBeNull();
      expect(boxes()).toHaveLength(20);
      view.unmount();

      openChat('chat-1', makeMessages(21));
      renderChat();
      expect(screen.getByTestId('virtual-list')).toHaveAttribute('data-count', '21');
      expect(screen.queryByTestId('message-box')).toBeNull();
      expect(screen.queryByTestId('clearance-spacer')).toBeNull();
    });

    it('counts the compacted summary row toward the virtual-list threshold', () => {
      openChat('chat-1', makeMessages(20), { compactedSummary: 'earlier turns, condensed' });
      renderChat();

      expect(screen.getByTestId('virtual-list')).toHaveAttribute('data-count', '21');
    });

    it('hands the virtual list the highlighted message id', () => {
      probes.searchParams = new URLSearchParams('highlight=m7');
      openChat('chat-1', makeMessages(25));
      renderChat();

      expect(probes.virtual.lastProps).toEqual({ messageCount: 25, highlightMessageId: 'm7' });
    });

    it('shows the override messages when it has any and falls back to the store when it is empty', () => {
      openChat('chat-1', makeMessages(2));
      const { update } = renderChat({ messagesOverride: makeMessages(3, 'chat-2') });
      expect(boxes()).toHaveLength(3);

      update({ messagesOverride: [] });
      expect(boxes()).toHaveLength(2);

      update({});
      expect(boxes()).toHaveLength(2);
    });

    it('puts the compacted summary row in front of the messages and numbers the messages after it', () => {
      openChat('chat-1', makeMessages(2), { compactedSummary: 'earlier turns, condensed' });
      const { container } = renderChat();

      expect(container.querySelector('[data-message-id]')?.getAttribute('data-message-id')).toBe(
        'compacted-summary-view',
      );
      expect(screen.getByTestId('compacted-summary-view')).toContainElement(screen.getByTestId('compacted-summary'));
      expect(boxes().map((box) => [box.dataset.message, box.dataset.index, box.dataset.last])).toEqual([
        ['m1', '1', 'false'],
        ['m2', '2', 'true'],
      ]);
    });

    it('does not show the compacted summary row for an empty conversation', () => {
      openChat('chat-1', [], { compactedSummary: 'earlier turns, condensed' });
      renderChat();

      expect(screen.queryByTestId('compacted-summary-view')).toBeNull();
      expect(screen.queryByTestId('message-box')).toBeNull();
    });

    it('shows the loading placeholder only until the assistant message appears', () => {
      openChat('chat-1', makeMessages(1));
      const { update } = renderChat({ loading: true, messageAppeared: false });
      expect(screen.getByTestId('message-loading')).toBeInTheDocument();

      update({ loading: true, messageAppeared: true });
      expect(screen.queryByTestId('message-loading')).toBeNull();

      update({ loading: false, messageAppeared: false });
      expect(screen.queryByTestId('message-loading')).toBeNull();
    });

    it('rings the message named by the highlight parameter and no other', () => {
      probes.searchParams = new URLSearchParams('highlight=m2');
      openChat('chat-1', makeMessages(3));
      const { container } = renderChat();

      expect(container.querySelector('[data-message-id="m2"]')?.className).toContain('ring-2');
      expect(container.querySelector('[data-message-id="m1"]')?.className ?? '').not.toContain('ring-2');
      expect(container.querySelector('[data-message-id="m3"]')?.className ?? '').not.toContain('ring-2');
    });

    it('centres the highlighted message on the next frame', () => {
      probes.searchParams = new URLSearchParams('highlight=m2');
      openChat('chat-1', makeMessages(4));
      renderChat();
      expect(browser.scrolled).toEqual([]);

      act(() => browser.flushFrames());
      expect(browser.scrolled).toContainEqual({ id: 'm2', options: { behavior: 'smooth', block: 'center' } });
    });

    it('does not scroll when the highlighted message is not in the list', () => {
      probes.searchParams = new URLSearchParams('highlight=missing');
      openChat('chat-1', makeMessages(4));
      renderChat();

      act(() => browser.flushFrames());
      expect(browser.scrolled).toEqual([]);
    });
  });

  describe('composer dock', () => {
    it('renders the composer and the agent panel in both list modes', () => {
      openChat('chat-1', makeMessages(2));
      const plain = renderChat({ loading: true });
      expect(screen.getByTestId('message-input')).toHaveAttribute('data-loading', 'true');
      expect(screen.getByTestId('agent-config-panel')).toBeInTheDocument();
      plain.unmount();

      openChat('chat-1', makeMessages(25));
      renderChat();
      expect(screen.getByTestId('message-input')).toHaveAttribute('data-loading', 'false');
      expect(screen.getByTestId('agent-config-panel')).toBeInTheDocument();
    });

    it('remounts the composer when the conversation changes so a draft does not follow it', () => {
      openChat('chat-1', makeMessages(2));
      renderChat();
      expect(probes.messageInputMounts).toEqual(['chat-1']);

      act(() => openChat('chat-2', makeMessages(2, 'chat-2')));
      expect(probes.messageInputMounts).toEqual(['chat-1', 'chat-2']);
    });

    it('registers the quick-focus shortcut', () => {
      openChat('chat-1', makeMessages(1));
      renderChat();

      expect(probes.fastFocus).toHaveBeenCalledWith({ enabled: true });
    });

    it('keeps the dock visible by default', () => {
      openChat('chat-1', makeMessages(1));
      const { container } = renderChat();

      expect(dock(container)?.className).toContain('opacity-100');
    });
  });

  describe('page chrome', () => {
    it('titles the page after a lone first message, without the datetime tag and cut to 30 characters', () => {
      openChat('chat-1', [
        {
          ...makeMessages(1)[0],
          content: `<current_datetime>2026-01-01</current_datetime>  ${'a'.repeat(40)}`,
        },
      ]);
      renderChat();

      expect(document.title).toBe(`${'a'.repeat(30)} - appTitle`);
    });

    it('leaves the title alone once there is more than one message', () => {
      openChat('chat-1', makeMessages(2));
      renderChat();

      expect(document.title).toBe('before');
    });

    it('sets the composer width after a short delay, falling back to 740px when the column has no width', () => {
      openChat('chat-1', makeMessages(2));
      renderChat();
      expect(document.documentElement.style.getPropertyValue('--message-input-width')).toBe('');

      act(() => void vi.advanceTimersByTime(99));
      expect(document.documentElement.style.getPropertyValue('--message-input-width')).toBe('');
      act(() => void vi.advanceTimersByTime(1));
      expect(document.documentElement.style.getPropertyValue('--message-input-width')).toBe('740px');
    });

    it('re-measures the column after a resize burst settles and stops once unmounted', () => {
      const width = vi.spyOn(Element.prototype, 'scrollWidth', 'get').mockReturnValue(612);
      openChat('chat-1', makeMessages(2));
      const { unmount } = renderChat();
      act(() => void vi.advanceTimersByTime(100));
      expect(document.documentElement.style.getPropertyValue('--message-input-width')).toBe('612px');

      width.mockReturnValue(700);
      act(() => {
        window.dispatchEvent(new Event('resize'));
        vi.advanceTimersByTime(60);
        window.dispatchEvent(new Event('resize'));
        vi.advanceTimersByTime(99);
      });
      expect(document.documentElement.style.getPropertyValue('--message-input-width')).toBe('612px');
      act(() => void vi.advanceTimersByTime(1));
      expect(document.documentElement.style.getPropertyValue('--message-input-width')).toBe('700px');

      width.mockReturnValue(900);
      act(() => void window.dispatchEvent(new Event('resize')));
      unmount();
      act(() => void vi.advanceTimersByTime(500));
      expect(document.documentElement.style.getPropertyValue('--message-input-width')).toBe('700px');
    });

    it('releases its resize listener and every pending timer when unmounted', () => {
      const added = vi.spyOn(window, 'addEventListener');
      const removed = vi.spyOn(window, 'removeEventListener');
      openChat('chat-1', makeMessages(2));
      const { unmount } = renderChat();
      const resizeHandlers = added.mock.calls
        .filter(([type]) => String(type) === 'resize')
        .map(([, handler]) => handler);
      expect(resizeHandlers.length).toBeGreaterThan(0);
      act(() => void window.dispatchEvent(new Event('resize')));
      expect(vi.getTimerCount()).toBeGreaterThan(0);

      unmount();

      for (const handler of resizeHandlers) {
        expect(removed).toHaveBeenCalledWith('resize', handler);
      }
      expect(vi.getTimerCount()).toBe(0);
    });

    it('feeds the rendered messages to the question navigator', () => {
      const syncMessages = vi.fn();
      useUserQuestionNavStore.setState({ syncMessages });
      openChat('chat-1', makeMessages(3));
      renderChat();

      expect(syncMessages).toHaveBeenLastCalledWith(
        expect.arrayContaining([expect.objectContaining({ messageId: 'm3' })]),
      );
      expect(syncMessages.mock.lastCall?.[0]).toHaveLength(3);
    });
  });
});
