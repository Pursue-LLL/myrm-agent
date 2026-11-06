import { act, fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatItem } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { expectDefined } from '@/test-utils/expectDefined';
import { DateGroupSection, type HistoryRowProps, PinnedSection } from '../ChatHistorySections';
import type { DateGroup } from '../dateGroupUtils';

interface DragEndStub {
  active: { id: string };
  over: { id: string } | null;
}

const dnd = vi.hoisted(() => ({ onDragEnd: undefined as ((event: DragEndStub) => void) | undefined }));

/** The drop handler is the only way into the section's reorder logic, so the real context hands it over. */
vi.mock('@dnd-kit/core', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@dnd-kit/core')>();
  return {
    ...actual,
    DndContext: (props: ComponentProps<typeof actual.DndContext>) => {
      dnd.onDragEnd = props.onDragEnd as typeof dnd.onDragEnd;
      return <actual.DndContext {...props} />;
    },
  };
});

vi.mock('../ChatHistoryRow', () => ({
  ChatHistoryRow: (props: {
    chat: ChatItem;
    isActive: boolean;
    batchMode?: boolean;
    isSelected?: boolean;
    onToggleSelect?: (id: string) => void;
  }) => (
    <div
      data-testid={`row:${props.chat.id}`}
      data-active={String(props.isActive)}
      data-batch={String(props.batchMode)}
      data-selected={String(props.isSelected)}
    >
      <button onClick={() => props.onToggleSelect?.(props.chat.id)}>select {props.chat.id}</button>
    </div>
  ),
  SortablePinnedRow: (props: { chat: ChatItem; isActive: boolean; pinIndex?: number }) => (
    <div data-testid={`pinned:${props.chat.id}`} data-active={String(props.isActive)} data-pin-index={props.pinIndex} />
  ),
}));

const chat = (id: string, overrides: Partial<ChatItem> = {}): ChatItem => ({
  id,
  title: `Title ${id}`,
  firstMessage: id,
  lastMessage: id,
  updatedAt: new Date('2026-11-06T10:00:00Z'),
  createdAt: new Date('2026-11-06T09:00:00Z'),
  actionMode: 'agent',
  source: 'web',
  ...overrides,
});

const noop = () => {};
const identityTranslator = ((key: string) => key) as unknown as HistoryRowProps['t'];

/** Marks chat "b" active so the tests can tell the list's per-chat props reach every row. */
const rowProps = (item: ChatItem): HistoryRowProps => ({
  chat: item,
  isMobile: false,
  isActive: item.id === 'b',
  renameId: null,
  renameValue: '',
  exportingId: null,
  formatTime: () => '',
  onRename: noop,
  onRenameSubmit: noop,
  onRenameCancel: noop,
  onRenameValueChange: noop,
  onDelete: noop,
  onExport: noop,
  onPin: noop,
  onUnpin: noop,
  t: identityTranslator,
});

/** Opacity-tinted or sub-12px section titles fall below the contrast and size the sidebar needs to be readable. */
const expectReadableHeading = (heading: HTMLElement) => {
  expect(heading.className).toContain('text-xs');
  expect(heading.className).toContain('text-muted-foreground');
  expect(heading.className).not.toMatch(/text-\[\d+px\]|text-(?:black|white|primary)\//);
};

describe('PinnedSection', () => {
  const reorderPinnedChats = vi.fn();
  const pinned = [chat('a'), chat('b'), chat('c')];

  beforeEach(() => {
    reorderPinnedChats.mockClear();
    useChatStore.setState({ reorderPinnedChats });
    dnd.onDragEnd = undefined;
  });

  const drop = (event: DragEndStub) => {
    const handler = dnd.onDragEnd;
    expectDefined(handler, 'the drop handler of the pinned drag context');
    act(() => handler(event));
  };

  it('lists the pinned chats in the given order, numbered from 1, under the pinned heading', () => {
    render(<PinnedSection chats={pinned} isMobile={false} rowProps={rowProps} />);

    expect(screen.getByText('chat.pin.section')).toBeTruthy();
    const rows = screen.getAllByTestId(/^pinned:/);
    expect(rows.map((row) => row.getAttribute('data-testid'))).toEqual(['pinned:a', 'pinned:b', 'pinned:c']);
    expect(rows.map((row) => row.getAttribute('data-pin-index'))).toEqual(['1', '2', '3']);
    expect(rows.map((row) => row.getAttribute('data-active'))).toEqual(['false', 'true', 'false']);
  });

  it('writes the heading at a readable size in the muted text color on every screen', () => {
    const { rerender } = render(<PinnedSection chats={pinned} isMobile={false} rowProps={rowProps} />);
    expectReadableHeading(screen.getByText('chat.pin.section'));

    rerender(<PinnedSection chats={pinned} isMobile rowProps={rowProps} />);
    expectReadableHeading(screen.getByText('chat.pin.section'));
  });

  it('saves the new order of all pinned chats when one is dropped on another', () => {
    render(<PinnedSection chats={pinned} isMobile={false} rowProps={rowProps} />);

    drop({ active: { id: 'a' }, over: { id: 'c' } });
    expect(reorderPinnedChats).toHaveBeenLastCalledWith(['b', 'c', 'a']);

    drop({ active: { id: 'c' }, over: { id: 'a' } });
    expect(reorderPinnedChats).toHaveBeenLastCalledWith(['c', 'a', 'b']);
    expect(reorderPinnedChats).toHaveBeenCalledTimes(2);
  });

  it.each([
    ['lands outside every row', { active: { id: 'a' }, over: null }],
    ['lands back on the same row', { active: { id: 'a' }, over: { id: 'a' } }],
    ['starts from a chat that is not pinned here', { active: { id: 'zzz' }, over: { id: 'a' } }],
    ['lands on a chat that is not pinned here', { active: { id: 'a' }, over: { id: 'zzz' } }],
  ] as const)('saves nothing when a drop %s', (_label, event) => {
    render(<PinnedSection chats={pinned} isMobile={false} rowProps={rowProps} />);

    drop(event);

    expect(reorderPinnedChats).not.toHaveBeenCalled();
  });
});

describe('DateGroupSection', () => {
  const group: DateGroup = { key: 'today', items: [chat('a'), chat('b')] };
  const baseProps = {
    group,
    collapsed: false,
    onToggle: vi.fn(),
    isMobile: false,
    batchMode: false,
    selectedIds: new Set<string>(),
    onToggleSelect: vi.fn(),
    rowProps,
  };

  beforeEach(() => {
    baseProps.onToggle.mockClear();
    baseProps.onToggleSelect.mockClear();
  });

  const rowsBody = () => {
    const body = screen.getByTestId('row:a').closest('div.grid');
    if (!(body instanceof HTMLElement)) {
      throw new Error('the animated rows wrapper is missing');
    }
    return body;
  };
  const chevron = () => {
    const icon = screen.getByRole('button', { name: 'chat.dateGroup.today' }).querySelector('svg');
    if (!icon) {
      throw new Error('the group chevron is missing');
    }
    return icon;
  };

  it('names the group and reports its key when the header is pressed', () => {
    render(<DateGroupSection {...baseProps} />);

    fireEvent.click(screen.getByRole('button', { name: 'chat.dateGroup.today' }));

    expect(baseProps.onToggle).toHaveBeenCalledExactlyOnceWith('today');
  });

  it('opens the rows to full height when expanded and folds them to nothing when collapsed', () => {
    const { rerender } = render(<DateGroupSection {...baseProps} />);
    expect(rowsBody().style.gridTemplateRows).toBe('1fr');
    expect(chevron().classList.contains('-rotate-90')).toBe(false);

    rerender(<DateGroupSection {...baseProps} collapsed />);
    expect(rowsBody().style.gridTemplateRows).toBe('0fr');
    expect(chevron().classList.contains('-rotate-90')).toBe(true);
    // Folding hides rows without unmounting them, so an open rename or menu survives a collapse.
    expect(screen.getByTestId('row:a')).toBeTruthy();
  });

  it('shows every chat of the group with the list-level props', () => {
    render(<DateGroupSection {...baseProps} />);

    expect(screen.getByTestId('row:a').getAttribute('data-active')).toBe('false');
    expect(screen.getByTestId('row:b').getAttribute('data-active')).toBe('true');
  });

  it('hands each row its own selection state and the batch flag', () => {
    render(<DateGroupSection {...baseProps} batchMode selectedIds={new Set(['b'])} />);

    expect(screen.getByTestId('row:a').getAttribute('data-batch')).toBe('true');
    expect(screen.getByTestId('row:a').getAttribute('data-selected')).toBe('false');
    expect(screen.getByTestId('row:b').getAttribute('data-selected')).toBe('true');
  });

  it('lets a row toggle its own selection', () => {
    render(<DateGroupSection {...baseProps} batchMode />);

    fireEvent.click(screen.getByRole('button', { name: 'select b' }));

    expect(baseProps.onToggleSelect).toHaveBeenCalledExactlyOnceWith('b');
  });

  it('writes the group name at a readable size in the muted text color on every screen', () => {
    const { rerender } = render(<DateGroupSection {...baseProps} />);
    expectReadableHeading(screen.getByText('chat.dateGroup.today'));

    rerender(<DateGroupSection {...baseProps} isMobile />);
    expectReadableHeading(screen.getByText('chat.dateGroup.today'));
  });

  it('tells assistive tech whether the group is open', () => {
    const { rerender } = render(<DateGroupSection {...baseProps} />);
    const header = () => screen.getByRole('button', { name: 'chat.dateGroup.today' });
    expect(header().getAttribute('aria-expanded')).toBe('true');

    rerender(<DateGroupSection {...baseProps} collapsed />);
    expect(header().getAttribute('aria-expanded')).toBe('false');
  });

  it('makes the header a finger-sized row on a phone and a compact one elsewhere', () => {
    const { rerender } = render(<DateGroupSection {...baseProps} />);
    const header = () => screen.getByRole('button', { name: 'chat.dateGroup.today' });
    expect(header().className).toContain('min-h-7');
    expect(header().className).not.toContain('min-h-11');

    rerender(<DateGroupSection {...baseProps} isMobile />);
    expect(header().className).toContain('min-h-11');
  });
});
