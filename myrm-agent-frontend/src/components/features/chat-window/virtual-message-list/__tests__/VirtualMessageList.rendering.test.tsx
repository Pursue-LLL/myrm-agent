import { act, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { installListStubs, kit, makeMessages, renderList, tearDownList, type ListStubs } from './virtualListKit';

let stubs: ListStubs;

beforeEach(() => {
  stubs = installListStubs();
});

afterEach(tearDownList);

/** The positioned wrapper the virtualizer owns around a message box. */
const rowOf = (box: HTMLElement) => box.parentElement?.parentElement as HTMLElement;

const compactedSummaryRow: Message = {
  messageId: 'compacted-summary-view',
  chatId: 'chat-1',
  createdAt: new Date(2026, 0, 1),
  content: '',
  role: 'system',
  isCompactedSummaryView: true,
};

describe('VirtualMessageList rows', () => {
  it('renders only the rows the virtualizer shows, at the offsets it reports', () => {
    kit.state.start = 2;
    kit.state.end = 5;
    renderList();

    const boxes = screen.getAllByTestId('message-box');
    expect(boxes.map((box) => box.dataset.message)).toEqual(['m3', 'm4', 'm5']);
    const rows = boxes.map(rowOf);
    expect(rows.map((row) => row.dataset.index)).toEqual(['2', '3', '4']);
    expect(rows[0]).toHaveStyle({ position: 'absolute', transform: 'translateY(200px)' });
    expect(rows[2]).toHaveStyle({ transform: 'translateY(400px)' });
  });

  it('hands every rendered row to the virtualizer so it can measure the row', () => {
    kit.state.start = 2;
    kit.state.end = 5;
    renderList();

    const measured = kit.virtualizer.measureElement.mock.calls.map(
      ([element]) => (element as HTMLElement).dataset.index,
    );
    expect(measured).toEqual(['2', '3', '4']);
  });

  it('sizes the inner container to the total height the virtualizer reports', () => {
    kit.state.total = 4321;
    const { container } = renderList();

    expect(container.querySelector('.max-w-5xl')).toHaveStyle({ height: '4321px', position: 'relative' });
  });

  it('tells each message box its index, whether the list is loading and whether it is the last message', () => {
    kit.state.start = 28;
    kit.state.end = 30;
    renderList({ loading: true });

    const [secondToLast, last] = screen.getAllByTestId('message-box');
    expect(secondToLast).toHaveAttribute('data-index', '28');
    expect(secondToLast).toHaveAttribute('data-last', 'false');
    expect(last).toHaveAttribute('data-index', '29');
    expect(last).toHaveAttribute('data-last', 'true');
    expect(last).toHaveAttribute('data-loading', 'true');
  });

  it('draws a rule under an assistant message unless it is the last one', () => {
    kit.state.end = 3;
    const { container, update } = renderList({ messages: makeMessages(4) });

    const rules = () => [...container.querySelectorAll('.h-px')].map((rule) => rule.parentElement?.dataset.messageId);
    expect(rules()).toEqual(['m2']);

    kit.state.end = 2;
    update({ messages: makeMessages(2) });
    expect(rules()).toEqual([]);
  });

  it('renders the compacted summary row instead of a message box', () => {
    kit.state.end = 2;
    renderList({ messages: [compactedSummaryRow, ...makeMessages(1)] });

    const row = screen.getByTestId('compacted-summary-view');
    expect(row).toContainElement(screen.getByTestId('compacted-summary'));
    expect(row).toHaveAttribute('data-message-id', 'compacted-summary-view');
    expect(screen.getAllByTestId('message-box').map((box) => box.dataset.message)).toEqual(['m1']);
  });

  it('rings the highlighted message and no other', () => {
    kit.state.end = 3;
    const { container } = renderList({ highlightMessageId: 'm2' });

    expect(container.querySelector('[data-message-id="m2"]')).toHaveClass('ring-2', 'ring-primary/40', 'rounded-lg');
    expect(container.querySelector('[data-message-id="m1"]')?.className ?? '').not.toContain('ring-2');
    expect(container.querySelector('[data-message-id="m3"]')?.className ?? '').not.toContain('ring-2');
  });
});

describe('VirtualMessageList chrome', () => {
  it('is a scrolling box sized against the viewport', () => {
    const { scroller } = renderList();

    expect(scroller().className).toContain('overflow-y-auto');
    // jsdom reorders the operands of calc(), so pin its two terms rather than their order.
    expect(scroller().style.height).toMatch(/^calc\(.*100vh.*\)$/);
    expect(scroller().style.height).toContain('200px');
  });

  it('shows the loading placeholder only until the answer appears', () => {
    const { update } = renderList({ loading: true, messageAppeared: false });
    expect(screen.getByTestId('message-loading')).toBeInTheDocument();

    update({ loading: true, messageAppeared: true });
    expect(screen.queryByTestId('message-loading')).toBeNull();

    update({ loading: false, messageAppeared: false });
    expect(screen.queryByTestId('message-loading')).toBeNull();
  });

  it('shows a spinner above the list while older messages are loading', () => {
    useChatStore.setState({ loadingOlder: true });
    const { container } = renderList();
    expect(container.querySelector('.animate-spin')).not.toBeNull();
  });

  it('shows the spinner when older messages start loading and drops it when they are in', () => {
    const { container } = renderList();
    expect(container.querySelector('.animate-spin')).toBeNull();

    act(() => useChatStore.setState({ loadingOlder: true }));
    expect(container.querySelector('.animate-spin')).not.toBeNull();

    act(() => useChatStore.setState({ loadingOlder: false }));
    expect(container.querySelector('.animate-spin')).toBeNull();
  });

  it('does not render again for chat store changes it does not show, such as the draft being typed', () => {
    renderList();
    kit.virtualizer.getVirtualItems.mockClear();

    act(() => useChatStore.setState({ inputMessage: 'a draft' }));
    act(() => useChatStore.setState({ inputMessage: 'a draft, longer' }));

    expect(kit.virtualizer.getVirtualItems).not.toHaveBeenCalled();
  });

  it('shows no spinner when nothing older is loading', () => {
    const { container } = renderList();
    expect(container.querySelector('.animate-spin')).toBeNull();
  });

  it('hands the clearance spacer the message column and its own minimum height', () => {
    renderList();

    const spacer = screen.getByTestId('clearance-spacer');
    expect(spacer).toHaveAttribute('data-column', 'message-column');
    expect(spacer.dataset.class).toContain('min-h-44');
  });
});

describe('VirtualMessageList row heights', () => {
  const estimate = (index: number) => kit.state.options?.estimateSize(index);

  it('estimates a user row shorter than an assistant row, and an unknown row like an assistant row', () => {
    renderList();

    expect(estimate(0)).toBe(80);
    expect(estimate(1)).toBe(150);
    expect(estimate(99)).toBe(150);
  });

  it('uses the measured height of a row once it has one, and tells the virtualizer to re-measure', () => {
    stubs.setRowHeight(321);
    kit.state.end = 2;
    renderList();

    expect(estimate(0)).toBe(321);
    expect(estimate(1)).toBe(321);
    expect(estimate(2)).toBe(80);
    expect(kit.virtualizer.measure).toHaveBeenCalled();
  });

  it('ignores a row that has no layout yet', () => {
    stubs.setRowHeight(0);
    kit.state.end = 2;
    renderList();

    expect(estimate(0)).toBe(80);
    expect(estimate(1)).toBe(150);
    expect(kit.virtualizer.measure).not.toHaveBeenCalled();
  });

  it('does not record a height for a message that has no id', () => {
    stubs.setRowHeight(321);
    kit.state.end = 1;
    const [first] = makeMessages(30);
    renderList({ messages: [{ ...first, messageId: '' }, ...makeMessages(30).slice(1)] });

    expect(kit.virtualizer.measure).not.toHaveBeenCalled();
    expect(estimate(0)).toBe(80);
  });

  it('forgets measured heights when the conversation changes', () => {
    stubs.setRowHeight(321);
    kit.state.end = 2;
    const { update } = renderList();
    expect(estimate(0)).toBe(321);

    stubs.setRowHeight(0);
    update({ chatId: 'another-chat', messages: makeMessages(30, 'another-chat') });
    expect(estimate(0)).toBe(80);
    expect(estimate(1)).toBe(150);
  });

  it('forgets measured heights on every change of conversation, including a return to the first', () => {
    stubs.setRowHeight(321);
    kit.state.end = 2;
    const { update } = renderList({ chatId: 'chat-a' });
    expect(estimate(0)).toBe(321);

    stubs.setRowHeight(0);
    update({ chatId: 'chat-b' });
    expect(estimate(0)).toBe(80);

    stubs.setRowHeight(321);
    update({ messages: makeMessages(31) });
    expect(estimate(0)).toBe(321);

    stubs.setRowHeight(0);
    update({ chatId: 'chat-a' });
    expect(estimate(0)).toBe(80);
  });

  it('keeps measured heights while the same conversation grows', () => {
    stubs.setRowHeight(321);
    kit.state.end = 2;
    const { update } = renderList({ chatId: 'growing-chat' });

    stubs.setRowHeight(0);
    update({ messages: makeMessages(31) });
    expect(estimate(0)).toBe(321);
  });

  it('measures a row element by its box height', () => {
    renderList();
    const element = document.createElement('div');
    vi.spyOn(element, 'getBoundingClientRect').mockReturnValue({ height: 77 } as DOMRect);

    expect(kit.state.options?.measureElement(element)).toBe(77);
  });

  it('gives the virtualizer the message count, three extra rows each way and the scroll box', () => {
    const { scroller } = renderList({ messages: makeMessages(12) });

    expect(kit.state.options?.count).toBe(12);
    expect(kit.state.options?.overscan).toBe(3);
    expect(kit.state.options?.getScrollElement()).toBe(scroller());
  });
});
