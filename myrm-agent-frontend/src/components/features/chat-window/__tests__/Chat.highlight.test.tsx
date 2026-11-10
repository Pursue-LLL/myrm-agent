import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { makeMessages, openChat, probes, setUpChatTest, tearDownChatTest, type BrowserStubs } from './chatMocks';
import Chat from '../Chat';
import { expectNonNull } from '@/test-utils/expectDefined';
import useChatStore from '@/store/useChatStore';

/** `Chat` is memoised and the router is mocked, so `update` flips an inert prop to make it read the router again. */
function renderChat() {
  let tick = false;
  const ui = (messageAppeared: boolean) => <Chat loading={false} messageAppeared={messageAppeared} />;
  const view = render(ui(tick));
  return {
    ...view,
    update: () => {
      tick = !tick;
      view.rerender(ui(tick));
    },
  };
}

describe('Chat highlighted message', () => {
  let browser: BrowserStubs;

  beforeEach(() => {
    browser = setUpChatTest();
  });

  afterEach(() => {
    tearDownChatTest();
  });

  const centred = (id: string) =>
    browser.scrolled.filter((entry) => entry.id === id && entry.options.block === 'center').length;
  const highlight = (id: string | null) => {
    probes.searchParams = id ? new URLSearchParams(`highlight=${id}`) : new URLSearchParams();
  };

  it('centres the highlighted message once, however much the conversation changes afterwards', () => {
    highlight('m2');
    openChat('chat-1', makeMessages(4));
    renderChat();
    act(() => browser.flushFrames());
    expect(centred('m2')).toBe(1);

    act(() => useChatStore.setState({ messages: makeMessages(5) }));
    act(() => useChatStore.setState({ messages: makeMessages(6) }));
    act(() => browser.flushFrames());

    expect(centred('m2')).toBe(1);
  });

  it('centres the next message when the highlight moves to it', () => {
    highlight('m2');
    openChat('chat-1', makeMessages(4));
    const { update } = renderChat();
    act(() => browser.flushFrames());

    highlight('m3');
    update();
    act(() => browser.flushFrames());

    expect(centred('m2')).toBe(1);
    expect(centred('m3')).toBe(1);
  });

  it('centres the same message again after its highlight was removed and set once more', () => {
    highlight('m2');
    openChat('chat-1', makeMessages(4));
    const { update } = renderChat();
    act(() => browser.flushFrames());

    highlight(null);
    update();
    highlight('m2');
    update();
    act(() => browser.flushFrames());

    expect(centred('m2')).toBe(2);
  });

  it('does not centre a message that is not there, and picks it up once it arrives', () => {
    highlight('m5');
    openChat('chat-1', makeMessages(4));
    renderChat();
    act(() => browser.flushFrames());
    expect(centred('m5')).toBe(0);

    act(() => useChatStore.setState({ messages: makeMessages(5) }));
    act(() => browser.flushFrames());

    expect(centred('m5')).toBe(1);
  });

  describe('with the virtual list', () => {
    it('hands the list the record of what was centred, so growing into a virtual list does not centre it again', () => {
      highlight('m2');
      openChat('chat-1', makeMessages(20));
      renderChat();
      act(() => browser.flushFrames());
      expect(centred('m2')).toBe(1);

      act(() => useChatStore.setState({ messages: makeMessages(21) }));

      const record = probes.virtual.centeredHighlightRef;
      expectNonNull(record, 'centered highlight record');
      expect(record.current).toBe('m2');
    });

    it('clears the record when the highlight goes away, so the list centres the next one', () => {
      highlight('m2');
      openChat('chat-1', makeMessages(25));
      const { update } = renderChat();
      const record = probes.virtual.centeredHighlightRef;
      expectNonNull(record, 'centered highlight record');
      record.current = 'm2';

      highlight(null);
      update();

      expect(record.current).toBeNull();
    });
  });
});
