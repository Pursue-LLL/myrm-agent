import { act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  installListStubs,
  kit,
  makeMessages,
  readMirror,
  renderList,
  tearDownList,
  type ListStubs,
} from './virtualListKit';

let stubs: ListStubs;

beforeEach(() => {
  stubs = installListStubs();
});

afterEach(tearDownList);

const CENTRE = { align: 'center', behavior: 'smooth' };

describe('VirtualMessageList highlighted message', () => {
  it('centres the highlighted message on the next frame and marks the reader as scrolled up', () => {
    const view = renderList({ highlightMessageId: 'm7' });
    expect(kit.virtualizer.scrollToIndex).not.toHaveBeenCalled();

    act(() => stubs.flushFrames());

    expect(kit.virtualizer.scrollToIndex).toHaveBeenCalledExactlyOnceWith(6, CENTRE);
    expect(view.userScrolledRef.current).toBe(true);
    expect(view.onUserScrolledChange).toHaveBeenCalledExactlyOnceWith(true);
    expect(readMirror(view.chatId() ?? '')).toMatchObject({ isFollowingBottom: false, isUserScrolledUp: true });
  });

  it('centres the first message of the conversation too', () => {
    renderList({ highlightMessageId: 'm1' });

    act(() => stubs.flushFrames());

    expect(kit.virtualizer.scrollToIndex).toHaveBeenCalledExactlyOnceWith(0, CENTRE);
  });

  it('records which highlight it centred', () => {
    const view = renderList({ highlightMessageId: 'm7' });

    expect(view.centeredHighlightRef.current).toBe('m7');
  });

  it('does nothing when the highlighted message is not in the list', () => {
    const view = renderList({ highlightMessageId: 'missing' });

    act(() => stubs.flushFrames());

    expect(kit.virtualizer.scrollToIndex).not.toHaveBeenCalled();
    expect(view.centeredHighlightRef.current).toBeNull();
    expect(view.userScrolledRef.current).toBe(false);
  });

  it('finds a highlighted message that arrives after the list was mounted', () => {
    const view = renderList({ highlightMessageId: 'm7', messages: [] });
    act(() => stubs.flushFrames());
    expect(kit.virtualizer.scrollToIndex).not.toHaveBeenCalled();

    view.update({ messages: makeMessages(30) });
    act(() => stubs.flushFrames());

    expect(kit.virtualizer.scrollToIndex).toHaveBeenCalledExactlyOnceWith(6, CENTRE);
  });

  it('centres a highlight once, however much the conversation changes afterwards', () => {
    const view = renderList({ highlightMessageId: 'm7' });
    act(() => stubs.flushFrames());

    view.update({ messages: makeMessages(32) });
    view.update({ messages: makeMessages(34), loading: false });
    act(() => stubs.flushFrames());

    expect(kit.virtualizer.scrollToIndex).toHaveBeenCalledTimes(1);
  });

  it('centres the next message when the highlight moves to it', () => {
    const view = renderList({ highlightMessageId: 'm7' });
    act(() => stubs.flushFrames());

    view.update({ highlightMessageId: 'm12' });
    act(() => stubs.flushFrames());

    expect(kit.virtualizer.scrollToIndex).toHaveBeenNthCalledWith(1, 6, CENTRE);
    expect(kit.virtualizer.scrollToIndex).toHaveBeenNthCalledWith(2, 11, CENTRE);
    expect(view.centeredHighlightRef.current).toBe('m12');
  });

  it('leaves a highlight alone when the page already centred it', () => {
    renderList({ highlightMessageId: 'm7' }, [], 'm7');

    act(() => stubs.flushFrames());

    expect(kit.virtualizer.scrollToIndex).not.toHaveBeenCalled();
  });
});
