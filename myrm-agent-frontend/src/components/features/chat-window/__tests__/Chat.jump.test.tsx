import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { makeMessages, openChat, probes, setUpChatTest, tearDownChatTest, type BrowserStubs } from './chatMocks';
import Chat from '../Chat';

function renderChat() {
  return render(<Chat loading={false} messageAppeared={false} />);
}

const click = (label: string) => fireEvent.click(screen.getByText(label));

describe('Chat jumping to a message', () => {
  let browser: BrowserStubs;

  beforeEach(() => {
    browser = setUpChatTest();
  });

  afterEach(() => {
    tearDownChatTest();
  });

  it('scrolls the plain list to the message, anchors the position there and offers the way back down', () => {
    openChat('chat-1', makeMessages(4));
    renderChat();

    click('rail jump index');

    expect(browser.scrolled).toEqual([{ id: 'm2', options: { behavior: 'smooth', block: 'start' } }]);
    expect(probes.scroll.save).toHaveBeenCalledWith({
      isFollowingBottom: false,
      isUserScrolledUp: true,
      anchorMessageId: 'm2',
    });
    expect(probes.scroll.userScrolled?.current).toBe(true);
    expect(screen.getByTestId('scroll-bottom')).toBeInTheDocument();
  });

  it('does nothing for an index that has no message', () => {
    openChat('chat-1', makeMessages(1));
    renderChat();
    browser.scrolled.length = 0; // mounting with a user message already scrolls to the end

    click('rail jump index');

    expect(browser.scrolled).toEqual([]);
    expect(probes.scroll.save).not.toHaveBeenCalled();
    expect(screen.queryByTestId('scroll-bottom')).toBeNull();
  });

  it('hands a jump to the virtual list when the conversation is long', () => {
    openChat('chat-1', makeMessages(25));
    renderChat();

    click('rail jump index');

    expect(probes.virtual.scrollToIndex).toHaveBeenCalledExactlyOnceWith(1);
    expect(browser.scrolled).toEqual([]);
    expect(probes.scroll.save).not.toHaveBeenCalled();
  });

  it('jumps by message id at once when the message is on screen', () => {
    openChat('chat-1', makeMessages(4));
    renderChat();

    click('rail jump id');

    expect(browser.scrolled).toEqual([{ id: 'm2', options: { behavior: 'smooth', block: 'start' } }]);
    expect(probes.scroll.save).toHaveBeenCalledWith({
      isFollowingBottom: false,
      isUserScrolledUp: true,
      anchorMessageId: 'm2',
    });
    expect(probes.scroll.userScrolled?.current).toBe(true);
    expect(screen.getByTestId('scroll-bottom')).toBeInTheDocument();

    act(() => browser.flushFrames());
    expect(browser.scrolled).toHaveLength(1);
  });

  it('retries a jump by id on the next frame when the message is mounted late', () => {
    openChat('chat-1', makeMessages(1));
    renderChat();
    browser.scrolled.length = 0; // mounting with a user message already scrolls to the end

    click('rail jump id');
    expect(browser.scrolled).toEqual([]);
    expect(screen.getByTestId('scroll-bottom')).toBeInTheDocument();

    act(() => openChat('chat-1', makeMessages(2)));
    act(() => browser.stepFrame());

    expect(browser.scrolled).toEqual([{ id: 'm2', options: { behavior: 'smooth', block: 'start' } }]);
    act(() => browser.flushFrames());
    expect(browser.scrolled).toHaveLength(1);
  });

  it('tries a second time on the frame after that', () => {
    openChat('chat-1', makeMessages(1));
    renderChat();
    browser.scrolled.length = 0; // mounting with a user message already scrolls to the end
    click('rail jump id');

    act(() => browser.stepFrame());
    expect(browser.scrolled).toEqual([]);
    act(() => openChat('chat-1', makeMessages(2)));
    act(() => browser.stepFrame());

    expect(browser.scrolled).toEqual([{ id: 'm2', options: { behavior: 'smooth', block: 'start' } }]);
  });

  it('stops after two frames when the message never shows up', () => {
    openChat('chat-1', makeMessages(1));
    renderChat();
    browser.scrolled.length = 0; // mounting with a user message already scrolls to the end
    click('rail jump id');

    act(() => browser.stepFrame());
    act(() => browser.stepFrame());
    act(() => openChat('chat-1', makeMessages(2)));
    act(() => browser.flushFrames());

    expect(browser.scrolled).toEqual([]);
  });

  it('finds the message in the store for a virtual list instead of in the DOM', () => {
    openChat('chat-1', makeMessages(25));
    renderChat();

    click('rail jump id');

    expect(probes.virtual.scrollToIndex).toHaveBeenCalledExactlyOnceWith(1);
    expect(browser.scrolled).toEqual([]);
    expect(probes.scroll.userScrolled?.current).toBe(true);
    expect(screen.getByTestId('scroll-bottom')).toBeInTheDocument();
  });
});
