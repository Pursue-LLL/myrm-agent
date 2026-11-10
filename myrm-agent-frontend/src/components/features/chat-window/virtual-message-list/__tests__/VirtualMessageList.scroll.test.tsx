import { act, fireEvent } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { deferred } from '@/test-utils/deferred';
import useChatStore from '@/store/useChatStore';
import {
  installListStubs,
  kit,
  makeMessages,
  readMirror,
  renderList,
  scrollTo,
  settle,
  setScrollMetrics,
  tearDownList,
  type ListStubs,
} from './virtualListKit';

let stubs: ListStubs;

beforeEach(() => {
  stubs = installListStubs();
});

afterEach(tearDownList);

describe('VirtualMessageList following a streaming answer', () => {
  it('scrolls to the last row without animation while an answer streams', () => {
    renderList({ loading: true });

    expect(kit.virtualizer.scrollToIndex).toHaveBeenCalledExactlyOnceWith(29, { align: 'end', behavior: 'auto' });
  });

  it('keeps following each update of the streaming answer', () => {
    const view = renderList({ loading: true });
    view.update({ messages: makeMessages(30) });

    expect(kit.virtualizer.scrollToIndex).toHaveBeenCalledTimes(2);
  });

  it('does not follow once the reader scrolled up', () => {
    const view = renderList({ loading: true });
    kit.virtualizer.scrollToIndex.mockClear();
    view.userScrolledRef.current = true;

    view.update({ messages: makeMessages(30) });
    expect(kit.virtualizer.scrollToIndex).not.toHaveBeenCalled();
  });

  it('does not follow an answer that is not streaming', () => {
    renderList({ loading: false });

    expect(kit.virtualizer.scrollToIndex).not.toHaveBeenCalled();
  });

  it('takes the reader to the bottom with a smooth scroll when they send a message', () => {
    const view = renderList();
    view.userScrolledRef.current = true;

    view.update({ messages: makeMessages(31), loading: true });

    expect(view.userScrolledRef.current).toBe(false);
    expect(view.onUserScrolledChange).toHaveBeenCalledExactlyOnceWith(false);
    expect(kit.virtualizer.scrollToIndex).toHaveBeenCalledExactlyOnceWith(30, { align: 'end', behavior: 'smooth' });
  });

  it('scrolls once, smoothly, when a reader who is following sends a message', () => {
    const view = renderList();

    view.update({ messages: makeMessages(31), loading: true });

    expect(kit.virtualizer.scrollToIndex).toHaveBeenCalledExactlyOnceWith(30, { align: 'end', behavior: 'smooth' });
  });
});

describe('VirtualMessageList scroll listener', () => {
  it('marks the reader as scrolled up after they move up by more than 5px, and says so once', () => {
    const view = renderList();
    scrollTo(view.scroller(), 500);

    scrollTo(view.scroller(), 400);
    scrollTo(view.scroller(), 300);

    expect(view.userScrolledRef.current).toBe(true);
    expect(view.onUserScrolledChange).toHaveBeenCalledExactlyOnceWith(true);
  });

  it('counts an upward movement of 6px', () => {
    const view = renderList();
    scrollTo(view.scroller(), 500);

    scrollTo(view.scroller(), 494);

    expect(view.userScrolledRef.current).toBe(true);
    expect(view.onUserScrolledChange).toHaveBeenCalledExactlyOnceWith(true);
  });

  it('ignores an upward movement of 5px or less', () => {
    const view = renderList();
    scrollTo(view.scroller(), 500);

    scrollTo(view.scroller(), 495);

    expect(view.userScrolledRef.current).toBe(false);
    expect(view.onUserScrolledChange).not.toHaveBeenCalled();
  });

  it('marks the reader as following again after they scroll down to within 100px of the end', () => {
    const view = renderList();
    setScrollMetrics(view.scroller(), { top: 0, height: 2000, client: 600 });
    view.userScrolledRef.current = true;

    scrollTo(view.scroller(), 1350);

    expect(view.userScrolledRef.current).toBe(false);
    expect(view.onUserScrolledChange).toHaveBeenCalledExactlyOnceWith(false);
  });

  it('keeps a scrolled-up reader scrolled up while they are still far from the end', () => {
    const view = renderList();
    setScrollMetrics(view.scroller(), { top: 0, height: 2000, client: 600 });
    view.userScrolledRef.current = true;

    scrollTo(view.scroller(), 300);

    expect(view.userScrolledRef.current).toBe(true);
    expect(view.onUserScrolledChange).not.toHaveBeenCalled();
  });

  it('keeps a scrolled-up reader scrolled up while 100px or more remain below', () => {
    const view = renderList();
    setScrollMetrics(view.scroller(), { top: 0, height: 2000, client: 600 });
    view.userScrolledRef.current = true;

    scrollTo(view.scroller(), 1300);

    expect(view.userScrolledRef.current).toBe(true);
    expect(view.onUserScrolledChange).not.toHaveBeenCalled();
  });

  it('counts a downward movement of 6px near the end', () => {
    const view = renderList();
    setScrollMetrics(view.scroller(), { top: 0, height: 2000, client: 600 });
    scrollTo(view.scroller(), 1320);
    view.userScrolledRef.current = true;

    scrollTo(view.scroller(), 1326);

    expect(view.userScrolledRef.current).toBe(false);
    expect(view.onUserScrolledChange).toHaveBeenCalledExactlyOnceWith(false);
  });

  it('ignores a downward movement of 5px or less', () => {
    const view = renderList();
    setScrollMetrics(view.scroller(), { top: 0, height: 2000, client: 600 });
    scrollTo(view.scroller(), 1320);
    view.userScrolledRef.current = true;

    scrollTo(view.scroller(), 1325);

    expect(view.userScrolledRef.current).toBe(true);
    expect(view.onUserScrolledChange).not.toHaveBeenCalled();
  });

  it('says nothing when a reader who was already following scrolls down near the end', () => {
    const view = renderList();
    setScrollMetrics(view.scroller(), { top: 0, height: 2000, client: 600 });

    scrollTo(view.scroller(), 1350);

    expect(view.onUserScrolledChange).not.toHaveBeenCalled();
  });

  it('measures movement from where the list is when the listener is attached again', () => {
    useChatStore.setState({ hasMoreMessages: true });
    const view = renderList();
    setScrollMetrics(view.scroller(), { top: 690, height: 1500, client: 800 });
    view.userScrolledRef.current = true;

    act(() => useChatStore.setState({ hasMoreMessages: false }));
    scrollTo(view.scroller(), 687);

    expect(view.userScrolledRef.current).toBe(true);
    expect(view.onUserScrolledChange).not.toHaveBeenCalled();
  });

  it('listens passively, so the handler never holds up scrolling', () => {
    const addListener = vi.spyOn(EventTarget.prototype, 'addEventListener');
    const view = renderList();

    const call = addListener.mock.calls.findIndex(
      ([type], index) => type === 'scroll' && addListener.mock.contexts[index] === view.scroller(),
    );
    expect(call).toBeGreaterThanOrEqual(0);
    expect(addListener.mock.calls[call][2]).toEqual({ passive: true });
  });

  it('saves the position 200ms after the last scroll, restarting the wait on every scroll', () => {
    const view = renderList();
    setScrollMetrics(view.scroller(), { height: 2000, client: 600 });
    scrollTo(view.scroller(), 700);
    settle(150);
    scrollTo(view.scroller(), 800);
    settle(199);
    expect(readMirror(view.chatId() ?? '')).toBeNull();

    settle(1);
    expect(readMirror(view.chatId() ?? '')).toMatchObject({ position: 800 });
  });

  it('stops listening and drops the pending save when the list goes away', () => {
    const view = renderList();
    scrollTo(view.scroller(), 700);
    const scroller = view.scroller();
    view.unmount();

    settle(200);
    expect(readMirror(view.chatId() ?? '')).toBeNull();
    setScrollMetrics(scroller, { top: 300 });
    fireEvent.scroll(scroller);
    expect(view.onUserScrolledChange).not.toHaveBeenCalled();
  });
});

describe('VirtualMessageList loading older messages', () => {
  function withLoader(hasMore = true) {
    const loadOlderMessages = vi.fn<() => Promise<void>>(() => Promise.resolve());
    useChatStore.setState({ hasMoreMessages: hasMore, loadOlderMessages });
    return loadOlderMessages;
  }

  it('asks for older messages when the reader gets near the top and more exist', () => {
    const loadOlderMessages = withLoader();
    const view = renderList();

    scrollTo(view.scroller(), 150);

    expect(loadOlderMessages).toHaveBeenCalledTimes(1);
  });

  it('does not ask when nothing older exists', () => {
    const loadOlderMessages = withLoader(false);
    const view = renderList();

    scrollTo(view.scroller(), 150);

    expect(loadOlderMessages).not.toHaveBeenCalled();
  });

  it('does not ask while the reader is 200px or more from the top', () => {
    const loadOlderMessages = withLoader();
    const view = renderList();

    scrollTo(view.scroller(), 200);

    expect(loadOlderMessages).not.toHaveBeenCalled();
  });

  it('asks once while a page is on its way, then again after it arrived', async () => {
    const page = deferred<void>();
    const loadOlderMessages = vi.fn<() => Promise<void>>(() => page.promise);
    useChatStore.setState({ hasMoreMessages: true, loadOlderMessages });
    const view = renderList();

    scrollTo(view.scroller(), 150);
    scrollTo(view.scroller(), 120);
    expect(loadOlderMessages).toHaveBeenCalledTimes(1);

    await act(async () => page.resolve());
    scrollTo(view.scroller(), 100);
    expect(loadOlderMessages).toHaveBeenCalledTimes(2);
  });

  it('keeps the reader on the same message after older ones were added above', async () => {
    const page = deferred<void>();
    useChatStore.setState({ hasMoreMessages: true, loadOlderMessages: vi.fn(() => page.promise) });
    const view = renderList();
    setScrollMetrics(view.scroller(), { height: 2000, client: 600 });
    scrollTo(view.scroller(), 150);

    await act(async () => page.resolve());
    // The older messages are in the store, but only laid out before the next frame.
    setScrollMetrics(view.scroller(), { height: 3000 });
    act(() => stubs.flushFrames());

    expect(view.scroller().scrollTop).toBe(3000 - 2000 + 150);
  });
});
