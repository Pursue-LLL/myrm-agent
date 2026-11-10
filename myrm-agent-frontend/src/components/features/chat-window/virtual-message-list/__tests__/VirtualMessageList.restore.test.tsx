import { act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  freshChatId,
  installListStubs,
  kit,
  makeMessages,
  readMirror,
  renderList,
  scrollTo,
  settle,
  setScrollMetrics,
  tearDownList,
  writeMirror,
  type ListStubs,
} from './virtualListKit';

let stubs: ListStubs;

beforeEach(() => {
  stubs = installListStubs();
});

afterEach(tearDownList);

describe('VirtualMessageList restoring the reading position', () => {
  it('puts a reader who had scrolled up back where they were', () => {
    const chatId = freshChatId();
    writeMirror(chatId, { position: 40, isFollowingBottom: false, isUserScrolledUp: true });
    const view = renderList({ chatId });
    setScrollMetrics(view.scroller(), { top: 0, height: 2000, client: 600 });

    settle(50);
    act(() => stubs.flushFrames());

    expect(view.userScrolledRef.current).toBe(true);
    expect(view.onUserScrolledChange).toHaveBeenCalledExactlyOnceWith(true);
    expect(view.scroller().scrollTop).toBe(40);
  });

  it('puts a reader who was following the answer back at the bottom', () => {
    const chatId = freshChatId();
    writeMirror(chatId, { position: 10, isFollowingBottom: true, isUserScrolledUp: false });
    const view = renderList({ chatId });
    view.userScrolledRef.current = true;
    setScrollMetrics(view.scroller(), { top: 0, height: 2000, client: 600 });

    settle(50);
    act(() => stubs.flushFrames());

    expect(view.userScrolledRef.current).toBe(false);
    expect(view.onUserScrolledChange).toHaveBeenCalledExactlyOnceWith(false);
    expect(view.scroller().scrollTop).toBe(2000);
  });

  it('leaves the reader alone when no position was saved', () => {
    const view = renderList();

    settle(50);
    act(() => stubs.flushFrames());

    expect(view.onUserScrolledChange).not.toHaveBeenCalled();
    expect(view.userScrolledRef.current).toBe(false);
  });

  it('restores once per conversation, not again when a message arrives', () => {
    const chatId = freshChatId();
    writeMirror(chatId, { position: 40, isFollowingBottom: false, isUserScrolledUp: true });
    const view = renderList({ chatId });
    settle(50);
    expect(view.onUserScrolledChange).toHaveBeenCalledTimes(1);

    view.update({ messages: makeMessages(32) });
    settle(50);
    expect(view.onUserScrolledChange).toHaveBeenCalledTimes(1);
  });

  it('waits for messages before restoring', () => {
    const chatId = freshChatId();
    writeMirror(chatId, { position: 40, isFollowingBottom: false, isUserScrolledUp: true });
    const view = renderList({ chatId, messages: [] });
    settle(50);
    expect(view.onUserScrolledChange).not.toHaveBeenCalled();

    view.update({ messages: makeMessages(30) });
    settle(50);
    expect(view.onUserScrolledChange).toHaveBeenCalledExactlyOnceWith(true);
  });

  it('does not restore into a list that is already gone', () => {
    const chatId = freshChatId();
    writeMirror(chatId, { position: 40, isFollowingBottom: false, isUserScrolledUp: true });
    const view = renderList({ chatId });

    view.unmount();
    settle(50);

    expect(view.onUserScrolledChange).not.toHaveBeenCalled();
  });

  it('does not restore for a conversation without an id', () => {
    const view = renderList({ chatId: undefined });

    settle(50);
    expect(view.onUserScrolledChange).not.toHaveBeenCalled();
  });
});

describe('VirtualMessageList controls handed to the page', () => {
  it('exposes jump-to-message while mounted and takes it back on unmount', () => {
    const view = renderList();
    expect(view.scrollToMessageRef.current).toBeTypeOf('function');

    view.unmount();
    expect(view.scrollToMessageRef.current).toBeNull();
  });

  it('jumps to a message, marks the reader as scrolled up and saves that position', () => {
    const view = renderList();

    act(() => view.scrollToMessageRef.current?.(4));

    expect(kit.virtualizer.scrollToIndex).toHaveBeenCalledExactlyOnceWith(4, { align: 'start', behavior: 'smooth' });
    expect(view.userScrolledRef.current).toBe(true);
    expect(view.onUserScrolledChange).toHaveBeenCalledExactlyOnceWith(true);
    expect(readMirror(view.chatId() ?? '')).toMatchObject({ isFollowingBottom: false, isUserScrolledUp: true });
  });

  it('exposes jump-to-bottom while mounted and takes it back on unmount', () => {
    const view = renderList();
    expect(view.scrollToBottomRef.current).toBeTypeOf('function');

    view.unmount();
    expect(view.scrollToBottomRef.current).toBeNull();
  });

  it('jumps to the last message, marks the reader as following and saves that position', () => {
    const view = renderList();
    view.userScrolledRef.current = true;

    act(() => view.scrollToBottomRef.current?.());

    expect(kit.virtualizer.scrollToIndex).toHaveBeenCalledExactlyOnceWith(29, { align: 'end', behavior: 'smooth' });
    expect(view.userScrolledRef.current).toBe(false);
    expect(view.onUserScrolledChange).toHaveBeenCalledExactlyOnceWith(false);
    expect(readMirror(view.chatId() ?? '')).toMatchObject({ isFollowingBottom: true, isUserScrolledUp: false });
  });

  it('jumps to the latest last message after the conversation grew', () => {
    const view = renderList();
    view.update({ messages: makeMessages(33) });

    act(() => view.scrollToBottomRef.current?.());

    expect(kit.virtualizer.scrollToIndex).toHaveBeenLastCalledWith(32, { align: 'end', behavior: 'smooth' });
  });

  it('works without the optional handles', () => {
    const view = renderList({}, ['scrollToMessageRef', 'scrollToBottomRef', 'onUserScrolledChange']);

    expect(view.scrollToMessageRef.current).toBeNull();
    expect(view.scrollToBottomRef.current).toBeNull();
    scrollTo(view.scroller(), 500);
    scrollTo(view.scroller(), 300);
    expect(view.userScrolledRef.current).toBe(true);
  });
});
